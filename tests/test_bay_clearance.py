"""Physical bay entry happens after a local check; departure retains its resource."""
from types import SimpleNamespace
import math
from panda_abm.environment import generate_synthetic_facility
from panda_abm.behavior.continuous import make_population
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.core.bay_clearance import begin_maneuver,access_node,release_departure_if_clear,limit_motion,rectangle,overlaps

def model():
    f=generate_synthetic_facility();p=make_population(f,size=2,seed=1000)
    return ParkingModel(f,p,seed=1000,initial_occupancy_rate=0,traffic_enabled=True)

def test_bay_maneuver_excludes_competitor_without_reserving_on_report():
    m=model();a,b=list(m.agents);sid=m.facility.spaces[0].space_id
    a.chosen_space_id=b.chosen_space_id=sid
    assert begin_maneuver(a)
    assert m.resource_manager.is_available(sid)  # Supply is claimed only after maneuver.
    assert not begin_maneuver(b)
    assert getattr(m,'bay_maneuvers')[sid]==a.driver_id

def test_lost_target_rejected_at_aisle_before_entering_occupied_bay():
    m=model();a=list(m.agents)[0];s=m.facility.spaces[0]
    decision=SimpleNamespace(chosen_space_id=s.space_id,chosen_utility=2.)
    a.search_started_s=0.;a.last_decision=decision;a._candidate_times[s.space_id]=10;a._select_target(decision)
    stage=m.navigation.positions[access_node(m,s.space_id)]
    a.x_m,a.y_m=stage;a.route=[]
    m.resource_manager.claim_space('initial_occupancy',s.space_id)
    a.last_tick_s=0.;m.clock_s=1.;a.step()
    assert a.state==DriverState.SEARCHING and a.lost_space_events==1
    assert (a.x_m,a.y_m)==stage
    assert math.dist(stage,(s.x_m,s.y_m))>0

def test_departure_does_not_release_until_vehicle_clears_bay():
    m=model();a=list(m.agents)[0];s=m.facility.spaces[0]
    m.resource_manager.claim_space(a.driver_id,s.space_id)
    a.chosen_space_id=s.space_id;a.x_m,a.y_m=s.x_m,s.y_m
    a._start_exiting()
    assert m.resource_manager.occupant(s.space_id)==a.driver_id
    release_departure_if_clear(a)
    assert m.resource_manager.occupant(s.space_id)==a.driver_id
    a.x_m+=10;release_departure_if_clear(a)
    assert m.resource_manager.is_available(s.space_id)

def test_swept_clearance_cannot_tunnel_into_parked_car():
    m=model();a=list(m.agents)[0];s=m.facility.spaces[0]
    m.resource_manager.claim_space('initial_occupancy',s.space_id)
    a.x_m=s.x_m-12;a.y_m=s.y_m;a.state=DriverState.TARGETING
    safe=limit_motion(a,(1.,0.),20.)
    assert 0<safe<12
    assert a.traffic_reason=='occupied_bay'
    from panda_abm.core.bay_clearance import dimensions,display_position
    assert not overlaps(rectangle(display_position(m,(a.x_m+safe,a.y_m),(1,0)),(1,0),*dimensions(a)),rectangle((s.x_m,s.y_m),(1,0),5.45,2.02))


def test_exported_bay_access_is_on_aisle_not_at_stall_centre():
    from panda_abm.twin.environments import export_network
    m = model()
    network = export_network(m.facility)
    for space in m.facility.spaces:
        point = network['nodes'][network['space_access'][space.space_id]['node']]
        assert math.dist(point, (space.x_m, space.y_m)) > 1e-6


def test_neighboring_occupied_vehicle_prevents_overlapping_parked_pose():
    from panda_abm.core.bay_clearance import parking_clear
    m = model()
    a = list(m.agents)[0]
    first, second = m.facility.spaces[:2]
    # Deliberately malformed inventory: two bays share a centre. A free resource
    # must not imply enough physical room to park beside the occupied resource.
    from dataclasses import replace
    second = replace(second, x_m=first.x_m, y_m=first.y_m)
    m.facility.space_by_id[second.space_id] = second
    m.resource_manager.claim_space('initial_occupancy', second.space_id)
    a.chosen_space_id = first.space_id
    assert not parking_clear(a)
    assert not begin_maneuver(a)


def test_submillimetre_exit_connector_cannot_hold_vehicle_inside_facility():
    m=model();a=list(m.agents)[0]
    a.state=DriverState.EXITING;a.route=[(a.x_m+0.00004,a.y_m)]
    m.traffic.budgets[a.driver_id]=0.
    a._advance_route(1.,count_search=False)
    assert a.route==[]


def test_free_downtown_bay_with_blocked_entry_is_rejected_before_maneuver():
    from panda_abm.twin.environments import downtown_environment, facility_from_environment
    from panda_abm.core.bay_clearance import parking_clear
    f = facility_from_environment(downtown_environment())
    m = ParkingModel(f, make_population(f, size=1, seed=1000), seed=1000,
                     initial_occupancy_rate=0, traffic_enabled=True)
    a = list(m.agents)[0]
    a.chosen_space_id = 'DT105'
    stage = m.navigation.positions[access_node(m, 'DT105')]
    a.x_m, a.y_m = stage
    m.resource_manager.claim_space('initial_occupancy', 'DT104')
    # The parked footprint fits, but the approach crosses the neighboring car.
    assert parking_clear(a)
    assert not begin_maneuver(a)
    assert (a.x_m, a.y_m) == stage
    assert 'DT105' not in m.bay_maneuvers
