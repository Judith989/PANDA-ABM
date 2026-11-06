from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from planning_study_engine import StudyModel,StudyLog
from panda_abm.environment import generate_synthetic_facility
from panda_abm.behavior.continuous import make_population
from panda_abm.simulation.tcss_conditions import ExperimentalParkingModel

def signature(m):
    return [(a.driver_id,a.chosen_space_id,a.parking_time_s,a.search_time_s,a.state) for a in sorted(m.agents,key=lambda x:x.driver_id)]

def test_measurement_sink_does_not_change_decisions():
    f=generate_synthetic_facility();p=make_population(f,size=8,seed=1000)
    opts=dict(seed=1000,initial_occupancy_rate=.8,information_mode='space',run_id='check',decision_seed_namespace='check')
    a=StudyModel(f,p,**opts);b=StudyModel(f,p,**opts)
    log=StudyLog(b);b.event_logger=log
    for _ in range(1200):a.step();b.step()
    assert signature(a)==signature(b)
    actual={sid:s.occupant_id for sid,s in b.space_states.items() if s.occupied}
    assert log.active==actual and log.exclusive and log.legal
    for sid in f.space_by_id:log.integrate(sid,b.clock_s)
    assert all(0<=v<=b.clock_s for v in log.occupied_seconds.values())

def test_legacy_departure_deque_remains_supported():
    f=generate_synthetic_facility();p=make_population(f,size=2,seed=1000)
    m=ExperimentalParkingModel(f,p,seed=1000,initial_occupancy_rate=.8,background_median_s=1)
    for _ in range(20):m.step()
    assert not m.background_departures
