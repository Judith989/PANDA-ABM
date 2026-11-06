"""Every recorded movement leg follows a graph edge; capture preserves corners."""
import math
from types import SimpleNamespace
import numpy as np
import pytest
from panda_abm.twin.replay import record_run,build_replay_model,step_motion
from panda_abm.core.agent import DriverAgent
from panda_abm.core.states import DriverState
from panda_abm.core.traffic import AisleTraffic
from panda_abm.twin.environments import satellite_environment


def test_one_tick_with_a_turn_keeps_the_corner_in_motion_data():
    car=SimpleNamespace(model=SimpleNamespace(search_speed_m_per_s=5.,traffic=None),x_m=0.,y_m=0.,route=[(2.,0.),(2.,4.)],path=[(0.,0.)],search_distance_m=0.,state=DriverState.SEARCHING,log=lambda *a,**k:None)
    DriverAgent._advance_route(car,1.)
    assert step_motion(car,1)==[[0.,0.],[2.,0.],[2.,3.]]
    assert math.isclose(car.search_distance_m,5.)


@pytest.mark.parametrize('variant',['original','satellite'])
def test_recorded_motion_legs_remain_on_network_edges(variant):
    settings=dict(population_size=6,arrival_interval_s=1,simulation_duration_s=120,traffic_enabled=True,information='space',occupancy=.95)
    if variant=='satellite':settings['environment']=satellite_environment()
    result=record_run(settings);edges=np.asarray(result['aisle_edges']);v=edges[:,1]-edges[:,0];l2=(v*v).sum(1)
    def contains(p):
        p=np.asarray(p);fraction=((p-edges[:,0])*v).sum(1)/l2
        feet=edges[:,0]+np.clip(fraction,0,1)[:,None]*v
        return np.linalg.norm(feet-p,axis=1)<1e-5
    legs=0
    for track in result['tracks']:
        for sample in track['samples']:
            motion=sample[6]
            if motion:
                assert np.allclose(motion[-1],sample[1:3])
                for a,b in zip(motion,motion[1:]):
                    assert np.any(contains(a)&contains(b)),(a,b)
                    legs+=1
    assert legs>0


def test_congestion_cause_seconds_follow_physical_time_not_tick_count():
    a=SimpleNamespace(driver_id='a',x_m=0.,y_m=0.,route=[(100.,0.)],state=DriverState.SEARCHING,traffic_wait_s=0.,traffic_speed_m_s=0.,maneuver_remaining_s=0.)
    b=SimpleNamespace(**vars(a));b.driver_id='b';b.x_m=6.
    model=SimpleNamespace(agents=[a,b],search_speed_m_per_s=5.,integration_seconds=.5,perception_radius_m=60.,clock_s=0.)
    traffic=AisleTraffic(model);traffic.aisle_at=lambda p:'aisle'
    for i in range(14):model.clock_s=i*.5;traffic.begin_tick();traffic.end_tick()
    model.clock_s=7.;b.state=DriverState.LEFT;traffic.begin_tick();traffic.end_tick();model.clock_s=7.5
    episode=traffic.snapshot()['episodes'][0]
    assert episode['duration_s']==7.
    assert episode['cause_active_seconds']=={'following_vehicle':7.}
    assert episode['cause_vehicle_seconds']=={'following_vehicle':7.}
    assert episode['queued_vehicle_delay_s']==7.
    assert not episode['multi_vehicle_queue']
