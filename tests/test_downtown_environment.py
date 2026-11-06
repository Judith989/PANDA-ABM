"""Downtown schema and restriction checks; no downtown simulations are executed."""
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import json,hashlib
import pytest
from panda_abm.twin.environments import validate_environment,facility_from_environment,ROOT
from panda_abm.twin.replay import build_replay_model
from panda_abm.behavior.continuous import make_population
from panda_abm.behavior.decision.transforms import build_candidate_features
from panda_abm.environment.choice_set import ChoiceSetBuilder
from panda_abm.environment.perception import PerceivedSpace
from panda_abm.environment.navigation import AisleNetwork

@pytest.fixture
def draft():
    return validate_environment(dict(id='downtown_laramie_review',config=json.loads((ROOT/'data/lot_config.downtown_laramie.review.json').read_text(encoding='utf8'))))

def test_multiple_destinations_access_and_distances(draft):
    facility=facility_from_environment(draft)
    assert len(facility.walmart_doors)==8 and len(facility.entry_points)==6
    assert len(AisleNetwork(facility).positions)>len(facility.spaces)
    population=make_population(facility,size=80,seed=1000)
    assert len({d.attributes.walmart_door_id for d in population.drivers})==8
    assert {d.attributes.preferred_exit_id for d in population.drivers} <= set(facility.exit_point_ids)
    space=facility.spaces[0];pid=facility.exit_point_ids[0]
    features=build_candidate_features(space,destination_m=facility.walmart_doors[0],accumulated_search_time_s=0,familiarity=.5,preferred_exit_id=pid)
    assert features['exit_distance_m']==pytest.approx(draft['config']['slots'][0]['distance_to_'+pid+'_m'])
    assert validate_environment(draft)['environment_sha256']==draft['environment_sha256']

def test_time_limits_include_both_walks_and_no_limit_keeps_long_stays(draft):
    facility=facility_from_environment(draft);attrs=make_population(facility,size=1,seed=1000).drivers[0].attributes
    street=next(s for s in facility.spaces if s.time_limit_minutes==120)
    attrs=replace(attrs,destination_x_m=street.x_m,destination_y_m=street.y_m,expected_dwell_duration_s=7200,max_walking_distance_m=None)
    assert street.permits_planned_stay(attrs)
    attrs=replace(attrs,destination_x_m=street.x_m+14)
    assert not street.permits_planned_stay(attrs)
    agent=SimpleNamespace(attributes=attrs)
    assert ChoiceSetBuilder().build(agent,[PerceivedSpace(street,0,False,True)])==[]
    unlimited=next(s for s in facility.spaces if s.time_limit_minutes is None)
    assert unlimited.permits_planned_stay(replace(attrs,expected_dwell_duration_s=10000))

def test_review_guard_before_any_simulation(draft):
    with pytest.raises(ValueError,match='preview-only'):build_replay_model(dict(environment=draft))

@pytest.mark.parametrize('change',['time_limit','duplicate_destination','conflicting_access','mismatched_alias'])
def test_invalid_generalized_config(draft,change):
    d=deepcopy(draft);c=d['config']
    if change=='time_limit':c['slots'][0]['time_limit_minutes']=-1
    if change=='duplicate_destination':
        c['destinations'][1]['id']=c['destinations'][0]['id'];c.pop('walmart_doors')
    if change=='conflicting_access':c['exit_points'][0]['local_x_m']+=1
    if change=='mismatched_alias':c['destinations'][0]['local_x_m']+=1
    with pytest.raises(ValueError):validate_environment(d)

def test_original_inventory_unchanged():
    original=ROOT/'research/walmart_pedestrians_20261105/before_lot_config.json'
    assert hashlib.sha256(original.read_bytes()).hexdigest()=='6cd8d14592ed7590dfe0c00ddd96424d2dc2ab7a9525e36bed968a6d3ef250a4'
    current=json.loads((ROOT/'data/lot_config.json').read_text())
    assert len(current['slots'])==1315 and current['pedestrian_network']


@pytest.mark.parametrize('model',['deterministic','rum','cpt'])
def test_platform_downtown_starts_without_review_approval(model):
    from panda_abm.twin.environments import downtown_environment
    from panda_abm.twin.replay import LiveSimulation
    env=downtown_environment()
    assert env['id']=='downtown_laramie' and env['config']['meta']['simulation_ready']
    assert not env['config']['meta']['review_required']
    live=LiveSimulation(dict(environment=env,model=model,population_size=2,traffic_enabled=True,information='space',simulation_duration_s=60))
    result=live.advance(5)
    assert result['time_s']==5 and len(result['frames'])==5
    assert result['summary']['drivers']==2
