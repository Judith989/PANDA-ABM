"""Supply conservation, traffic mechanisms, and live/recorded reproducibility."""
from types import SimpleNamespace
import math
import pytest
from panda_abm.twin.replay import build_replay_model, LiveSimulation, record_run, validate_settings
from panda_abm.core.interventions import apply_intervention, supply_snapshot
from panda_abm.core.traffic import AisleTraffic
from panda_abm.core.states import DriverState


def test_exact_count_and_explicit_ids_select_only_usable_spaces():
    _, facility, _, model = build_replay_model(dict(initial_free_count=5, population_size=1))
    free = sorted(sid for sid in model.space_states if model.resource_manager.is_available(sid))
    assert len(free) == 5
    _, _, _, other = build_replay_model(dict(initial_free_space_ids=free, population_size=1))
    assert {sid for sid in other.space_states if other.resource_manager.is_available(sid)} == set(free)
    assert supply_snapshot(other)['occupied'] == 1101
    with pytest.raises(ValueError):
        build_replay_model(dict(initial_free_space_ids=['missing']))
    blocked = next(s.space_id for s in facility.spaces if s.unavailable)
    with pytest.raises(ValueError):
        build_replay_model(dict(initial_free_space_ids=[blocked]))


def test_closure_preserves_occupant_and_blocks_claim_until_reopened():
    _, _, _, model = build_replay_model(dict(initial_free_count=0, population_size=1))
    sid = next(sid for sid, s in model.space_states.items() if s.occupied)
    apply_intervention(model, dict(action='close', space_ids=[sid]))
    assert model.resource_manager.occupant(sid) == 'initial_occupancy'
    assert supply_snapshot(model)['closed_occupied'] == 1
    apply_intervention(model, dict(action='release', space_ids=[sid]))
    assert not model.resource_manager.is_available(sid)
    apply_intervention(model, dict(action='open', space_ids=[sid]))
    assert model.resource_manager.is_available(sid)
    assert supply_snapshot(model)['occupied'] == 1105
    assert len(model.intervention_log) == 3


def test_map_occupied_ids_start_empty_and_only_selected_spaces_are_occupied():
    settings,facility,_,model=build_replay_model(dict(population_size=1,occupancy=.95,initial_occupied_space_ids=[]))
    assert settings['occupancy']==0
    assert supply_snapshot(model)['occupied']==0
    ids=[s.space_id for s in facility.spaces if not s.unavailable][:3]
    settings,_,_,model=build_replay_model(dict(population_size=1,occupancy=.95,initial_occupied_space_ids=ids))
    assert settings['occupancy']==3/1106
    assert {sid for sid,state in model.space_states.items() if state.occupied}==set(ids)
    with pytest.raises(ValueError):build_replay_model(dict(initial_occupied_space_ids=['missing']))
    with pytest.raises(ValueError):validate_settings(dict(initial_occupied_space_ids=ids,initial_free_count=5))


def test_map_selection_does_not_occupy_closed_unselected_spaces():
    _,facility,_,_=build_replay_model(dict(population_size=1))
    ids=[s.space_id for s in facility.spaces if not s.unavailable][:2]
    _,_,_,model=build_replay_model(dict(population_size=1,initial_occupied_space_ids=[ids[0]],closed_space_ids=[ids[1]]))
    assert supply_snapshot(model)['occupied']==1
    assert not model.space_states[ids[1]].occupied
    assert not model.resource_manager.is_available(ids[1])


def test_unused_percentage_cannot_change_exact_supply_or_decision_draws():
    a,_,_,first=build_replay_model(dict(initial_free_count=5,occupancy=0,population_size=1))
    b,_,_,second=build_replay_model(dict(initial_free_count=5,occupancy=1,population_size=1))
    assert a==b
    assert a['occupancy']==1-5/1106
    assert {sid for sid,s in first.space_states.items() if s.occupied}=={sid for sid,s in second.space_states.items() if s.occupied}
    assert first.seed_for_driver_step('D0000',10)==second.seed_for_driver_step('D0000',10)


def test_intervention_is_atomic_and_cannot_delete_active_driver():
    _, _, _, model = build_replay_model(dict(initial_free_count=5, population_size=1))
    sid = next(sid for sid in model.space_states if model.resource_manager.is_available(sid))
    assert model.resource_manager.claim_space('test-driver', sid)
    with pytest.raises(ValueError):
        apply_intervention(model, dict(action='release', space_ids=[sid]))
    with pytest.raises(ValueError):
        apply_intervention(model, dict(action='close', space_ids=[sid, 'missing']))
    assert not model.space_states[sid].unavailable
    assert model.resource_manager.occupant(sid) == 'test-driver'


@pytest.mark.parametrize('settings',[
    dict(initial_free_count=True), dict(initial_free_count=1107),
    dict(initial_free_count=5, initial_free_space_ids=[]),
    dict(traffic_enabled='yes'), dict(interventions=[dict(action='unknown', space_ids=['x'])]),
    dict(initial_free_space_ids=['x'],closed_space_ids=['x'])])
def test_invalid_supply_settings(settings):
    with pytest.raises(ValueError):validate_settings(settings)


def fake_car(id, x, y, route):
    return SimpleNamespace(driver_id=id,x_m=x,y_m=y,route=route,state=DriverState.SEARCHING,
                           traffic_wait_s=0.,traffic_speed_m_s=0.,maneuver_remaining_s=0.)


def fake_traffic(cars):
    model=SimpleNamespace(agents=cars, search_speed_m_per_s=5., integration_seconds=1.,
                          perception_radius_m=60.,clock_s=0.)
    traffic=AisleTraffic(model)
    traffic.aisle_at=lambda p:'test_aisle'
    return traffic


def test_following_prevents_overtaking_and_reports_both_neighbors():
    follower=fake_car('follower',0,0,[(100,0)])
    leader=fake_car('leader',8,0,[(100,0)])
    traffic=fake_traffic([follower,leader]);traffic.begin_tick()
    assert traffic.distance_budget(follower,1) == pytest.approx(8-traffic.vehicle_length_m-traffic.minimum_gap_m)
    assert traffic.distance_budget(leader,1) == 5.
    assert follower.traffic_reason == 'following_vehicle'
    assert follower.traffic_ahead == 'leader'
    assert leader.traffic_behind == 'follower'
    assert follower.traffic_gap_m == pytest.approx(8-traffic.vehicle_length_m)


def test_junction_has_one_priority_and_opposing_lane_does_not_block():
    a=fake_car('a',-4,0,[(20,0)])
    b=fake_car('b',0,-4,[(0,20)])
    traffic=fake_traffic([a,b]);traffic.begin_tick()
    assert traffic.distance_budget(a,1) == 5.
    assert traffic.distance_budget(b,1) == 0.
    assert b.traffic_reason == 'junction_yield'
    opposing=fake_car('c',4,0,[(-20,0)])
    traffic=fake_traffic([a,opposing]);traffic.begin_tick()
    assert traffic.distance_budget(a,1) == traffic.distance_budget(opposing,1) == 5.


def test_opposing_turns_do_not_enter_same_junction_together():
    a=fake_car('a',0,-8,[(0,0),(-20,0)])
    b=fake_car('b',0,8,[(0,0),(20,0)])
    traffic=fake_traffic([a,b]);traffic.begin_tick()
    assert traffic.distance_budget(a,1)==5.
    assert traffic.distance_budget(b,1)<2.
    assert b.traffic_reason=='junction_yield'


def test_short_congestion_episodes_preserve_duration_and_cause():
    a=fake_car('a',0,0,[(100,0)])
    b=fake_car('b',6,0,[(100,0)])
    traffic=fake_traffic([a,b])
    for t in range(7):
        traffic.model.clock_s=t;traffic.begin_tick();traffic.end_tick()
    traffic.model.clock_s=7
    ongoing=traffic.snapshot()['episodes']
    assert len(ongoing)==1 and ongoing[0]['duration_s']==7
    b.state=DriverState.LEFT
    traffic.begin_tick();traffic.end_tick();traffic.model.clock_s=8
    episode=traffic.snapshot()['episodes'][0]
    assert episode['end_s']==7 and episode['causes']=={'following_vehicle':7}


def test_blocked_queue_cannot_reserve_an_unreachable_crossing():
    cross_traffic=fake_car('c',-5,0,[(20,0)])
    blocked=fake_car('a',0,-10,[(0,20)])
    # The leading vehicle turns before the crossing; its extrapolated heading
    # must not reserve a junction beyond that turn.
    leader=fake_car('b',0,-5,[(0,-4),(10,-4)])
    traffic=fake_traffic([cross_traffic,blocked,leader]);traffic.begin_tick()
    assert traffic.distance_budget(blocked,1)==0
    assert traffic.distance_budget(cross_traffic,1)==5


def test_vehicle_in_crossing_keeps_priority_until_clear():
    inside=fake_car('z',1,0,[(20,0)])
    waiting=fake_car('a',0,-6,[(0,20)])
    waiting.traffic_wait_s=100
    traffic=fake_traffic([inside,waiting]);traffic.begin_tick()
    assert traffic.distance_budget(inside,1)==5
    assert traffic.distance_budget(waiting,1)==0


def test_previous_priority_cannot_trap_vehicle_already_in_junction():
    inside=fake_car('inside',0,0,[(20,0)])
    approaching=fake_car('approaching',0,2.3,[(0,-20)])
    traffic=fake_traffic([inside,approaching])
    traffic.priority_leaders={'approaching'}
    traffic.begin_tick()
    assert traffic.distance_budget(inside,1)==5
    assert traffic.distance_budget(approaching,1)==0


def test_close_junctions_cannot_create_a_circular_yield():
    east=fake_car('east',97.4,-58.7,[(114,-58.7),(128,-58.7)])
    south=fake_car('south',97.4,-52.2,[(97.4,-58.7),(114,-58.7)])
    north=fake_car('north',98.4,-65.2,[(98.4,-58.7),(128,-58.7)])
    west=fake_car('west',103.9,-58.7,[(97.4,-58.7),(97.4,-39)])
    traffic=fake_traffic([east,south,north,west]);traffic.begin_tick()
    assert any(traffic.distance_budget(a,1)>0 for a in (east,south,north,west))
    assert len(traffic.priority_leaders)==1


def test_exit_road_small_bend_is_not_false_crossing_traffic():
    exiting=fake_car('exit',128,-58.7,[(184,-64)])
    opposing=fake_car('opposing',123.4,-58.7,[(114,-58.7)])
    traffic=fake_traffic([exiting,opposing]);traffic.begin_tick()
    assert traffic.distance_budget(exiting,1)==5
    assert traffic.distance_budget(opposing,1)==5


def test_traffic_delays_route_completion_and_parking_maneuver():
    _,_,_,model=build_replay_model(dict(population_size=1,initial_free_count=1106,traffic_enabled=True))
    agent=next(iter(model.agents))
    model.step()
    target=next(s for s in model.facility.spaces if not s.unavailable and not s.accessible and not s.reserved_type)
    node=model.navigation.space_nodes[target.space_id]
    distance=model.navigation.distances((agent.x_m,agent.y_m),[node])[node]
    agent._candidate_times={target.space_id:distance/5+2}
    agent._select_target(SimpleNamespace(chosen_space_id=target.space_id,chosen_utility=3.))
    original=model.traffic.distance_budget
    model.traffic.distance_budget=lambda a,dt:0. if model.clock_s<11 else original(a,dt)
    for _ in range(600):
        model.step()
        if agent.parking_time_s is not None:break
    assert agent.parking_time_s is not None
    assert agent.parking_time_s>=11+distance/5+model.parking_maneuver_s-1e-6


def test_full_lot_includes_unsuccessful_trajectories_and_no_false_claims():
    replay=record_run(dict(population_size=2,initial_free_count=0,traffic_enabled=True))
    assert replay['summary']['parked']==0
    assert replay['summary']['abandoned']==2
    assert all(o['search_s']==600 for o in replay['outcomes'])
    assert all(t['samples'][-1][3]=='abandoned' for t in replay['tracks'])
    assert replay['traffic']['enabled']


def test_scheduled_and_live_supply_changes_have_the_same_outcomes():
    settings=dict(population_size=2, initial_free_count=0, traffic_enabled=True, model='deterministic',information='space')
    session=LiveSimulation(settings)
    sid=next(s.space_id for s in session.facility.spaces if not s.unavailable and not s.accessible and not s.reserved_type)
    session.advance(10)
    session.intervene(dict(action='release',space_ids=[sid]))
    replay=record_run(settings|dict(interventions=[dict(time_s=10,action='release',space_ids=[sid])]))
    while not session.done:result=session.advance(120)
    assert result['summary']==replay['summary']
    for a,o in zip(session.agents,replay['outcomes']):
        assert (a.chosen_space_id,a.search_time_s)==(o['chosen_space'],o['search_s'])
    for track in replay['tracks']:
        for prev,row in zip(track['samples'],track['samples'][1:]):
            if row[3] in ('searching','targeting','exiting'):
                assert math.dist(prev[1:3],row[1:3]) <= 5*(row[0]-prev[0])+1e-6
