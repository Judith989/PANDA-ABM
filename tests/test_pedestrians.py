"""Pedestrian display metadata follows core timestamps without moving the vehicle."""
import math
from types import SimpleNamespace
from panda_abm.twin.pedestrians import walking_intervals
from panda_abm.twin.replay import LiveSimulation,record_run
from panda_abm.core.states import DriverState


def test_walking_intervals_use_destination_and_return_timestamps():
    space=SimpleNamespace(x_m=0.,y_m=0.)
    a=SimpleNamespace(parking_time_s=10.,walking_distance_m=14.,chosen_space_id='s',destination_ready_s=20.,return_ready_s=110.,attributes=SimpleNamespace(destination=(14.,0.),walmart_door_id='door_2'),model=SimpleNamespace(facility=SimpleNamespace(space_by_id={'s':space})))
    legs=walking_intervals(a,1.4)
    assert [(p['start_s'],p['end_s']) for p in legs]==[(10.,20.),(100.,110.)]
    assert legs[0]['from_m']==legs[1]['to_m']==[0.,0.]
    assert legs[0]['to_m']==legs[1]['from_m']==[14.,0.]
    assert legs[0]['door']=='door_2'
    a.parking_time_s=None
    assert walking_intervals(a,1.4)==[]


def test_complete_lifecycle_exposes_walking_then_departure_without_vehicle_teleport():
    live=LiveSimulation(dict(population_size=1,occupancy=.4,model='deterministic'))
    a=live.agents[0]
    # Shorten only the test activity to exercise the complete lifecycle quickly.
    from dataclasses import replace
    a.attributes=replace(a.attributes,expected_dwell_duration_s=10)
    parked_location=None;stages=set();last_legs=[]
    for _ in range(10):
        result=live.advance(120)
        for frame in result['frames']:
            row=frame['vehicles'][0];state=row[3];stages.add(state)
            if state in ('parked','walking_to_destination','at_destination','returning_to_vehicle'):
                if parked_location is None:parked_location=row[1:3]
                assert row[1:3]==parked_location
            if frame['walking_intervals']:last_legs=frame['walking_intervals'][a.driver_id]
        if result['complete']:break
    assert result['complete']
    assert {'walking_to_destination','returning_to_vehicle','exiting','left'}<=stages
    assert {leg['phase'] for leg in last_legs}=={'to_door','to_vehicle'}
    assert len(last_legs)>2  # The built-in Walmart environment now follows a network.
    for leg in last_legs:
        duration=leg['end_s']-leg['start_s']
        assert math.isclose(duration,math.dist(leg['from_m'],leg['to_m'])/live.model.walk_speed_m_per_s)
    assert live.model.resource_manager.occupant(a.chosen_space_id) is None


def test_live_and_saved_walking_metadata_agree():
    settings=dict(population_size=2,simulation_duration_s=120,occupancy=.4)
    saved=record_run(settings);live=LiveSimulation(settings);end=live.advance(120)
    assert end['summary']==saved['summary']
    for track in saved['tracks']:
        assert track['walking_intervals']==end['frames'][-1]['walking_intervals'].get(track['id'],[])
