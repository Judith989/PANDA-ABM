"""Headless study adapter: unchanged decisions/movement, bounded observation and full outcomes."""
from pathlib import Path
from dataclasses import replace,asdict
from collections import Counter,defaultdict,deque
from functools import lru_cache
import math,json,hashlib,time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from panda_abm.environment import load_facility_from_lot_config
from panda_abm.twin.environments import downtown_environment,satellite_environment,synthetic_environment,traffic_segment_labels
from panda_abm.twin.urban_scenarios import apply_policy,apply_visit_profile,ResidualBackground,urban_outcomes
from panda_abm.behavior.continuous import make_population,PopulationPriors,PREFERENCE_MEANS
from panda_abm.behavior.decision.cpt import LinearProspectDecisionModel
from panda_abm.simulation.tcss_conditions import SimpleSearchDecisionModel,ExperimentalParkingModel,ExperimentalAisleInformation
from panda_abm.core.model import ParkingModel
from panda_abm.core.urban_traffic import ThroughTraffic,road_agents
from panda_abm.core.states import DriverState,SpaceType
from panda_abm.twin.time_window import window_status

MODELS=('deterministic','rum','cpt','linear_cpt','simple')
INFOS=('unaided','aisle','space')

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

@lru_cache(maxsize=20)
def facility_for(name,policy='configured',accessible='baseline',cycle=96):
    if name=='walmart_original':f=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    elif name=='walmart_satellite':f=__import__('panda_abm.twin.environments',fromlist=['facility_from_environment']).facility_from_environment(satellite_environment())
    elif name=='downtown':f=__import__('panda_abm.twin.environments',fromlist=['facility_from_environment']).facility_from_environment(downtown_environment())
    elif name=='synthetic':f=__import__('panda_abm.twin.environments',fromlist=['facility_from_environment']).facility_from_environment(synthetic_environment())
    else:raise ValueError(name)
    f=apply_policy(f,policy)
    if cycle!=96:
        import copy
        net=copy.deepcopy(f.aisle_network)
        for c in net.get('controls',[]):
            if c['type']=='signal':c.update(cycle_s=cycle,east_west_green=[0,cycle/2-6],north_south_green=[cycle/2,cycle-6])
        f=replace(f,aisle_network=net)
    if accessible!='baseline':
        candidates=[s for s in f.spaces if not s.unavailable and not s.accessible and not s.reserved_type and (f.walking_network is None or any(math.isfinite(f.walking_network.distance(s.space_id,d)) for d in f.walmart_door_ids))]
        ids=choose_spaces(f,candidates,10,'door' if accessible=='near_doors' else 'spread')
        f=replace(f,spaces=tuple(replace(s,accessible=True,space_type=SpaceType.ACCESSIBLE) if s.space_id in ids else s for s in f.spaces))
    return f

def choose_spaces(f,spaces,count,kind):
    count=min(count,len(spaces));spaces=list(spaces)
    if kind=='door':return [s.space_id for s in sorted(spaces,key=lambda s:(min(math.dist((s.x_m,s.y_m),d) for d in f.walmart_doors),s.space_id))[:count]]
    if kind=='exit':return [s.space_id for s in sorted(spaces,key=lambda s:(min(math.dist((s.x_m,s.y_m),d) for d in f.exit_points),s.space_id))[:count]]
    ordered=sorted(spaces,key=lambda s:(s.x_m,s.y_m,s.space_id))
    return [ordered[i].space_id for i in np.linspace(0,len(ordered)-1,count,dtype=int)] if count else []

class StudyModel(ParkingModel):
    information_mode_for=ExperimentalParkingModel.information_mode_for
    perceive=ExperimentalParkingModel.perceive
    availability_snapshot=ExperimentalParkingModel.availability_snapshot
    remote_snapshot=ExperimentalParkingModel.remote_snapshot
    def __init__(self,*args,adoption=1.,delay=0.,**kwargs):
        self.report_delay_s=delay;self.adoption_rate=adoption
        super().__init__(*args,**kwargs)
        rng=np.random.default_rng(np.random.SeedSequence([self.seed,80421]));self.adoption_draws={a.driver_id:float(rng.random()) for a in sorted(self.agents,key=lambda a:a.driver_id)}
        self.adopters={k for k,v in self.adoption_draws.items() if v<adoption}
        self.aisle_information=ExperimentalAisleInformation(self)
        self._snapshots=deque([(0.,self.availability_snapshot())])
    def before_physical_tick(self):
        if self.report_delay_s and self.clock_s>self._snapshots[-1][0]:
            self._snapshots.append((self.clock_s,self.availability_snapshot()))
            target=self.clock_s-self.report_delay_s
            while len(self._snapshots)>1 and self._snapshots[1][0]<=target+1e-9:self._snapshots.popleft()

class StudyLog:
    """Measurement-only sink; retains every claim and selected representative trajectories."""
    def __init__(self,model,trace=False):
        self.model=model;self.trace=trace;self.counts=Counter();self.by_driver=defaultdict(Counter);self.claims=[];self.trajectories=[];self.choices=[]
        self.active={sid:v.occupant_id for sid,v in model.space_states.items() if v.occupied};self.exclusive=True;self.legal=True
        self.last_change=defaultdict(float);self.occupied_seconds=Counter();self.closed_seconds=Counter();self.open_occupied_seconds=Counter();self.closed={sid for sid,v in model.space_states.items() if v.unavailable and not model.facility.space_by_id[sid].unavailable}
    def integrate(self,sid,time_s):
        duration=time_s-self.last_change[sid]
        if sid in self.active:self.occupied_seconds[sid]+=duration
        if sid in self.closed:self.closed_seconds[sid]+=duration
        if sid in self.active and sid not in self.closed:self.open_occupied_seconds[sid]+=duration
        self.last_change[sid]=time_s
    def log(self,event_type,time_s,agent=None,space=None,space_id=None,module_id=None,utility=None,probability=None,details=None):
        self.counts[event_type]+=1
        if agent:self.by_driver[agent.driver_id][event_type]+=1
        sid=space.space_id if space is not None else space_id
        if sid and event_type in ('SpaceClaimSucceeded','SpaceReleased','SupplyIntervention'):self.integrate(sid,time_s)
        if event_type=='SpaceClaimSucceeded':
            self.exclusive &= sid not in self.active;self.active[sid]=agent.driver_id
            self.claims.append(dict(time_s=time_s,space=sid,driver=agent.driver_id,module=space.module_id))
            self.legal &= space.is_compatible_with_vehicle(agent.attributes.vehicle_type) and (not space.accessible or agent.attributes.accessibility_eligibility) and (not space.reserved_type or agent.attributes.permit_type==(space.permit_requirement or space.reserved_type))
        elif event_type=='SpaceReleased':self.exclusive &= self.active.pop(sid,None)==agent.driver_id
        elif event_type=='SupplyIntervention':
            action=(details or {}).get('action')
            if action=='release':self.active.pop(sid,None)
            if action=='close':self.closed.add(sid)
            if action=='open':self.closed.discard(sid)
        if self.trace and event_type in ('VehicleSearchingAisle','VehicleMovingToTarget','AgentExited','TargetSelected','LostSpace') and agent:
            self.trajectories.append([time_s,agent.driver_id,agent.x_m,agent.y_m,agent.state.value,sid])
        if event_type=='TargetSelected':self.choices.append([time_s,agent.driver_id,sid,(details or {}).get('information_source')])

def simulate(job):
    start=time.perf_counter();f=facility_for(job['environment'],job.get('policy','configured'),job.get('accessible','baseline'),job.get('cycle',96))
    seed=job['seed'];gap=job.get('gap',20);n=math.ceil(job['demand_s']/gap) if job.get('demand_s') else job.get('population',80)
    priors=PopulationPriors(arrival_interval_s=gap)
    pop=make_population(f,size=n,seed=seed,priors=priors)
    pop=apply_visit_profile(pop,f,job.get('visit','baseline'),seed)
    if job.get('population_control')=='mean_preferences':pop=replace(pop,drivers=tuple(replace(d,behavioral_parameters=replace(d.behavioral_parameters,**PREFERENCE_MEANS)) for d in pop.drivers))
    if job.get('population_control')=='central_cpt':
        from panda_abm.behavior.cpt_parameters import CPTParameters
        pop=replace(pop,drivers=tuple(replace(d,cpt_parameters=CPTParameters(alpha=.88,beta=.88,lambda_loss=2.25,gamma=.61,gamma_loss=.69)) for d in pop.drivers))
    usable=[s for s in f.spaces if not s.unavailable];planning_pool=[s for s in usable if f.walking_network is None or any(math.isfinite(f.walking_network.distance(s.space_id,d)) for d in f.walmart_door_ids)];strategy=job.get('supply','baseline');closed=[];interventions=[]
    if strategy.startswith('close_'):closed=choose_spaces(f,planning_pool,20,strategy[6:])
    if strategy.startswith('pool_'):
        closed=choose_spaces(f,planning_pool,60,'spread')
        if strategy!='pool_closed':
            pool=[f.space_by_id[s] for s in closed];opening=choose_spaces(f,pool,20,strategy[5:]);interventions=[dict(time_s=900,action='open',space_ids=opening)]
    name=job['model'];policy=LinearProspectDecisionModel() if name=='linear_cpt' else SimpleSearchDecisionModel() if name=='simple' else name
    dt=job.get('dt',1.)
    m=StudyModel(f,pop,policy,seed=seed,initial_occupancy_rate=job.get('occupancy',.95),initial_free_count=job.get('free_count'),closed_space_ids=closed,interventions=interventions,
        information_mode=job['information'],traffic_enabled=job.get('traffic',True),adoption=job.get('adoption',1.),delay=job.get('delay',0.),
        run_id=f'planning_{seed}',scenario_id='planning',replication_id=f'seed_{seed}',decision_seed_namespace='planning_matched',step_seconds=dt,integration_seconds=dt)
    if job.get('background')=='residual':m.background_departures=ResidualBackground(m,job.get('visit','baseline'),seed)
    m.through_traffic=ThroughTraffic(m,job.get('through','off'),job.get('demand_s',3600),seed)
    trace=seed==1000;log=StudyLog(m,trace);m.event_logger=log
    initial=sorted(sid for sid,v in m.space_states.items() if v.occupied)
    attrs=[asdict(d.attributes) for d in pop.drivers];preferences=[d.behavioral_parameters.as_dict() for d in pop.drivers]
    initialization=time.perf_counter()-start
    horizon=job.get('horizon',7200);timeline=[];occupancy_integral=defaultdict(float);closed_integral=defaultdict(float);queue_integral=defaultdict(float)
    while m.clock_s<horizon:
        m.step()
        # Integrate exact piecewise-constant occupancy using claim/release times below; timeline is descriptive.
        if abs(m.clock_s%30)<1e-7:
            from panda_abm.core.interventions import supply_snapshot
            supply=supply_snapshot(m);q=sum(getattr(m.traffic,'queues',{}).values()) if m.traffic else None
            timeline.append(dict(time_s=m.clock_s,occupied=supply['occupied'],open_spaces=supply['usable_inventory']-supply['closed'],free=supply['free'],closed=supply['closed'],queued=q,parked=sum(a.parking_time_s is not None for a in m.agents),searching=sum(a.state in (DriverState.SEARCHING,DriverState.TARGETING) for a in m.agents),through_active=m.through_traffic.snapshot()['active']))
    outcomes=[];urban={r['driver']:r for r in urban_outcomes(m)};agents=sorted(m.agents,key=lambda a:a.driver_id)
    for a in agents:
        status=window_status(a,m.clock_s);parked=a.parking_time_s is not None;s=f.space_by_id.get(a.chosen_space_id) if parked else None
        entry=max(0.,(a.search_started_s if a.search_started_s is not None else m.clock_s)-a.arrival_time_s) if status['observed_arrival'] else None
        reached=hasattr(a,'dwell_end_s');door_time=a.dwell_end_s-a.attributes.expected_dwell_duration_s if reached else None
        distance=sum(math.dist(p,q) for p,q in zip(a.path,a.path[1:]))
        assert not parked or math.isfinite(a.walking_distance_m)
        if a.search_started_s is not None and a.search_ended_s is not None:assert abs(a.search_time_s-(a.search_ended_s-a.search_started_s))<1e-6
        outcomes.append(dict(driver=a.driver_id,**status,chosen_space=s.space_id if s else None,module=s.module_id if s else None,aisle=m.navigation.space_aisle[s.space_id] if s else None,
            walk_m=a.walking_distance_m if parked else None,exit_m=s.exit_distance(a.attributes.preferred_exit_id) if s else None,entry_wait_s=entry,arrival_to_resolution_s=entry+status['search_s'] if entry is not None else None,
            door_reached=reached,time_to_door_s=door_time-a.arrival_time_s if reached else None,walk_elapsed_s=door_time-a.parking_time_s if reached else None,
            traffic_delay_s=getattr(a,'traffic_delay_s',0.),vehicle_distance_m=distance,search_distance_m=a.search_distance_m,lost_claims=a.lost_space_events,rejections=a.rejected_spaces,
            target_selections=log.by_driver[a.driver_id]['TargetSelected'],candidate_evaluations=a.candidate_evaluations,information_access=m.information_mode_for(a),adoption_draw=m.adoption_draws[a.driver_id],
            walking_limited=a.attributes.max_walking_distance_m is not None,accessible_eligible=a.attributes.accessibility_eligibility,max_walk_m=a.attributes.max_walking_distance_m,
            destination=a.attributes.walmart_door_id,intended_exit=a.attributes.preferred_exit_id,activity_s=a.attributes.expected_dwell_duration_s,
            beta_walk=a.parameters.beta_walk,beta_search=a.parameters.beta_search,loss_aversion=a.spec.cpt_parameters.lambda_loss if a.spec.cpt_parameters else None,
            completed_trip=a.state in (DriverState.LEFT,DriverState.ABANDONED),**{k:v for k,v in urban[a.driver_id].items() if k not in ('driver','destination')}))
    for space in usable:log.integrate(space.space_id,horizon)
    actual={sid:v.occupant_id for sid,v in m.space_states.items() if v.occupied};assert actual==log.active and log.exclusive and log.legal
    cohort=[r for r in outcomes if r['observed_arrival']];parked=[r for r in cohort if r['success']];doors=[r for r in cohort if r['door_reached']]
    mean=lambda rows,k:float(np.mean([r[k] for r in rows])) if rows else None
    traffic=m.traffic.snapshot() if m.traffic else dict(enabled=False);jams=traffic.get('jam_episodes',[])
    intervals=sorted((e['start_s'],e['end_s'] if e['end_s'] is not None else horizon) for e in jams);merged=[]
    for a,b in intervals:
        if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    summary=dict(occupied_space_seconds=sum(log.occupied_seconds.values()),closed_space_seconds=sum(log.closed_seconds.values()),occupancy_fixed_pct=100*sum(log.occupied_seconds.values())/(horizon*len(usable)),open_supply_utilization_pct=100*sum(log.open_occupied_seconds.values())/(horizon*len(usable)-sum(log.closed_seconds.values())) if horizon*len(usable)>sum(log.closed_seconds.values()) else None,arrivals=len(cohort),parked=len(parked),success_pct=100*len(parked)/len(cohort) if cohort else None,search_s=mean(cohort,'search_s'),entry_wait_s=mean(cohort,'entry_wait_s'),arrival_to_resolution_s=mean(cohort,'arrival_to_resolution_s'),walk_m=mean(parked,'walk_m'),exit_m=mean(parked,'exit_m'),failed_claims=mean(cohort,'lost_claims'),traffic_delay_s=mean(cohort,'traffic_delay_s'),vehicle_distance_m=mean(cohort,'vehicle_distance_m'),time_to_door_s=mean(doors,'time_to_door_s'),pedestrian_wait_s=mean(parked,'pedestrian_wait_s'),
        abandoned=sum(r['search_status']=='abandoned' for r in cohort),unfinished_searches=sum(r['right_censored'] for r in cohort),unfinished_trips=sum(not r['completed_trip'] for r in cohort),jam_count=len(jams) if m.traffic else None,jam_clock_s=sum(b-a for a,b in merged) if m.traffic else None,peak_queue=max(traffic.get('aisle_peak_queue',{}).values(),default=0) if m.traffic else None,ongoing_jams=sum(e['end_s'] is None for e in jams),total_traffic_delay_s=traffic.get('cumulative_delay_s'),observed_limit_exceedances=sum(r['observed_time_limit_exceeded'] for r in parked))
    counts=Counter(r['space'] for r in log.claims)
    result=dict(job=job,summary=summary,outcomes=outcomes,traffic=traffic,through=m.through_traffic.snapshot(),space_use=dict(counts),space_occupied_seconds=dict(log.occupied_seconds),space_closed_seconds=dict(log.closed_seconds),claims=log.claims,choices=log.choices,timeline=timeline,
        invariants=dict(exclusive=log.exclusive,legal=log.legal,occupancy_reconciled=actual==log.active,finite=True),population_sha256=digest(pop.as_dict()),attributes_sha256=digest(attrs),preferences_sha256=digest(preferences),initial_occupancy_sha256=digest(initial),initial_occupied=initial,closed_ids=closed,interventions=m.intervention_log,
        walking_measure='network' if f.pedestrian_network else 'straight_line',nominal_usable=len(usable),segment_labels=traffic_segment_labels(f,m.navigation),initialize_wall_s=initialization,wall_s=time.perf_counter()-start,event_counts=dict(log.counts))
    if job.get('stage')=='core' and name=='deterministic' and job['information']=='unaided' and job.get('occupancy')==.4:
        # Outcome-independent profile fitting must use the actual frozen drivers,
        # including those who never obtain a space, not an earlier population.
        result['population']=pop.as_dict()
    if trace:result.update(trajectories=log.trajectories,walking_traces={a.driver_id:getattr(a,'pedestrian_segments',[]) for a in agents if getattr(a,'pedestrian_segments',[])})
    return result
