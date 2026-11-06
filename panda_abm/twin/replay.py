"""Record the existing model for a Cesium replay without changing its decisions."""
from panda_abm.twin.environments import traffic_segment_labels
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import numpy as np
from panda_abm.behavior.continuous import make_population,PopulationPriors
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.environment import load_facility_from_lot_config
from panda_abm.twin.time_window import window_status, window_summary
from panda_abm.twin.pedestrians import walking_intervals
from panda_abm.core.urban_traffic import road_agents,through_finished

ROOT=Path(__file__).resolve().parents[2]
DEFAULTS=dict(seed=1000,population_size=80,occupancy=.4,model='cpt',information='unaided',arrival_interval_s=20)
DEFAULTS.update(initial_free_count=None, initial_free_space_ids=None, closed_space_ids=[], interventions=[], traffic_enabled=False)
DEFAULTS['initial_occupied_space_ids']=None
DEFAULTS['simulation_duration_s']=None
DEFAULTS['environment']=None
DEFAULTS.update(background_departures='static',visit_profile='baseline',parking_policy='configured',through_traffic='off',through_demand_s=3600,demand_duration_s=None)


def step_motion(agent, previous_length):
    """Actual within-tick polyline, including graph corners (display data only)."""
    if len(agent.path)<=previous_length:return []
    return [list(p) for p in agent.path[max(0,previous_length-1):]]


def validate_intervention(event):
    if not isinstance(event, dict) or set(event)-{'time_s','action','space_ids'}:
        raise ValueError('Invalid supply intervention')
    if event.get('action') not in ('close','open','release'):
        raise ValueError('Choose close, open, or release')
    ids=event.get('space_ids')
    if not isinstance(ids,list) or not ids or len(ids)>2000 or any(not isinstance(s,str) for s in ids) or len(set(ids))!=len(ids):
        raise ValueError('Choose distinct space IDs')
    t=event.get('time_s',0)
    if type(t) is not int or not 0<=t<=86400:raise ValueError('Intervention time must be whole seconds within one day')
    return dict(time_s=t,action=event['action'],space_ids=list(ids))


def validate_settings(settings):
    if not isinstance(settings,dict) or set(settings)-set(DEFAULTS):raise ValueError('Unknown scenario settings')
    s=DEFAULTS|settings
    for key,low,high in [('seed',0,2147483647),('population_size',1,1200),('arrival_interval_s',1,3600)]:
        if type(s[key]) is not int or not low<=s[key]<=high:raise ValueError(f'{key} must be an integer in [{low}, {high}]')
    if type(s['occupancy']) not in (int,float) or not np.isfinite(s['occupancy']) or not 0<=s['occupancy']<=1:raise ValueError('occupancy must be in [0, 1]')
    if s['model'] not in ('deterministic','rum','cpt'):raise ValueError('Unknown decision model')
    if s['information'] not in ('unaided','aisle','space'):raise ValueError('Unknown information condition')
    if type(s['traffic_enabled']) is not bool:raise ValueError('traffic_enabled must be true or false')
    duration=s['simulation_duration_s']
    if duration is not None and (type(duration) is not int or not 60<=duration<=21600):
        raise ValueError('Simulation duration must be 60–21600 whole seconds, or null for full trips')
    if s['background_departures'] not in ('static','residual'):raise ValueError('Unknown background departure model')
    if s['visit_profile'] not in ('baseline','short','near_limit','long','mixed'):raise ValueError('Unknown visit profile')
    if s['parking_policy'] not in ('configured','unrestricted','street_2h'):raise ValueError('Unknown parking policy')
    if s['through_traffic'] not in ('off','low','medium','high'):raise ValueError('Unknown through-traffic level')
    if s['through_traffic']!='off' and not s['traffic_enabled']:raise ValueError('Through traffic requires traffic interactions')
    if type(s['through_demand_s']) is not int or not 60<=s['through_demand_s']<=21600:raise ValueError('Through demand must last 60–21600 s')
    demand=s['demand_duration_s']
    if demand is not None:
        if type(demand) is not int or not 60<=demand<=21600:raise ValueError('Parking demand must last 60–21600 s')
        s['population_size']=int(np.ceil(demand/s['arrival_interval_s']))
        if s['population_size']>1200:raise ValueError('Demand window exceeds 1,200 parking drivers; increase arrival interval')
    capacity=1106
    if s['environment'] is not None:
        from panda_abm.twin.environments import validate_environment
        s['environment']=validate_environment(s['environment'])
        capacity=s['environment']['validation']['usable_spaces']
        ped=s['environment']['config'].get('pedestrian_network')
        if ped and any(e['kind']=='crossing' for e in ped['edges']) and not s['traffic_enabled']:raise ValueError('Enable traffic interactions to simulate safe pedestrian crossings')
    count=s['initial_free_count']
    if count is not None and (type(count) is not int or not 0<=count<=capacity):raise ValueError('Free count must be 0–1106')
    for key in ('initial_free_space_ids','initial_occupied_space_ids','closed_space_ids'):
        ids=s[key]
        if ids is not None and (not isinstance(ids,list) or len(ids)>capacity or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids)):
            raise ValueError(f'{key} must contain distinct space IDs')
    if sum(x is not None for x in (count,s['initial_free_space_ids'],s['initial_occupied_space_ids']))>1:raise ValueError('Choose one initial supply mode')
    if set(s['initial_free_space_ids'] or []) & set(s['closed_space_ids'] or []):raise ValueError('Selected free spaces cannot also be closed')
    if not isinstance(s['interventions'],list) or len(s['interventions'])>200:raise ValueError('Too many interventions')
    s['interventions']=[validate_intervention(e) for e in s['interventions']]
    # The percentage control is inactive in exact-supply modes. Canonicalize it
    # before it enters run IDs and decision RNG namespaces.
    if count is not None:s['occupancy']=1-count/capacity
    elif s['initial_free_space_ids'] is not None:s['occupancy']=1-len(s['initial_free_space_ids'])/capacity
    elif s['initial_occupied_space_ids'] is not None:s['occupancy']=len(s['initial_occupied_space_ids'])/capacity
    return s


def build_replay_model(settings):
    """Use one construction path for saved recordings and live sessions."""
    settings=validate_settings(settings)
    if settings['environment'] and settings['environment']['config']['meta'].get('review_required'):
        raise ValueError('This environment is preview-only pending layout and rule review')
    seed=settings['seed'];occ=settings['occupancy']
    if settings['environment'] is None:
        facility=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    else:
        from panda_abm.twin.environments import facility_from_environment
        facility=facility_from_environment(settings['environment'])
    from panda_abm.twin.urban_scenarios import apply_policy, apply_visit_profile
    facility=apply_policy(facility,settings['parking_policy'])
    population=make_population(facility,size=settings['population_size'],seed=seed,
                               priors=PopulationPriors(arrival_interval_s=float(settings['arrival_interval_s'])))
    population=apply_visit_profile(population,facility,settings['visit_profile'],seed)
    # Match the experiment's RNG namespace and run ID across model/information arms.
    model=ParkingModel(facility,population,settings['model'],seed=seed,initial_occupancy_rate=occ,
                       information_mode=settings['information'],scenario_id=f'occupancy_{occ}',
                       run_id=f'information_{seed}_{occ}',replication_id=f'seed_{seed}',
                       decision_seed_namespace='information_matched',step_seconds=1,
                       initial_free_count=settings['initial_free_count'],initial_free_space_ids=settings['initial_free_space_ids'],
                       closed_space_ids=settings['closed_space_ids'],interventions=settings['interventions'],
                       traffic_enabled=settings['traffic_enabled'],initial_occupied_space_ids=settings['initial_occupied_space_ids'])
    from panda_abm.core.urban_traffic import ThroughTraffic
    model.through_traffic=ThroughTraffic(model,settings['through_traffic'],settings['through_demand_s'],seed)
    if settings['background_departures']=='residual':
        from panda_abm.twin.urban_scenarios import ResidualBackground
        model.background_departures=ResidualBackground(model,settings['visit_profile'],seed)
    for event in settings['interventions']:
        for sid in event['space_ids']:
            if sid not in facility.space_by_id or facility.space_by_id[sid].unavailable:
                raise ValueError(f'Intervention space is not usable: {sid}')
    # Keep construction arguments explicit so archived defaults retain their RNG.
    return settings,facility,population,model


def record_run(settings,progress=None,verify_archive=False):
    settings,facility,population,model=build_replay_model(settings)
    if settings['environment'] and settings['environment']['config']['meta'].get('review_required'):
        raise ValueError('This environment is preview-only pending layout and rule review')
    seed=settings['seed'];occ=settings['occupancy']
    agents=sorted(model.agents,key=lambda a:a.driver_id)
    horizon=settings['simulation_duration_s']
    visual_agents=sorted(road_agents(model),key=lambda a:a.driver_id)
    tracks=[dict(id=a.driver_id,door=a.attributes.walmart_door_id,intended_exit=a.attributes.preferred_exit_id,
                 arrival_exit=a.attributes.arrival_exit_id,arrival_s=a.arrival_time_s,samples=[],observations=[],role=getattr(a,'role','parking')) for a in visual_agents]
    occupied={sid for sid,s in model.space_states.items() if s.occupied}
    initial=sorted(occupied);changes=[];system=[];telemetry=[]
    static_spaces=facility.space_by_id
    initial_closed=sorted(sid for sid,s in model.space_states.items() if s.unavailable and not static_spaces[sid].unavailable)
    path_lengths={a.driver_id:len(a.path) for a in visual_agents}
    def capture():
        nonlocal occupied
        for a,track in zip(visual_agents,tracks):
            row=[a.x_m,a.y_m,a.state.value,a.chosen_space_id,a.search_time_s]
            if horizon is not None:row[-1]=window_status(a,model.clock_s)['search_s']
            motion=step_motion(a,path_lengths[a.driver_id]);path_lengths[a.driver_id]=len(a.path)
            if not track['samples'] or track['samples'][-1][1:6]!=row:
                track['samples'].append([model.clock_s,*row,motion])
            track['walking_intervals']=walking_intervals(a,model.walk_speed_m_per_s,static_spaces)
            observed=getattr(a,'last_observation_s',None)
            if observed is not None and (not track['observations'] or track['observations'][-1]['time_s']!=observed):
                track['observations'].append(dict(time_s=observed,visible=a.last_visible_space_ids,
                    free=a.last_visible_free_space_ids,candidates=list(a.last_candidate_space_ids)))
        now={sid for sid,s in model.space_states.items() if s.occupied}
        if now!=occupied:
            changes.append([model.clock_s,sorted(now-occupied),sorted(occupied-now)])
        occupied=now
        from panda_abm.core.interventions import supply_snapshot
        telemetry.append(dict(time_s=model.clock_s,supply=supply_snapshot(model),through_traffic=model.through_traffic.snapshot(),
            drivers={a.driver_id:model.traffic.driver_view(a) for a in visual_agents if getattr(a,'role',None)!='through_traffic' or a.state==DriverState.EXITING} if model.traffic else {},
            traffic=model.traffic.snapshot() if model.traffic else dict(enabled=False)))
        if model.clock_s%10==0 or (horizon is not None and model.clock_s==horizon):
            system.append([model.clock_s,len(now),sum(a.state in (DriverState.SEARCHING,DriverState.TARGETING) for a in agents),
                           sum(a.parking_time_s is not None for a in agents),sum(a.search_ended_s is not None and a.parking_time_s is None for a in agents)])
    capture()
    route_bound=sum(e['weight'] for _,_,e in model.navigation.graph.edges(data=True))/model.search_speed_m_per_s
    bound=max(a.arrival_time_s+a.attributes.expected_dwell_duration_s for a in agents)+600+route_bound+2000
    bound=max(bound,settings['through_demand_s']+route_bound+2000 if settings['through_traffic']!='off' else bound)
    from panda_abm.core.pedestrian_movement import completion_padding
    bound+=completion_padding(model)
    while (model.clock_s<horizon if horizon is not None else model.clock_s<=bound):
        model.step();capture()
        if progress and model.clock_s%100==0:progress(model.clock_s)
        if horizon is None and all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in agents) and through_finished(model):break
    else:
        if horizon is None:raise RuntimeError('Simulation did not finish within its time bound')
    outcomes=[];signature=[]
    for a in agents:
        parked=a.parking_time_s is not None
        space=facility.space_by_id[a.chosen_space_id] if parked else None
        outcome=dict(driver=a.driver_id,success=parked,search_s=a.search_time_s,search_distance_m=a.search_distance_m,
                     walk_m=a.walking_distance_m if parked else None,chosen_space=a.chosen_space_id if parked else None,
                     lost_claims=a.lost_space_events,parking_time_s=a.parking_time_s)
        signature.append(outcome)
        outcomes.append(outcome|dict(door=a.attributes.walmart_door_id,intended_exit=a.attributes.preferred_exit_id,
                                     exit_distance_m=space.exit_distance(a.attributes.preferred_exit_id) if space else None))
        if model.traffic:
            entry=max(0.,(a.search_started_s if a.search_started_s is not None else model.clock_s)-a.arrival_time_s)
            outcomes[-1].update(entry_delay_s=entry,traffic_delay_s=getattr(a,'traffic_delay_s',0.),
                                arrival_to_search_end_s=entry+a.search_time_s)
        if horizon is not None:
            outcomes[-1].update(window_status(a,model.clock_s))
            if model.traffic:outcomes[-1]['arrival_to_search_end_s']=outcomes[-1]['entry_delay_s']+outcomes[-1]['search_s']
    outcome_hash=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    verification=None
    if verify_archive:
        if settings['simulation_duration_s'] is not None or settings['environment'] is not None:raise ValueError('Archive verification requires full Walmart trips')
        archive=ROOT/'results/tcss_first_batch_20261028'
        if not archive.exists():archive=ROOT/'results/parking_information_20261028'
        plan=json.loads((archive/'design.json').read_text())
        source_differences=[]
        for relative,digest in plan['source_sha256'].items():
            if relative.startswith('panda_abm/') or relative=='data/lot_config.json':
                if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=digest:source_differences.append(relative)
        population_hash=hashlib.sha256(json.dumps(population.as_dict(),sort_keys=True).encode()).hexdigest()
        checks=json.loads((archive/'checks.json').read_text())
        expected=next(c for c in checks if c['seed']==seed and c['occupancy']==occ and c['model']==settings['model'] and c['information']==settings['information'] and c.get('variant','base')=='base')
        assert expected['population_sha256']==population_hash,'Population did not match archive'
        assert expected['initial_occupancy_sha256']==hashlib.sha256(json.dumps(initial).encode()).hexdigest(),'Initial occupancy did not match'
        assert expected['outcome_sha256']==outcome_hash,'Recorded outcomes differ from saved experiment'
        verification=dict(status='Exact final-study outcome signature matched',outcome_sha256=outcome_hash,
                          archive=archive.name,source_differences=source_differences,
                          scope='Per-driver outcomes, population and initial occupancy; changed source files are recorded, not asserted identical',
                          original_checks_sha256=hashlib.sha256((archive/'checks.json').read_bytes()).hexdigest())
    parked=[o for o in outcomes if o['success']]
    edges=[[model.navigation.positions[u],model.navigation.positions[v]] for u,v in model.navigation.graph.edges()]
    result=dict(segment_labels=traffic_segment_labels(facility,model.navigation),schema_version=1,settings=settings,duration_s=model.clock_s,tracks=tracks,
                initial_occupied=initial,initial_closed=initial_closed,interventions=model.intervention_log,
                traffic_samples=telemetry,traffic=model.traffic.snapshot() if model.traffic else dict(enabled=False),
                occupancy_changes=changes,system=system,outcomes=outcomes,aisle_edges=edges,
                aisles={k:[model.navigation.positions[n] for n in ends] for k,ends in model.navigation.aisle_nodes.items()},
                source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT/'panda_abm').rglob('*.py')),ROOT/'data/lot_config.json']},
                population=population.as_dict(),verification=verification,
                summary=dict(drivers=len(agents),parked=len(parked),abandoned=sum(a.state==DriverState.ABANDONED for a in agents),
                             mean_search_s=float(np.mean([o['search_s'] for o in outcomes])),
                             mean_walk_m=float(np.mean([o['walk_m'] for o in parked])) if parked else None,
                             mean_exit_m=float(np.mean([o['exit_distance_m'] for o in parked])) if parked else None))
    if model.traffic:
        result['summary'].update(mean_entry_delay_s=float(np.mean([o['entry_delay_s'] for o in outcomes])),
            mean_arrival_to_search_end_s=float(np.mean([o['arrival_to_search_end_s'] for o in outcomes])))
    if horizon is not None:result['summary']=window_summary(model)
    result['config_sha256']=settings['environment']['config_sha256'] if settings['environment'] else hashlib.sha256((ROOT/'data/lot_config.json').read_bytes()).hexdigest()
    result['environment_sha256']=settings['environment']['environment_sha256'] if settings['environment'] else None
    from panda_abm.twin.urban_scenarios import urban_outcomes
    result['urban_outcomes']=urban_outcomes(model)
    result['walking_measure']='pedestrian_network' if facility.pedestrian_network else 'euclidean'
    result['through_traffic']=model.through_traffic.snapshot()
    result['termination_reason']='time_limit' if horizon is not None else 'all_drivers_finished'
    return result


class LiveSimulation:
    """On-demand 1-second updates; browser timing never changes physical time."""
    def __init__(self,settings):
        import threading
        self.lock=threading.Lock()
        self.settings,self.facility,self.population,self.model=build_replay_model(settings)
        self.agents=sorted(self.model.agents,key=lambda a:a.driver_id)
        self.visual_agents=sorted(road_agents(self.model),key=lambda a:a.driver_id)
        self.static_spaces=self.facility.space_by_id
        self.done=False
        self.horizon=self.settings['simulation_duration_s']
        self.initial_occupied=sorted(sid for sid,s in self.model.space_states.items() if s.occupied)
        self.occupied=set(self.initial_occupied)
        self.last_observation={}
        self.motion={a.driver_id:[] for a in self.visual_agents}
        self.bound=max(a.arrival_time_s+a.attributes.expected_dwell_duration_s for a in self.agents)+600+sum(e['weight'] for _,_,e in self.model.navigation.graph.edges(data=True))/self.model.search_speed_m_per_s+2000
        if self.settings['through_traffic']!='off':self.bound=max(self.bound,self.settings['through_demand_s']+2000+sum(e['weight'] for _,_,e in self.model.navigation.graph.edges(data=True))/self.model.search_speed_m_per_s)

        from panda_abm.core.pedestrian_movement import completion_padding
        self.bound+=completion_padding(self.model)

    def frame(self):
        now={sid for sid,s in self.model.space_states.items() if s.occupied}
        delta=[sorted(now-self.occupied),sorted(self.occupied-now)]
        self.occupied=now
        observations={}
        for a in self.agents:
            t=getattr(a,'last_observation_s',None)
            if t is not None and self.last_observation.get(a.driver_id)!=t:
                observations[a.driver_id]=dict(time_s=t,visible=a.last_visible_space_ids,
                    free=a.last_visible_free_space_ids,candidates=list(a.last_candidate_space_ids))
                self.last_observation[a.driver_id]=t
        from panda_abm.core.interventions import supply_snapshot
        return dict(time_s=self.model.clock_s,supply=supply_snapshot(self.model),observations=observations,
                    walking_intervals={a.driver_id:walking_intervals(a,self.model.walk_speed_m_per_s,self.static_spaces) for a in self.agents if a.parking_time_s is not None},
                    interventions=list(self.model.intervention_log),
                    traffic=self.model.traffic.snapshot() if self.model.traffic else dict(enabled=False),
                    through_traffic=self.model.through_traffic.snapshot(),
                    driver_views={a.driver_id:self.model.traffic.driver_view(a) for a in self.visual_agents if getattr(a,'role',None)!='through_traffic' or a.state==DriverState.EXITING} if self.model.traffic else {},
                    vehicles=[[a.driver_id,a.x_m,a.y_m,a.state.value,a.chosen_space_id,
                               window_status(a,self.model.clock_s)['search_s'] if self.horizon is not None else a.search_time_s,self.motion[a.driver_id]] for a in self.visual_agents if getattr(a,'role',None)!='through_traffic' or a.state==DriverState.EXITING or (a.left_s is not None and a.left_s>=self.model.clock_s-1)],
                    added=delta[0],removed=delta[1],
                    system=[self.model.clock_s,len(now),sum(a.state in (DriverState.SEARCHING,DriverState.TARGETING) for a in self.agents),
                            sum(a.parking_time_s is not None for a in self.agents),sum(a.search_ended_s is not None and a.parking_time_s is None for a in self.agents)])

    def describe(self):
        return dict(segment_labels=traffic_segment_labels(self.facility,self.model.navigation),settings=self.settings,initial_occupied=self.initial_occupied,
                    aisles={k:[self.model.navigation.positions[n] for n in ends] for k,ends in self.model.navigation.aisle_nodes.items()},
                    tracks=[dict(id=a.driver_id,door=a.attributes.walmart_door_id,intended_exit=a.attributes.preferred_exit_id,
                                 arrival_exit=a.attributes.arrival_exit_id,arrival_s=a.arrival_time_s,samples=[],role=getattr(a,'role','parking')) for a in self.visual_agents],
                    population=self.population.as_dict(),
                    source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT/'panda_abm').rglob('*.py')),ROOT/'data/lot_config.json']},
                    aisle_edges=[[self.model.navigation.positions[u],self.model.navigation.positions[v]] for u,v in self.model.navigation.graph.edges()],
                    frame=self.frame())

    def intervene(self,payload):
        from panda_abm.core.interventions import apply_intervention
        event=validate_intervention(payload)
        with self.lock:
            if self.done:raise ValueError('This simulation is complete; start a new simulation to change supply')
            event=apply_intervention(self.model,event)
            self.settings['interventions']=list(self.model.intervention_log)+list(self.model.scheduled_interventions)
            # Same-time actions can be replayed by adding this log to settings.
            return dict(event=event,settings=dict(self.settings),frame=self.frame())

    def advance(self,seconds):
        if type(seconds) is not int or not 1<=seconds<=120:raise ValueError('seconds must be an integer in [1, 120]')
        with self.lock:
            frames=[]
            for _ in range(seconds):
                if self.done:break
                path_lengths={a.driver_id:len(a.path) for a in self.visual_agents}
                self.model.step()
                self.motion={a.driver_id:step_motion(a,path_lengths[a.driver_id]) for a in self.visual_agents}
                frames.append(self.frame())
                self.done=(self.model.clock_s>=self.horizon if self.horizon is not None else
                           all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in self.agents) and through_finished(self.model))
                if self.horizon is None and self.model.clock_s>self.bound and not self.done:raise RuntimeError('Live run exceeded model time bound')
            parked=[a for a in self.agents if a.parking_time_s is not None]
            walks=[a.walking_distance_m for a in parked]
            exits=[self.facility.space_by_id[a.chosen_space_id].exit_distance(a.attributes.preferred_exit_id) for a in parked]
            summary=dict(drivers=len(self.agents),parked=len(parked),abandoned=sum(a.state==DriverState.ABANDONED for a in self.agents),
                         mean_search_s=float(np.mean([a.search_time_s for a in self.agents])),
                         mean_walk_m=float(np.mean(walks)) if walks else None,mean_exit_m=float(np.mean(exits)) if exits else None)
            if self.model.traffic:
                entry=[max(0.,(a.search_started_s if a.search_started_s is not None else self.model.clock_s)-a.arrival_time_s) for a in self.agents]
                summary.update(mean_entry_delay_s=float(np.mean(entry)),
                    mean_arrival_to_search_end_s=float(np.mean([t+a.search_time_s for t,a in zip(entry,self.agents)])))
            if self.horizon is not None:summary=window_summary(self.model)
            return dict(frames=frames,complete=self.done,time_s=self.model.clock_s,summary=summary,
                        cutoff_statuses={a.driver_id:window_status(a,self.model.clock_s) for a in self.agents} if self.done and self.horizon is not None else None,
                        termination_reason=('time_limit' if self.horizon is not None else 'all_drivers_finished') if self.done else None)
