"""Public-platform adapters and paired summaries; decision logic lives in core."""
from __future__ import annotations
from panda_abm.twin.environments import traffic_segment_labels

import hashlib
import json
import platform
import time
import numpy as np
from panda_abm.core.states import DriverState
from panda_abm.twin.replay import build_replay_model, ROOT
from panda_abm.twin.time_window import run_window, window_status, window_summary


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def runtime_versions():
    import mesa, pandas, networkx
    return dict(python=platform.python_version(), numpy=np.__version__,
                pandas=pandas.__version__, mesa=mesa.__version__, networkx=networkx.__version__)


def simulate(settings, include_population=False):
    """Complete a full trip lifecycle without storing rendering samples."""
    start = time.perf_counter()
    settings, facility, population, model = build_replay_model(settings)
    initial = sorted(sid for sid, state in model.space_states.items() if state.occupied)
    population_hash = digest(population.as_dict())
    initialized = time.perf_counter()
    horizon=settings['simulation_duration_s']
    run_window(model,horizon)
    agents = sorted(model.agents, key=lambda a: a.driver_id)
    if horizon is None and not all(a.state in (DriverState.LEFT, DriverState.ABANDONED) for a in agents):
        raise RuntimeError('Simulation exceeded its completion bound')
    outcomes = []
    for a in agents:
        success = a.parking_time_s is not None
        slot = facility.space_by_id[a.chosen_space_id] if success else None
        outcomes.append(dict(driver=a.driver_id, success=success,
            chosen_space=a.chosen_space_id if success else None,
            search_s=a.search_time_s, search_distance_m=a.search_distance_m,
            walk_m=a.walking_distance_m if success else None,
            exit_distance_m=slot.exit_distance(a.attributes.preferred_exit_id) if slot else None,
            lost_claims=a.lost_space_events, parking_time_s=a.parking_time_s))
    parked = [o for o in outcomes if o['success']]
    if model.traffic:
        for a,o in zip(agents,outcomes):
            entry=max(0.,(a.search_started_s if a.search_started_s is not None else model.clock_s)-a.arrival_time_s)
            o.update(entry_delay_s=entry,traffic_delay_s=getattr(a,'traffic_delay_s',0.),
                     arrival_to_search_end_s=entry+a.search_time_s)
    if horizon is not None:
        for a,o in zip(agents,outcomes):
            o.update(window_status(a,model.clock_s))
            if model.traffic:o['arrival_to_search_end_s']=o['entry_delay_s']+o['search_s']
    mean = lambda rows, key: float(np.mean([r[key] for r in rows])) if rows else None
    metrics = dict(search_s=mean(outcomes, 'search_s'), success_pct=100 * len(parked) / len(outcomes),
                   walk_m=mean(parked, 'walk_m'), exit_m=mean(parked, 'exit_distance_m'),
                   failed_claims=mean(outcomes, 'lost_claims'))
    cohort=outcomes
    if horizon is not None:
        cohort=[o for o in outcomes if o['observed_arrival']]
        metrics.update(search_s=mean(cohort,'search_s'),
                       success_pct=100*len(parked)/len(cohort) if cohort else None,
                       failed_claims=mean(cohort,'lost_claims'))
    traffic_snapshot=model.traffic.snapshot() if model.traffic else dict(enabled=False)
    # Planner-facing congestion measures; None when traffic interactions are off.
    metrics.update(entry_wait_s=mean(cohort,'entry_delay_s') if model.traffic else None,
                   arrival_to_search_end_s=mean(cohort,'arrival_to_search_end_s') if model.traffic else None,
                   traffic_delay_vehicle_s=traffic_snapshot['cumulative_delay_s'] if model.traffic else None,
                   jam_episodes=float(len(traffic_snapshot['jam_episodes'])) if model.traffic else None)
    result=dict(segment_labels=traffic_segment_labels(facility,model.navigation),settings=settings, metrics=metrics, outcomes=outcomes,
                population_sha256=population_hash, initial_occupancy_sha256=digest(initial),
                config_sha256=(settings['environment']['config_sha256'] if settings['environment'] else hashlib.sha256((ROOT/'data/lot_config.json').read_bytes()).hexdigest()),
                environment_sha256=settings['environment']['environment_sha256'] if settings['environment'] else None,
                simulated_duration_s=model.clock_s, initialize_wall_s=initialized-start,
                wall_s=time.perf_counter()-start)
    from panda_abm.core.interventions import supply_snapshot
    result.update(supply=supply_snapshot(model), interventions=model.intervention_log,
                  traffic=traffic_snapshot)
    from panda_abm.twin.urban_scenarios import urban_outcomes
    result['urban_outcomes']=urban_outcomes(model)
    result['walking_measure']='pedestrian_network' if facility.pedestrian_network else 'euclidean'
    result['through_traffic']=model.through_traffic.snapshot()
    if horizon is not None:result.update(window_summary=window_summary(model),termination_reason='time_limit')
    if include_population:result['population']=population.as_dict()
    return result


STANDARD_METRICS = ('search_s', 'success_pct', 'walk_m', 'exit_m', 'failed_claims')
TRAFFIC_METRICS = ('entry_wait_s', 'arrival_to_search_end_s', 'traffic_delay_vehicle_s', 'jam_episodes')
# Settings a planning scenario may vary against the shared base scenario.
PLANNING_KEYS = {'parking_policy', 'through_traffic', 'through_demand_s', 'arrival_interval_s', 'demand_duration_s',
                 'population_size', 'visit_profile', 'background_departures', 'occupancy', 'information',
                 'traffic_enabled', 'initial_free_count', 'closed_space_ids'}
MAX_SCENARIO_RUNS = 240


def validate_comparison(payload):
    if not isinstance(payload, dict) or set(payload) - {'settings', 'models', 'replications', 'scenarios'}:
        raise ValueError('Invalid comparison settings')
    from panda_abm.twin.replay import validate_settings
    settings = validate_settings(payload.get('settings', {}))
    models = payload.get('models', [settings['model']])
    reps = payload.get('replications', 5)
    if (not isinstance(models, list) or not models or len(set(models)) != len(models)
            or any(m not in ('deterministic', 'rum', 'cpt') for m in models)):
        raise ValueError('Choose one to three distinct decision models')
    if type(reps) is not int or not 1 <= reps <= 30 or settings['seed'] + reps - 1 > 2147483647:
        raise ValueError('Choose 1–30 replications within the seed range')
    return settings, models, reps


def interval(values, rng):
    values = np.asarray([v for v in values if v is not None], dtype=float)
    if len(values) == 0:
        return dict(mean=None, low=None, high=None, replications=0)
    if len(values) == 1:
        return dict(mean=float(values[0]), low=None, high=None, replications=1)
    means = values[rng.integers(0, len(values), size=(10000, len(values)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return dict(mean=float(values.mean()), low=float(lo), high=float(hi), replications=len(values))


def summarize_comparison(runs, models, seed, keys=STANDARD_METRICS):
    rng = np.random.default_rng(seed)
    cells, effects = [], []
    for name in models:
        for info in ('unaided', 'aisle', 'space'):
            selected = [r for r in runs if r['settings']['model'] == name and r['settings']['information'] == info]
            cells.append(dict(model=name, information=info, metrics={k: interval([r['metrics'][k] for r in selected], rng)
                for k in keys}))
            if info == 'unaided':
                continue
            differences = {k: [] for k in (*keys, 'joint_search_walk_s')}
            jointly_parked = []
            for informed in selected:
                baseline = next(r for r in runs if r['settings']['model'] == name
                    and r['settings']['information'] == 'unaided' and r['settings']['seed'] == informed['settings']['seed'])
                for k in differences:
                    if k == 'joint_search_walk_s':
                        continue
                    a, b = informed['metrics'][k], baseline['metrics'][k]
                    differences[k].append(None if a is None or b is None else a-b)
                base_drivers = {o['driver']: o for o in baseline['outcomes']}
                joint = [(o, base_drivers[o['driver']]) for o in informed['outcomes']
                         if o['success'] and base_drivers[o['driver']]['success']]
                jointly_parked.append(len(joint))
                differences['joint_search_walk_s'].append(float(np.mean([
                    a['search_s']-b['search_s']+(a['walk_m']-b['walk_m'])/1.4 for a, b in joint])) if joint else None)
            effects.append(dict(model=name, information=info,
                metrics={k: interval(v, rng) for k, v in differences.items()}, jointly_parked_counts=jointly_parked))
    return cells, effects


def validate_scenarios(payload, settings, models, reps):
    from panda_abm.twin.replay import validate_settings
    scenarios = payload['scenarios']
    if not isinstance(scenarios, list) or not 2 <= len(scenarios) <= 6:
        raise ValueError('Choose two to six planning scenarios')
    checked = []
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) != {'label', 'settings'}:
            raise ValueError('Each scenario needs a label and settings')
        label, overrides = scenario['label'], scenario['settings']
        if not isinstance(label, str) or not label.strip() or len(label) > 80:
            raise ValueError('Scenario labels must be 1–80 characters')
        if not isinstance(overrides, dict) or set(overrides) - PLANNING_KEYS:
            raise ValueError('Scenarios may vary only planning settings: ' + ', '.join(sorted(PLANNING_KEYS)))
        validate_settings(settings | overrides)
        checked.append(dict(label=label.strip(), settings=overrides))
    if len({c['label'] for c in checked}) != len(checked):
        raise ValueError('Scenario labels must be distinct')
    if reps*len(models)*len(checked) > MAX_SCENARIO_RUNS:
        raise ValueError(f'Reduce replications, models or scenarios: at most {MAX_SCENARIO_RUNS} simulations')
    return checked


def compare_scenarios(payload, progress=None):
    """Planning comparison: each scenario changes chosen settings of one shared base.

    Differences are scenario minus the first (reference) scenario within each seed.
    Populations stay matched unless a scenario changes demand (arrivals, driver
    count or visit profile); the result states which scenarios remained matched.
    """
    settings, models, reps = validate_comparison(payload)
    scenarios = validate_scenarios(payload, settings, models, reps)
    runs, base_fingerprint, matched = [], {}, {s['label']: True for s in scenarios}
    start, total = time.perf_counter(), reps*len(models)*len(scenarios)
    for offset in range(reps):
        seed = settings['seed'] + offset
        for name in models:
            for index, scenario in enumerate(scenarios):
                row = simulate(settings | scenario['settings'] | dict(seed=seed, model=name))
                key = (row['population_sha256'], row['initial_occupancy_sha256'])
                if index == 0:
                    base_fingerprint[seed, name] = key
                elif key != base_fingerprint[seed, name]:
                    matched[scenario['label']] = False
                row['scenario'] = scenario['label']
                if settings['environment'] is not None:
                    row['settings'] = row['settings'] | dict(environment=None, environment_sha256=settings['environment']['environment_sha256'])
                runs.append(row)
                if progress:
                    progress(len(runs), total, name, scenario['label'], seed)
    rng = np.random.default_rng(settings['seed'])
    keys = STANDARD_METRICS + (TRAFFIC_METRICS if any(r['settings']['traffic_enabled'] for r in runs) else ())
    cells, effects = [], []
    for name in models:
        reference = {r['settings']['seed']: r for r in runs if r['settings']['model'] == name and r['scenario'] == scenarios[0]['label']}
        for scenario in scenarios:
            selected = [r for r in runs if r['settings']['model'] == name and r['scenario'] == scenario['label']]
            cells.append(dict(model=name, scenario=scenario['label'],
                              metrics={k: interval([r['metrics'][k] for r in selected], rng) for k in keys}))
            if scenario is scenarios[0]:
                continue
            base = lambda r, k: reference[r['settings']['seed']]['metrics'][k]
            differences = {k: [None if r['metrics'][k] is None or base(r, k) is None else r['metrics'][k]-base(r, k)
                               for r in selected] for k in keys}
            effects.append(dict(model=name, scenario=scenario['label'], reference=scenarios[0]['label'],
                                metrics={k: interval(v, rng) for k, v in differences.items()}))
    return dict(schema_version=2, mode='scenarios', settings=settings, models=models, replications=reps,
        scenarios=scenarios, runs=runs, cells=cells, effects=effects, matched_population=matched, metrics=list(keys),
        runtime=runtime_versions(), wall_s=time.perf_counter()-start,
        method=dict(difference='scenario minus reference scenario within seed', reference=scenarios[0]['label'],
                    bootstrap_resamples=10000, interval='pointwise percentile 95%; no multiplicity adjustment',
                    matched_population_note='Unmatched scenarios change demand, so their differences include population changes.'))


def compare(payload, progress=None):
    if isinstance(payload, dict) and 'scenarios' in payload:
        return compare_scenarios(payload, progress)
    settings, models, reps = validate_comparison(payload)
    runs, fingerprints, populations = [], {}, {}
    start = time.perf_counter()
    for offset in range(reps):
        seed = settings['seed'] + offset
        for name in models:
            for info in ('unaided', 'aisle', 'space'):
                row = simulate(settings | dict(seed=seed, model=name, information=info),include_population=seed not in populations)
                if 'population' in row:populations[seed]=row.pop('population')
                key = (row['population_sha256'], row['initial_occupancy_sha256'])
                if seed in fingerprints and fingerprints[seed] != key:
                    raise RuntimeError('Matched population or initial occupancy differs between conditions')
                fingerprints[seed] = key
                if settings['environment'] is not None:
                    row['settings']=row['settings'] | dict(environment=None,environment_sha256=settings['environment']['environment_sha256'])
                runs.append(row)
                if progress:
                    progress(len(runs), reps*len(models)*3, name, info, seed)
    keys = STANDARD_METRICS + (TRAFFIC_METRICS if settings['traffic_enabled'] else ())
    cells, effects = summarize_comparison(runs, models, settings['seed'], keys)
    return dict(schema_version=1, settings=settings, models=models, replications=reps,
        runs=runs, populations=populations, cells=cells, effects=effects, runtime=runtime_versions(), wall_s=time.perf_counter()-start,
        method=dict(matched=True, difference='informed minus unaided within seed',
                    bootstrap_resamples=10000, interval='pointwise percentile 95%; no multiplicity adjustment',
                    walking_speed_m_s=1.4, joint_population='parked under both conditions'))
