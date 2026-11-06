"""Jam classification requires continuously two or more constrained vehicles."""
from types import SimpleNamespace
import pytest
from panda_abm.core.traffic import AisleTraffic
from panda_abm.core.states import DriverState


def fixture(dt):
    cars=[SimpleNamespace(driver_id=f'D{i}',state=DriverState.SEARCHING,route=[(100,0)],x_m=i*7.,y_m=0.,traffic_reason='following_vehicle',traffic_speed_m_s=0.) for i in range(2)]
    model=SimpleNamespace(agents=cars[:1],integration_seconds=dt,search_speed_m_per_s=5.,clock_s=0.)
    traffic=AisleTraffic(model);traffic.aisle_at=lambda p:'A'
    def tick(count):
        model.agents=cars[:count];traffic.end_tick();model.clock_s+=dt
    return traffic,tick


@pytest.mark.parametrize('dt',[1.,.5,.25])
def test_single_vehicle_period_does_not_extend_multi_vehicle_jam(dt):
    traffic,tick=fixture(dt)
    for _ in range(round(6/dt)):tick(1)
    assert traffic.snapshot()['jam_episodes']==[]
    for _ in range(round(7/dt)):tick(2)
    ongoing=traffic.snapshot()['jam_episodes'][0]
    assert ongoing['start_s']==6 and ongoing['end_s'] is None and ongoing['duration_s']==7
    for _ in range(round(4/dt)):tick(1)
    jam=traffic.snapshot()['jam_episodes'][0]
    assert jam['end_s']==13 and jam['duration_s']==7 and jam['peak_queue']==2
    assert jam['cause_active_seconds']=={'following_vehicle':7}
    assert jam['cause_vehicle_seconds']=={'following_vehicle':14}
    assert traffic.snapshot()['episodes'][0]['duration_s']==17


def test_two_short_queues_separated_by_one_vehicle_are_not_one_jam():
    traffic,tick=fixture(1)
    for n in [2,2,2,1,2,2,2,1]:tick(n)
    assert traffic.snapshot()['jam_episodes']==[]
    assert len(traffic.snapshot()['episodes'])==1
