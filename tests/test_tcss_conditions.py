from dataclasses import replace
import math
import pytest
from panda_abm.environment import load_facility_from_lot_config,generate_synthetic_facility,ParkingSpace
from panda_abm.behavior.continuous import make_population
from panda_abm.behavior.decision.base import DecisionContext
from panda_abm.behavior import BehavioralParameters,ReferencePoints
from panda_abm.core.model import ParkingModel
from panda_abm.simulation.tcss_conditions import ExperimentalParkingModel,SimpleSearchDecisionModel,transfer_facility


def build(mode='space',**kwargs):
    f=generate_synthetic_facility();p=make_population(f,size=8,seed=1000)
    return ExperimentalParkingModel(f,p,seed=1000,initial_occupancy_rate=.8,
        information_mode=mode,run_id='matched',decision_seed_namespace='matched',**kwargs)


def signature(m):
    return [(a.driver_id,a.parking_time_s,a.chosen_space_id,a.search_time_s,a.lost_space_events)
            for a in sorted(m.agents,key=lambda a:a.driver_id)]


@pytest.mark.parametrize('mode',['unaided','aisle','space'])
def test_default_extension_and_zero_adoption_preserve_baseline(mode):
    x=build(mode);y=ParkingModel(x.facility,x.population,seed=1000,initial_occupancy_rate=.8,
        information_mode=mode,run_id='matched',decision_seed_namespace='matched')
    x.run_until_complete();y.run_until_complete();assert signature(x)==signature(y)
    x=build(mode,adoption_rate=0);y=build('unaided')
    x.run_until_complete();y.run_until_complete();assert signature(x)==signature(y)
    assert all(a.information_reports_received==0 for a in x.agents)


def test_adoption_sets_nested_and_independent_of_service_and_supply():
    a=build(adoption_rate=.25);b=build('aisle',adoption_rate=.75,background_median_s=1800)
    assert a.adopters<=b.adopters
    assert a.adoption_draws==b.adoption_draws
    assert a.population==b.population


def test_simple_ignores_aspiration_prefers_local_then_graph_approach_and_stable_id():
    ctx=DecisionContext('d',BehavioralParameters(acceptance_utility_threshold=999),ReferencePoints(),0,(0,0),(0,0),
        approach_times_s={'local':10,'remote':1,'b':10},remaining_search_time_s=20)
    spaces=[ParkingSpace('remote','A',100,0),ParkingSpace('local','A',20,0)]
    model=SimpleSearchDecisionModel()
    assert model.evaluate_candidates(ctx,spaces).chosen_space_id=='local'
    assert model.evaluate_candidates(ctx,[spaces[0]]).chosen_space_id=='remote'
    assert model.evaluate_candidates(ctx,[replace(spaces[1],space_id='b'),spaces[1]]).chosen_space_id=='b'
    assert model.evaluate_candidates(replace(ctx,remaining_search_time_s=.5),spaces).chosen_action=='continue'
    assert model.evaluate_candidates(ctx,[replace(spaces[1],accessible=True)]).chosen_action=='continue'


def test_stale_report_never_leaks_remote_present_but_local_view_is_current():
    m=build(report_delay_s=30);a=next(iter(m.agents));a.x_m=-1000;a.y_m=-1000
    sid=m.facility.spaces[0].space_id
    before=m.remote_snapshot()[1][sid]
    # Change the world after its initial cached snapshot.
    if m.space_states[sid].occupied:m.resource_manager.release_space('initial_occupancy',sid)
    else:m.resource_manager.claim_space('other',sid)
    m.clock_s=10;m.before_physical_tick()
    o={o.space.space_id:o for o in m.perceive(a)}[sid]
    assert o.observed_at_s==0 and o.perceived_available==before
    m.clock_s=40;m.before_physical_tick()
    o={o.space.space_id:o for o in m.perceive(a)}[sid]
    assert o.observed_at_s==10 and o.perceived_available!=before
    a.x_m=o.space.x_m;a.y_m=o.space.y_m
    assert {o.space.space_id:o for o in m.perceive(a)}[sid].observed_at_s==40


def test_stale_aisle_counts_are_from_cache_not_current_world():
    m=build('aisle',report_delay_s=30);a=next(iter(m.agents))
    report=m.aisle_information.snapshot(a)
    for sid,s in m.space_states.items():
        if s.occupied:m.resource_manager.release_space('initial_occupancy',sid)
    m.clock_s=10;m.before_physical_tick()
    assert m.aisle_information.snapshot(a)==report


def test_turnover_has_frozen_schedule_and_releases_only_once():
    a=build(background_median_s=1800);b=build('aisle',background_median_s=1800,adoption_rate=.25)
    assert a.background_schedule==b.background_schedule
    due,sid=a.background_schedule[0]
    a.clock_s=math.ceil(due);a.before_physical_tick()
    assert a.space_states[sid].occupant_id is None
    a.resource_manager.claim_space('new_driver',sid)
    a.before_physical_tick()
    assert a.space_states[sid].occupant_id=='new_driver'
    releases=[e for e in a.event_logger.records if e.event_type=='BackgroundSpaceReleased' and e.space_id==sid]
    assert len(releases)==1


def test_transfer_layout_preserves_supply_and_restrictions_with_connected_routes():
    old=load_facility_from_lot_config('data/lot_config.json');f=transfer_facility(old)
    assert len(f.spaces)==1106 and all(not s.unavailable for s in f.spaces)
    assert len(f.entry_points)==len(f.walmart_doors)==2
    for s in f.spaces:
        previous=old.space_by_id[s.space_id]
        assert (s.accessible,s.reserved_type,s.permit_requirement)==(previous.accessible,previous.reserved_type,previous.permit_requirement)
        assert s.distance_to_door_1_m==pytest.approx(math.dist((s.x_m,s.y_m),f.walmart_doors[0]))
    m=ExperimentalParkingModel(f,make_population(f,size=2),initial_occupancy_rate=.95)
    assert len(m.navigation.space_nodes)==1106


@pytest.mark.parametrize('settings',[{'adoption_rate':-1},{'report_delay_s':float('nan')},{'background_median_s':0}])
def test_invalid_conditions_rejected(settings):
    with pytest.raises(ValueError):build(**settings)
