"""Regressions for downtown routing, through traffic and planning comparisons (2026-11-07)."""
import math
import pytest
from panda_abm.core.urban_traffic import road_agents
from panda_abm.core.traffic import DRIVING
from panda_abm.twin.environments import downtown_environment, facility_from_environment
from panda_abm.twin.platform import simulate, compare
from panda_abm.twin.replay import build_replay_model
from panda_abm.twin.urban_scenarios import apply_policy
from panda_abm.environment.navigation import AisleNetwork


@pytest.fixture(scope='module')
def downtown():
    return downtown_environment()


@pytest.mark.parametrize('seed', [1000, 1002])
def test_downtown_runs_complete_with_traffic(downtown, seed):
    # Previously KeyError / "No route satisfying turn restrictions" within minutes.
    r = simulate(dict(environment=downtown, seed=seed, occupancy=.4, population_size=30, arrival_interval_s=20,
                      simulation_duration_s=900, traffic_enabled=True))
    assert r['metrics']['success_pct'] > 0
    assert r['metrics']['entry_wait_s'] is not None and r['metrics']['jam_episodes'] is not None


def test_heading_blocked_position_still_reaches_targets(downtown):
    # Off-graph during a bay maneuver, facing away from both nearby graph nodes.
    nav = AisleNetwork(facility_from_environment(downtown))
    targets = list(nav.space_nodes.values())[:6]
    d = nav.distances((16.654579800390437, 97.28509286349144), targets, heading=(-0.2786, -0.9604))
    assert all(t in d for t in targets)


def test_boundary_vehicle_facing_out_gets_a_real_patrol_goal(downtown):
    f = facility_from_environment(downtown)
    nav = AisleNetwork(f)
    entry = f.entry_points[3]
    goal = nav.next_patrol(entry, {}, heading=(-0.99986, 0.01686))
    assert math.dist(nav.positions[goal], entry) > 1


@pytest.mark.parametrize('environment', ['walmart', 'downtown'])
def test_through_vehicles_leave_the_entry_and_finish(downtown, environment):
    # Rounded route coordinates once gave through vehicles a zero speed budget forever.
    settings = dict(seed=1000, population_size=5, arrival_interval_s=60, occupancy=.4, traffic_enabled=True,
                    through_traffic='high', through_demand_s=120, simulation_duration_s=600)
    if environment == 'downtown':
        settings['environment'] = downtown
    _, _, _, m = build_replay_model(settings)
    for _ in range(600):
        m.step()
    snapshot = m.through_traffic.snapshot()
    assert snapshot['arrived'] > 0 and snapshot['completed'] >= snapshot['arrived'] // 2


def test_no_permanent_gridlock_downtown(downtown):
    _, _, _, m = build_replay_model(dict(environment=downtown, seed=1000, population_size=45, arrival_interval_s=20,
                                         occupancy=.8, traffic_enabled=True, simulation_duration_s=900))
    stalled, worst = {}, 0
    for _ in range(900):
        m.step()
        for a in road_agents(m):
            moving = a.state not in DRIVING or a.traffic_speed_m_s >= .05
            stalled[a.driver_id] = 0 if moving else stalled.get(a.driver_id, 0)+1
            worst = max(worst, stalled[a.driver_id])
    # Signals, queues and releases all resolve well within two minutes.
    assert worst < 120
    assert all('reason' in r for r in m.traffic.snapshot()['deadlock_releases'])


def test_street_limit_policies(downtown):
    f = facility_from_environment(downtown)
    limited = apply_policy(f, 'street_1h')
    assert {s.time_limit_minutes for s in limited.spaces if s.parking_kind == 'on_street'} == {60}
    assert [s.time_limit_minutes for s in limited.spaces if s.parking_kind != 'on_street'] == \
           [s.time_limit_minutes for s in f.spaces if s.parking_kind != 'on_street']
    from panda_abm.environment import load_facility_from_lot_config
    with pytest.raises(ValueError):
        apply_policy(load_facility_from_lot_config('data/lot_config.json'), 'street_3h')


def test_free_count_message_uses_environment_capacity(downtown):
    from panda_abm.twin.replay import validate_settings
    with pytest.raises(ValueError, match='0–241'):
        validate_settings(dict(environment=downtown, initial_free_count=500, traffic_enabled=True))


def test_planning_scenario_comparison():
    result = compare(dict(settings=dict(seed=1000, population_size=8, arrival_interval_s=20, occupancy=.4),
                          models=['cpt'], replications=2,
                          scenarios=[dict(label='Configured', settings=dict(parking_policy='configured')),
                                     dict(label='Busier', settings=dict(arrival_interval_s=10)),
                                     dict(label='Mixed visits', settings=dict(visit_profile='mixed'))]))
    assert result['mode'] == 'scenarios' and len(result['runs']) == 6
    assert [c['scenario'] for c in result['cells']] == ['Configured', 'Busier', 'Mixed visits']
    assert [e['scenario'] for e in result['effects']] == ['Busier', 'Mixed visits']
    # Arrival gap changes arrival times (unmatched); visit profile keeps arrivals but alters stays.
    assert result['matched_population']['Configured']
    assert result['effects'][0]['metrics']['search_s']['replications'] == 2
    with pytest.raises(ValueError):
        compare(dict(settings={}, models=['cpt'], replications=1,
                     scenarios=[dict(label='a', settings=dict(seed=1)), dict(label='b', settings={})]))


def test_independent_movement_outcomes_unchanged_by_traffic_fixes():
    # Values from the original code (commit 7eb76a3); traffic-only fixes must not alter them.
    for population, metrics in ((10, dict(search_s=36.2, walk_m=127.14, failed_claims=1.0)),
                                (80, dict(search_s=50.99, walk_m=119.34, failed_claims=1.85))):
        r = simulate(dict(seed=1000, population_size=population, arrival_interval_s=20, occupancy=.4,
                          simulation_duration_s=600 if population == 10 else None))
        assert {k: round(r['metrics'][k], 2) for k in metrics} == metrics


def test_imported_model_names_are_kept_and_checked():
    from panda_abm.twin.environments import example_environment, validate_environment
    env = example_environment()
    digest = '0'*64
    named = validate_environment(env | dict(model_files=[dict(name='lot.glb', sha256=digest, label='North lot pavement')]))
    assert named['model_files'][0]['label'] == 'North lot pavement'
    for bad in (dict(label=''), dict(label='x'*81), dict(colour='red')):
        with pytest.raises(ValueError):
            validate_environment(env | dict(model_files=[dict(name='lot.glb', sha256=digest, **bad)]))


def test_corrected_walmart_layout():
    import hashlib, json
    from pathlib import Path
    from shapely.geometry import Polygon
    from shapely.strtree import STRtree
    from panda_abm.environment.pedestrian_geometry import bay_polygon
    from panda_abm.twin.environments import corrected_environment
    root = Path(__file__).resolve().parents[1]
    # The published layout stays byte-identical.
    assert hashlib.sha256((root/'data/lot_config.json').read_bytes()).hexdigest() == \
        '2704bc586d74885a73a87b1850c8e3fabb2bda959256b9d9e23f23814351c7bb'
    env = corrected_environment()
    slots = env['config']['slots']
    assert len(slots) == 909 and env['validation']['usable_spaces'] == 790
    satellite = json.loads((root/'data/lot_config.satellite_estimated.json').read_text(encoding='utf8'))['slots']
    traced = {s['id']: s for s in slots}
    assert all((traced[s['id']]['local_x_m'], traced[s['id']]['local_y_m']) == (s['local_x_m'], s['local_y_m']) for s in satellite)
    polygons = [Polygon(bay_polygon(s)) for s in slots]
    tree = STRtree(polygons)
    assert not any(polygons[j].intersection(p).area > .05 for i, p in enumerate(polygons) for j in tree.query(p) if j != i)
    walk = env['config']['pedestrian_network']['summary']['reachable_usable_by_destination']
    assert walk == {'door_1': 790, 'door_2': 790}
    r = simulate(dict(environment=env, seed=1000, population_size=40, arrival_interval_s=20, occupancy=.8,
                      traffic_enabled=True, simulation_duration_s=900))
    assert r['metrics']['success_pct'] > 90


def test_jams_clear_and_report_root_causes():
    # Oversaturated corrected Walmart lot: queues may persist, but no vehicle stays stopped.
    from panda_abm.twin.environments import corrected_environment
    _, _, _, m = build_replay_model(dict(environment=corrected_environment(), seed=1000, population_size=120,
                                         arrival_interval_s=5, occupancy=.95, traffic_enabled=True, simulation_duration_s=900))
    stopped, longest = {}, 0
    for _ in range(900):
        m.step()
        for a in road_agents(m):
            held = a.state in DRIVING and a.traffic_speed_m_s < .05 and getattr(a, 'traffic_reason', None)
            stopped[a.driver_id] = stopped.get(a.driver_id, 0)+1 if held else 0
            longest = max(longest, stopped[a.driver_id])
    snapshot = m.traffic.snapshot()
    assert longest < 400
    assert snapshot['jam_episodes'] and all(e['root_cause_seconds'] for e in snapshot['jam_episodes'])
    assert all('aisle' in r and 'reason' in r for r in snapshot['deadlock_releases'])
