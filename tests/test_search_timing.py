from dataclasses import replace
import math
import networkx as nx
import pytest

from panda_abm.behavior.factory import make_population
from panda_abm.behavior import BehavioralParameters,DriverAttributes,DriverSpec,PopulationSpec,ReferencePoints
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.environment import Facility,ParkingSpace,generate_synthetic_facility,load_facility_from_lot_config


def signature(model):
    return [(a.driver_id,a.parking_time_s,a.chosen_space_id,a.search_time_s,tuple(a.path)) for a in sorted(model.agents,key=lambda a:a.driver_id)]


@pytest.mark.parametrize('decision_model',['deterministic','rum','cpt'])
def test_output_cadence_does_not_change_physical_outcomes(decision_model):
    facility=generate_synthetic_facility(42)
    pop=make_population(facility,size=8,seed=42)
    results=[]
    for interval in (5,10,20,30):
        model=ParkingModel(facility,pop,decision_model=decision_model,seed=42,step_seconds=interval,initial_occupancy_rate=.7)
        model.run_until_complete();results.append(signature(model))
    assert all(x==results[0] for x in results)


def test_search_explores_connected_aisles_and_finds_space_away_from_destination():
    facility=Facility('explore','Explore',(
        ParkingSpace('A0','A',0,0,unavailable=True),ParkingSpace('A1','A',0,100,unavailable=True),
        ParkingSpace('B0','B',120,0,unavailable=True),ParkingSpace('B1','B',120,100)),
        ((-20,-8),),((-20,-8),),synthetic=True)
    spec=DriverSpec(DriverAttributes('D',0,0,expected_dwell_duration_s=10),
        BehavioralParameters(acceptance_utility_threshold=0),ReferencePoints())
    model=ParkingModel(facility,PopulationSpec('p',42,(spec,)),initial_occupancy_rate=0,perception_radius_m=12)
    model.run_until_complete();agent=next(iter(model.agents))
    assert agent.chosen_space_id=='B1' and agent.state==DriverState.LEFT
    assert len(agent.aisle_visits)>=2
    assert agent.search_distance_m>math.dist(facility.entry_points[0],(120,100))
    for a,b in zip(agent.path,agent.path[1:]):
        midpoint=((a[0]+b[0])/2,(a[1]+b[1])/2)
        anchors=model.navigation._anchors(midpoint)
        assert min(math.dist(midpoint,foot) for _,_,foot in anchors)<1e-6


@pytest.mark.parametrize('full',[False,True])
def test_elapsed_search_matches_all_event_timestamps_and_deadline(full):
    facility=generate_synthetic_facility(8);pop=make_population(facility,size=12,seed=8)
    model=ParkingModel(facility,pop,initial_occupancy_rate=1 if full else .8)
    model.run_until_complete()
    starts={r.agent_id:r.time_s for r in model.event_logger.records if r.event_type=='SearchStarted'}
    ends={r.agent_id:r.time_s for r in model.event_logger.records if r.event_type in ('ParkingStarted','SearchAbandoned')}
    for a in model.agents:
        assert a.search_time_s==pytest.approx(ends[a.driver_id]-starts[a.driver_id])
        assert a.search_time_s<=model.max_search_time_s
    if full:assert all(a.search_time_s==600 for a in model.agents)


def test_seeded_tie_breaking_does_not_depend_on_insertion_order():
    facility=Facility('tie','tie',(ParkingSpace('only','A',0,0),),((0,0),),((0,0),),synthetic=True)
    pop=make_population(facility,size=2,seed=42)
    pop=replace(pop,drivers=tuple(replace(d,attributes=replace(d.attributes,arrival_time_s=0,expected_dwell_duration_s=900)) for d in pop.drivers))
    winners=[]
    for reverse in (False,True):
        model=ParkingModel(facility,pop,initial_occupancy_rate=0)
        model.agents.sort(key=lambda a:a.driver_id,ascending=not reverse,inplace=True)
        model.run_until_complete();winners.append([a.driver_id for a in model.agents if a.parking_time_s is not None])
    assert winners[0]==winners[1]
    assert len(winners[0])==1


def test_walmart_network_includes_all_side_spaces_and_connected_access_points():
    facility=load_facility_from_lot_config('data/lot_config.json')
    pop=make_population(facility,size=1)
    model=ParkingModel(facility,pop,initial_occupancy_rate=0)
    assert set(model.navigation.space_nodes)=={s.space_id for s in facility.spaces}
    assert nx.is_connected(model.navigation.graph)
    for point in facility.entry_points+facility.exit_points:
        assert model.navigation.graph.degree(model.navigation._node(point))>0


@pytest.mark.parametrize('resolution',[1.,.5,.25])
def test_travel_and_maneuver_time_converge_to_analytic_route_time(resolution):
    facility=Facility('analytic','analytic',(ParkingSpace('S','A',0,0),),((0,-9),),((0,-9),),synthetic=True)
    spec=DriverSpec(DriverAttributes('D',0,0,expected_dwell_duration_s=1),BehavioralParameters(acceptance_utility_threshold=0),ReferencePoints())
    model=ParkingModel(facility,PopulationSpec('p',42,(spec,)),initial_occupancy_rate=0,integration_seconds=resolution)
    node=model.navigation.space_nodes['S']
    expected=model.navigation.distances((0,-9))[node]/model.search_speed_m_per_s+model.parking_maneuver_s
    model.run_until_complete();agent=next(iter(model.agents))
    assert expected-1e-9<=agent.parking_time_s<=expected+resolution+1e-9
    assert agent.search_time_s==agent.parking_time_s-agent.search_started_s


def test_targeting_cannot_bypass_the_elapsed_search_deadline():
    from panda_abm.behavior.decision import DeterministicUtilityModel
    class UncheckedTargetModel(DeterministicUtilityModel):
        # Exercise the engine's independent deadline backstop even when a
        # custom decision provider overlooks the shared reachability filter.
        def evaluate_candidates(self,context,candidates,*args,**kwargs):
            return super().evaluate_candidates(replace(context,remaining_search_time_s=None),candidates,*args,**kwargs)
    facility=Facility('far','far',(ParkingSpace('far','A',4000,0),),((0,-8),),((0,-8),),synthetic=True)
    spec=DriverSpec(DriverAttributes('D',4000,0),BehavioralParameters(acceptance_utility_threshold=0),ReferencePoints())
    model=ParkingModel(facility,PopulationSpec('p',42,(spec,)),decision_model=UncheckedTargetModel(),initial_occupancy_rate=0,perception_radius_m=5000)
    model.run_until_complete();agent=next(iter(model.agents))
    assert any(r.event_type=='TargetSelected' for r in model.event_logger.records)
    assert agent.state==DriverState.ABANDONED and agent.parking_time_s is None
    assert agent.search_time_s==600
