"""Environment validation, routing, provenance and unchanged reference geometry."""
from copy import deepcopy
from dataclasses import replace
import json
import pytest
from panda_abm.twin.environments import (synthetic_environment,validate_environment,facility_from_environment,export_network,ROOT)
from panda_abm.environment import load_facility_from_lot_config
from panda_abm.simulation.tcss_conditions import transfer_facility
from panda_abm.environment.navigation import AisleNetwork
from panda_abm.twin.replay import record_run,LiveSimulation,validate_settings
from panda_abm.twin.platform import simulate,compare

@pytest.fixture(scope='module')
def synthetic():return synthetic_environment()


def test_synthetic_matches_existing_transfer_geometry_and_routes(synthetic):
    expected=transfer_facility(load_facility_from_lot_config(ROOT/'data/lot_config.json'))
    actual=facility_from_environment(synthetic)
    assert [(s.space_id,s.x_m,s.y_m,s.unavailable,s.accessible) for s in actual.spaces]==[(s.space_id,s.x_m,s.y_m,s.unavailable,s.accessible) for s in expected.spaces]
    a,b=AisleNetwork(expected),AisleNetwork(actual)
    assert list(a.positions.values())==list(b.positions.values())
    for sid in (expected.spaces[0].space_id,expected.spaces[-1].space_id):
        assert a.route(expected.entry_points[0],a.space_nodes[sid])==b.route(actual.entry_points[0],b.space_nodes[sid])
    assert synthetic['validation']['usable_spaces']==1106


@pytest.mark.parametrize('change', ['duplicate','nonfinite','disconnected','missing_access','no_doors','bad_bool','bad_scale','external_path'])
def test_invalid_environments_rejected(synthetic,change):
    env=deepcopy(synthetic);c=env['config']
    if change=='duplicate':c['slots'][1]['id']=c['slots'][0]['id']
    if change=='nonfinite':c['slots'][0]['local_x_m']=float('nan')
    if change=='disconnected':c['aisle_network']['nodes']['isolated']=[999,999]
    if change=='missing_access':c['aisle_network']['space_access'].pop(c['slots'][0]['id'])
    if change=='no_doors':c['walmart_doors']=[]
    if change=='bad_bool':c['slots'][0]['is_accessible']='false'
    if change=='bad_scale':env['alignment']['scale']=0
    if change=='external_path':env['model_files']=[dict(name='../x.glb',sha256='a'*64)]
    with pytest.raises(ValueError):validate_environment(env)


def test_recompute_stale_distances_and_alignment_provenance(synthetic):
    env=deepcopy(synthetic);env['config']['slots'][0]['distance_to_door_1_m']=999999
    canonical=validate_environment(env)
    assert canonical['config_sha256']==synthetic['config_sha256']
    env['alignment']['east_m']=20
    aligned=validate_environment(env)
    assert aligned['config_sha256']==canonical['config_sha256']
    assert aligned['environment_sha256']!=canonical['environment_sha256']


def test_small_environment_uses_own_inventory_and_resumes(synthetic):
    env=deepcopy(synthetic);c=env['config'];c['slots']=c['slots'][:8]
    f=facility_from_environment(synthetic);f=replace(f,spaces=f.spaces[:8],aisle_network=None)
    c['aisle_network']=export_network(f)
    # This fixture deliberately replaces both inventories; rebuild its access map.
    if c.get('pedestrian_network'):
        ids={s['id'] for s in c['slots']}
        c['pedestrian_network']['space_access']={k:v for k,v in c['pedestrian_network']['space_access'].items() if k in ids}
    env=validate_environment(env)
    settings=dict(environment=env,initial_occupied_space_ids=[c['slots'][0]['id']],population_size=2,simulation_duration_s=60)
    assert validate_settings(settings)['occupancy']==.125
    with pytest.raises(ValueError):validate_settings(settings|dict(initial_occupied_space_ids=None,initial_free_count=9))
    replay=record_run(settings);live=LiveSimulation(settings);end=live.advance(60)
    assert replay['summary']==end['summary']
    assert len(replay['initial_occupied'])==1
    result=simulate(settings)
    assert result['config_sha256']==env['config_sha256']
    assert result['environment_sha256']==env['environment_sha256']
    comparison=compare(dict(settings=settings,models=['cpt'],replications=1))
    assert len({r['population_sha256'] for r in comparison['runs']})==1
    assert len({r['config_sha256'] for r in comparison['runs']})==1


def test_satellite_variant_preserves_original_and_records_rule_assumptions():
    import hashlib
    from panda_abm.twin.environments import satellite_environment
    original=(ROOT/'data/lot_config.json').read_bytes()
    old=json.loads(original);lookup={s['id']:s for s in old['slots']}
    env=satellite_environment();config=env['config']
    assert len(old['slots'])==1315 and len(config['slots'])==472
    legacy=ROOT/'research/walmart_pedestrians_20261105/before_lot_config.json'
    if legacy.exists():
        assert config['meta']['original_config_sha256']==hashlib.sha256(legacy.read_bytes()).hexdigest()
    assert env['validation']['usable_spaces']==396
    assert sum(s['is_accessible'] for s in config['slots'])==7
    for key in ('entry_points','exit_points','walmart_doors'):
        assert [(p['id'],p['local_x_m'],p['local_y_m']) for p in config[key]]==[(p['id'],p['local_x_m'],p['local_y_m']) for p in old[key]]
    for space in config['slots']:
        source=lookup[space['nearest_original_id']]
        assert all(space.get(k)==source.get(k) for k in ('type','is_accessible','is_reserved','is_unavailable','is_blocked'))
        assert 'not_field_verified' in space['restriction_review_status']
    network=AisleNetwork(facility_from_environment(env))
    assert len(network.space_nodes)==472
    assert (ROOT/'data/lot_config.json').read_bytes()==original


def test_satellite_live_record_and_comparison_use_own_inventory():
    from panda_abm.twin.environments import satellite_environment
    env=satellite_environment()
    settings=dict(environment=env,population_size=2,initial_free_count=5,simulation_duration_s=60)
    replay=record_run(settings);live=LiveSimulation(settings);end=live.advance(60)
    assert replay['summary']==end['summary']
    assert len(replay['initial_occupied'])==391
    assert live.frame()['supply']['usable_inventory']==396
    assert validate_settings(settings)['occupancy']==1-5/396
    comparison=compare(dict(settings=settings,models=['cpt'],replications=1))
    assert {r['config_sha256'] for r in comparison['runs']}=={env['config_sha256']}
    assert len({r['population_sha256'] for r in comparison['runs']})==1
