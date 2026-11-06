"""Short downtown route-integrity checks, not publication-effect experiments."""
from pathlib import Path
import sys,json,math,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from panda_abm.twin.environments import downtown_environment
from panda_abm.twin.replay import LiveSimulation
from panda_abm.environment.pedestrian_geometry import ObstacleIndex,bay_polygon
from panda_abm.core.states import DriverState

def main():
    env=downtown_environment();raw=env['config'];obstacles=ObstacleIndex([(b['id'],b['footprint_m']) for b in raw['buildings']]+[(s['id'],bay_polygon(s)) for s in raw['slots']]);results=[]
    for model in ('deterministic','rum','cpt'):
        start=time.perf_counter();live=LiveSimulation(dict(environment=env,population_size=3,arrival_interval_s=60,traffic_enabled=True,simulation_duration_s=300,information='space',model=model,occupancy=.4,seed=1000))
        walking_samples=0;minimum=math.inf
        for _ in range(300):
            live.advance(1)
            for a in live.agents:
                if a.state not in (DriverState.WALKING_TO_DESTINATION,DriverState.RETURNING_TO_VEHICLE) or not hasattr(a,'walk_position'):continue
                walking_samples+=1
                for car in live.agents:
                    if car is not a and car.state in (DriverState.SEARCHING,DriverState.TARGETING,DriverState.EXITING):minimum=min(minimum,math.dist(a.walk_position,(car.x_m,car.y_m)))
        segments=0
        for a in live.agents:
            for leg in getattr(a,'pedestrian_segments',[]):
                assert not obstacles.hits(leg['from_m'],leg['to_m'],ignore=a.chosen_space_id),'Walker intersects another bay or building'
                segments+=1
            if a.parking_time_s is not None:assert math.isfinite(live.facility.walking_distance(live.facility.space_by_id[a.chosen_space_id],a.attributes))
        assert segments>0,'No walking occurred in the diagnostic'
        assert minimum>=3.2-1e-3,'Pedestrian/vehicle clearance failed'
        trace=[dict(driver=a.driver_id,space=a.chosen_space_id,door=a.attributes.walmart_door_id,walk_m=a.walking_distance_m,wait_s=getattr(a,'pedestrian_wait_s',0.),segments=getattr(a,'pedestrian_segments',[])) for a in live.agents]
        (ROOT/f'research/downtown_pedestrians_20261105/{model}_walking_traces.json').write_text(json.dumps(trace,indent=2),encoding='utf8')
        row=dict(model=model,simulated_s=300,parked=sum(a.parking_time_s is not None for a in live.agents),walking_segments_checked=segments,walking_state_samples=walking_samples,minimum_moving_vehicle_centre_distance_m=minimum if math.isfinite(minimum) else None,wall_s=time.perf_counter()-start,checks_passed=True)
        results.append(row);print(json.dumps(row),flush=True)
    report=dict(scope='Native downtown three-driver smoke checks; not field validation or browser visual QA',results=results)
    (ROOT/'research/downtown_pedestrians_20261105/smoke_checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
if __name__=='__main__':main()
