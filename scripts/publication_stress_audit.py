"""Prospective simulation verification and sensitivity screen, not empirical validation.

Each replication is the uncertainty unit. Independent worker processes run
simulations; no agents or named personas are assigned to drivers.
"""
from pathlib import Path
from dataclasses import replace, asdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import sys
import time
import zipfile
import platform
import argparse
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior.continuous import make_population, PopulationPriors
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.environment import generate_synthetic_facility, load_facility_from_lot_config

MODELS = ('deterministic', 'rum', 'cpt')
VARIANTS = {
    'baseline': {},
    'concentration_8': {'prior': {'preference_concentration': 8.}},
    'concentration_128': {'prior': {'preference_concentration': 128.}},
    'reference_150': {'prior': {'search_reference_median_s': 150.}},
    'reference_450': {'prior': {'search_reference_median_s': 450.}},
    'loss_aversion_1': {'prior': {'cpt_lambda_median': 1.}},
    'loss_aversion_4': {'prior': {'cpt_lambda_median': 4.}},
    'hazard_0': {'model': {'claim_hazard_per_s': 0.}},
    'hazard_004': {'model': {'claim_hazard_per_s': .004}},
    'perception_30': {'model': {'perception_radius_m': 30.}},
    'perception_100': {'model': {'perception_radius_m': 100.}},
    'scan_5': {'model': {'decision_interval_s': 5.}},
    'scan_20': {'model': {'decision_interval_s': 20.}},
    'resolution_half': {'model': {'integration_seconds': .5}},
    'resolution_two': {'model': {'integration_seconds': 2.}},
    'output_30': {'model': {'step_seconds': 30}},
    'repeat': {},
}


def run(job):
    suite, variant, occupancy, arrival, seed, out = job
    started = time.perf_counter()
    setting = VARIANTS.get(variant, {})
    facility = load_facility_from_lot_config(ROOT/'data/lot_config.json') if suite.startswith('walmart') else generate_synthetic_facility(seed)
    size = 80 if suite == 'walmart_pressure' else 40 if suite == 'walmart' else 24
    priors = replace(PopulationPriors(), arrival_interval_s=arrival, **setting.get('prior', {}))
    pop = make_population(facility, size=size, seed=seed, priors=priors)
    # Short trips exercise turnover/release and keep the numerical screen cheap.
    # This is a declared validation scenario, not a calibrated shopping duration.
    if suite != 'walmart_pressure':
        pop = replace(pop, drivers=tuple(replace(d, attributes=replace(d.attributes, expected_dwell_duration_s=30)) for d in pop.drivers))
    rows, checks = [], []
    for name in MODELS:
        model = ParkingModel(facility, pop, name, seed=seed, run_id=f'audit_{suite}_{seed}',
            decision_seed_namespace='matched', initial_occupancy_rate=occupancy, **setting.get('model', {}))
        model.run_until_complete()
        active = {}; safe = True; claims = releases = 0
        for e in model.event_logger.records:
            if e.event_type == 'SpaceClaimSucceeded':
                safe &= e.space_id not in active
                active[e.space_id] = e.agent_id; claims += 1
            elif e.event_type == 'SpaceReleased':
                safe &= active.get(e.space_id) == e.agent_id
                active.pop(e.space_id, None); releases += 1
        agents = sorted(model.agents, key=lambda a: a.driver_id)
        values = [dict(driver=a.driver_id, space=a.chosen_space_id if a.parking_time_s is not None else None,
                       search=a.search_time_s, walk=a.walking_distance_m, state=a.state.value,
                       parking_time=a.parking_time_s, lost=a.lost_space_events) for a in agents]
        checks.append(dict(suite=suite, variant=variant, occupancy=occupancy, arrival=arrival, seed=seed, model=name,
            exclusive_claims=bool(safe), balanced_release=claims == releases and not active,
            elapsed_identity=all(a.search_time_s == a.search_ended_s-a.search_started_s for a in agents),
            bounded_search=all(0 <= a.search_time_s <= 600 for a in agents),
            terminal=all(a.state in (DriverState.LEFT, DriverState.ABANDONED) for a in agents),
            legal=not any(a.violation for a in agents),
            mobility_constraint=all(a.parking_time_s is None or a.attributes.max_walking_distance_m is None or a.walking_distance_m <= a.attributes.max_walking_distance_m+1e-9 for a in agents),
            finite=all(np.isfinite(e.utility) for e in model.event_logger.records if e.utility is not None),
            full_lot_abandons=occupancy != 1 or claims == 0,
            outcome_hash=hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()))
        for a, v in zip(agents, values):
            rows.append(dict(suite=suite, variant=variant, occupancy=occupancy, arrival=arrival, seed=seed, model=name,
                success=a.parking_time_s is not None, **v))
        del model
    tag = f'{suite}_{variant}_{occupancy}_{arrival}_{seed}'
    Path(out, 'raw', tag+'.json').write_text(json.dumps(dict(checks=checks, drivers=rows)), encoding='utf-8')
    return tag, time.perf_counter()-started


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/publication_audit_20261027')
    out=parser.parse_args().output
    out.mkdir(parents=True, exist_ok=True); (out/'raw').mkdir(exist_ok=True)
    jobs = [('synthetic', 'boundary', occ, arrival, seed, str(out))
            for occ in (0., .8, 1.) for arrival in (0., 20.) for seed in range(101, 106)]
    jobs += [('walmart', variant, .95, 20., seed, str(out)) for variant in VARIANTS for seed in range(101, 104)]
    plan = dict(purpose='Verification and one-factor sensitivity screen; no empirical validation or claim of CPT superiority',
        jobs=jobs, runs=len(jobs)*3, priors=asdict(PopulationPriors()), variants=VARIANTS,
        seeds='101-105 synthetic; 101-103 Walmart; independent of previous 42-51 study',
        changes='24/40 drivers; 30 second dwell exercises turnover; initial background cars static',
        sensitivity='One-factor local screen, not global sensitivity or interactions; three seed Walmart pilot',
        failure_policy='Record all failures; do not tune behavior to improve results', python=platform.python_version())
    if (out/'design.json').exists(): raise FileExistsError('Preserve the original frozen design')
    files = sorted([*ROOT.glob('panda_abm/**/*.py'), *ROOT.glob('scripts/*.py'), *ROOT.glob('tests/*.py'), ROOT/'data/lot_config.json'])
    plan['sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (out/'design.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    with zipfile.ZipFile(out/'source_snapshot.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files: z.write(p, p.relative_to(ROOT))
    with ProcessPoolExecutor(max_workers=3) as pool:
        for tag, elapsed in pool.map(run, jobs): print(f'{tag}: {elapsed:.1f}s', flush=True)
    payload = [json.loads(p.read_text()) for p in sorted((out/'raw').glob('*.json'))]
    pd.DataFrame([v for p in payload for v in p['checks']]).to_csv(out/'checks.csv', index=False)
    pd.DataFrame([v for p in payload for v in p['drivers']]).to_csv(out/'drivers.csv', index=False)
    print(f'Completed {len(jobs)*3} runs', flush=True)


if __name__ == '__main__': main()
