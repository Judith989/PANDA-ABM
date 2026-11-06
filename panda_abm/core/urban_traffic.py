"""Through vehicles and assumed intersection controls for optional sensitivity tests.
Through vehicles never claim parking and are excluded from parking denominators.
"""
import math
from types import SimpleNamespace
import numpy as np
from panda_abm.core.states import DriverState

RATES_PER_HOUR={'off':0,'low':30,'medium':120,'high':240}

class ThroughVehicle:
    role='through_traffic'
    def __init__(self,model,identifier,arrival,entry,exit):
        self.model=model;self.driver_id=identifier;self.arrival_time_s=arrival
        self.x_m,self.y_m=entry;self.exit=exit;self.state=DriverState.NOT_ARRIVED
        self.route=[];self.path=[entry];self.traffic_speed_m_s=0.;self.search_time_s=0.
        self.chosen_space_id=None;self.parking_time_s=None;self.search_started_s=None;self.search_ended_s=None
        self.walking_distance_m=None;self.last_candidate_space_ids=[];self.maneuver_remaining_s=0.
        self.attributes=SimpleNamespace(walmart_door_id=None,preferred_exit_id=model.facility.exit_point_ids[model.facility.exit_points.index(exit)],arrival_exit_id=model.facility.entry_point_ids[model.facility.entry_points.index(entry)],vehicle_type='sedan',expected_dwell_duration_s=0)
        self.entered_s=None;self.left_s=None
    def enter(self):
        if self.state!=DriverState.NOT_ARRIVED or self.model.clock_s<self.arrival_time_s:return
        if not self.model.traffic.can_enter(self):return
        self.entered_s=self.model.clock_s;self.state=DriverState.EXITING
        node=self.model.navigation._node(self.exit)
        self.route=self.model.navigation.route((self.x_m,self.y_m),node)
    def step(self):
        if self.state!=DriverState.EXITING:return
        budget=self.model.traffic.distance_budget(self,self.model.integration_seconds);moved=0.
        while self.route:
            p=self.route[0];distance=math.dist((self.x_m,self.y_m),p)
            if distance<1e-9:self.route.pop(0);continue
            if budget<=1e-9:break
            d=min(distance,budget);self.x_m+=(p[0]-self.x_m)*d/distance;self.y_m+=(p[1]-self.y_m)*d/distance
            budget-=d;moved+=d;self.path.append((self.x_m,self.y_m))
            if d>=distance-1e-9:self.route.pop(0)
        self.traffic_speed_m_s=moved/self.model.integration_seconds
        if not self.route:self.state=DriverState.LEFT;self.left_s=self.model.clock_s+self.model.integration_seconds

class ThroughTraffic:
    def __init__(self,model,level,demand_s,seed):
        self.model=model;self.level=level;self.demand_s=demand_s;self.vehicles=[]
        rate=RATES_PER_HOUR[level]
        if not rate:return
        entries=model.facility.entry_points;exits=model.facility.exit_points
        if len(exits)<2:raise ValueError('Through traffic needs at least two distinct boundary exits')
        rng=np.random.default_rng(np.random.SeedSequence([seed,44817]));gap=3600/rate
        for i,t in enumerate(np.arange(0,demand_s,gap)):
            entry=entries[int(rng.integers(len(entries)))];possible=[p for p in exits if math.dist(entry,p)>1]
            if not possible:raise ValueError('Through traffic needs a distinct destination exit')
            exit=possible[int(rng.integers(len(possible)))];arrival=float(round(t/model.integration_seconds)*model.integration_seconds)
            self.vehicles.append(ThroughVehicle(model,f'T{i:04}',arrival,entry,exit))
    def begin_tick(self):
        for vehicle in self.vehicles:vehicle.enter()
    def step(self):
        for vehicle in self.vehicles:
            vehicle.frame_path_index=len(vehicle.path)
            vehicle.step()
    def frame(self):
        return [dict(id=a.driver_id,time_s=self.model.clock_s,x_m=a.x_m,y_m=a.y_m,state=a.state.value,arrival_s=a.arrival_time_s,
            motion=[list(p) for p in a.path[getattr(a,'frame_path_index',0):]],traffic=self.model.traffic.driver_view(a)) for a in self.vehicles if a.state!=DriverState.NOT_ARRIVED]
    def snapshot(self):
        arrived=[a for a in self.vehicles if a.arrival_time_s<self.model.clock_s];finished=[a for a in arrived if a.left_s is not None]
        return dict(level=self.level,assumed_rate_per_hour=RATES_PER_HOUR[self.level],demand_duration_s=self.demand_s,scheduled=len(self.vehicles),arrived=len(arrived),completed=len(finished),
            waiting_entry=sum(a.entered_s is None for a in arrived),active=sum(a.state==DriverState.EXITING for a in arrived),
            traffic_delay_vehicle_s=sum(getattr(a,'traffic_delay_s',0.) for a in self.vehicles),
            entry_wait_vehicle_s=sum(max(0.,(a.entered_s if a.entered_s is not None else self.model.clock_s)-a.arrival_time_s) for a in arrived),
            mean_completed_travel_s=float(np.mean([a.left_s-a.entered_s for a in finished])) if finished else None,
            calibration_status='assumed demand, uniform boundary assignment; not measured')

def road_agents(model):
    return list(model.agents)+getattr(getattr(model,'through_traffic',None),'vehicles',[])

def apply_controls(traffic,active,poses):
    model=traffic.model
    controls=(getattr(getattr(model,'facility',None),'aisle_network',None) or {}).get('controls',[])
    if not controls:return
    nav=model.navigation
    stop_distance=traffic.vehicle_length_m+traffic.minimum_gap_m
    for a in active:
        pos,u=poses[a.driver_id]
        for c in controls:
            point=nav.positions[nav._point_nodes[tuple(round(v,8) for v in model.facility.aisle_network['nodes'][c['node']])]]
            if hasattr(a,'stop_visits') and math.dist(point,pos)>15:a.stop_visits.pop(c['node'],None)
            dx,dy=point[0]-pos[0],point[1]-pos[1];along=dx*u[0]+dy*u[1];across=abs(dx*u[1]-dy*u[0])
            if not a.route or not any(math.dist(point,p)<1e-5 for p in a.route):continue
            if not 1e-6<along<model.search_speed_m_per_s*model.integration_seconds+8 or across>1.5:continue
            wait=False;reason=None
            if c['type']=='signal':
                # A vehicle that crossed the stop line on green must clear the
                # junction when the phase changes, not stop inside the crossing.
                if along<stop_distance-1e-6:continue
                phase=(model.clock_s+c.get('offset_s',0))%c['cycle_s']
                low,high=c['east_west_green'] if abs(u[0])>=abs(u[1]) else c['north_south_green']
                wait=not low<=phase<high;reason='red_signal'
            else:
                if not hasattr(a,'stop_visits'):a.stop_visits={}
                started=a.stop_visits.get(c['node'])
                if along<=stop_distance+.1 and started is None:a.stop_visits[c['node']]=model.clock_s;started=model.clock_s
                wait=started is None or model.clock_s-started<c.get('dwell_s',2);reason='stop_control'
            if wait:
                limit=max(0.,along-stop_distance)
                if limit<traffic.budgets[a.driver_id]:traffic.budgets[a.driver_id]=limit;a.traffic_reason=reason;a.traffic_blocker=c['node']


def through_finished(model):
    return all(a.state==DriverState.LEFT for a in getattr(getattr(model,'through_traffic',None),'vehicles',[]))
