"""Record the existing model for a Cesium replay without changing its decisions."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import numpy as np
from panda_abm.behavior.continuous import make_population,PopulationPriors
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.environment import load_facility_from_lot_config

ROOT=Path(__file__).resolve().parents[2]
DEFAULTS=dict(seed=1000,population_size=80,occupancy=.4,model='cpt',information='unaided',arrival_interval_s=20)


def validate_settings(settings):
    if not isinstance(settings,dict) or set(settings)-set(DEFAULTS):raise ValueError('Unknown scenario settings')
    s=DEFAULTS|settings
    for key,low,high in [('seed',0,2147483647),('population_size',1,120),('arrival_interval_s',1,120)]:
        if type(s[key]) is not int or not low<=s[key]<=high:raise ValueError(f'{key} must be an integer in [{low}, {high}]')
    if type(s['occupancy']) not in (int,float) or not np.isfinite(s['occupancy']) or not 0<=s['occupancy']<=1:raise ValueError('occupancy must be in [0, 1]')
    if s['model'] not in ('deterministic','rum','cpt'):raise ValueError('Unknown decision model')
    if s['information'] not in ('unaided','aisle','space'):raise ValueError('Unknown information condition')
    return s


def build_replay_model(settings):
    """Use one construction path for saved recordings and live sessions."""
    settings=validate_settings(settings)
    seed=settings['seed'];occ=settings['occupancy']
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    population=make_population(facility,size=settings['population_size'],seed=seed,
                               priors=PopulationPriors(arrival_interval_s=float(settings['arrival_interval_s'])))
    # Match the experiment's RNG namespace and run ID across model/information arms.
    model=ParkingModel(facility,population,settings['model'],seed=seed,initial_occupancy_rate=occ,
                       information_mode=settings['information'],scenario_id=f'occupancy_{occ}',
                       run_id=f'information_{seed}_{occ}',replication_id=f'seed_{seed}',
                       decision_seed_namespace='information_matched',step_seconds=1)
    return settings,facility,population,model


def record_run(settings,progress=None,verify_archive=False):
    settings,facility,population,model=build_replay_model(settings)
    seed=settings['seed'];occ=settings['occupancy']
    agents=sorted(model.agents,key=lambda a:a.driver_id)
    tracks=[dict(id=a.driver_id,door=a.attributes.walmart_door_id,intended_exit=a.attributes.preferred_exit_id,
                 arrival_exit=a.attributes.arrival_exit_id,arrival_s=a.arrival_time_s,samples=[]) for a in agents]
    occupied={sid for sid,s in model.space_states.items() if s.occupied}
    initial=sorted(occupied);changes=[];system=[]
    def capture():
        nonlocal occupied
        for a,track in zip(agents,tracks):
            row=[a.x_m,a.y_m,a.state.value,a.chosen_space_id,a.search_time_s]
            if not track['samples'] or track['samples'][-1][1:]!=row:
                track['samples'].append([model.clock_s,*row])
        now={sid for sid,s in model.space_states.items() if s.occupied}
        if now!=occupied:
            changes.append([model.clock_s,sorted(now-occupied),sorted(occupied-now)])
        occupied=now
        if model.clock_s%10==0:
            system.append([model.clock_s,len(now),sum(a.state in (DriverState.SEARCHING,DriverState.TARGETING) for a in agents),
                           sum(a.parking_time_s is not None for a in agents),sum(a.state==DriverState.ABANDONED for a in agents)])
    capture()
    route_bound=sum(e['weight'] for _,_,e in model.navigation.graph.edges(data=True))/model.search_speed_m_per_s
    bound=max(a.arrival_time_s+a.attributes.expected_dwell_duration_s for a in agents)+600+route_bound+2000
    while model.clock_s<=bound:
        model.step();capture()
        if progress and model.clock_s%100==0:progress(model.clock_s)
        if all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in agents):break
    else:raise RuntimeError('Simulation did not finish within its time bound')
    outcomes=[];signature=[]
    for a in agents:
        parked=a.parking_time_s is not None
        space=facility.space_by_id[a.chosen_space_id] if parked else None
        outcome=dict(driver=a.driver_id,success=parked,search_s=a.search_time_s,search_distance_m=a.search_distance_m,
                     walk_m=a.walking_distance_m if parked else None,chosen_space=a.chosen_space_id if parked else None,
                     lost_claims=a.lost_space_events,parking_time_s=a.parking_time_s)
        signature.append(outcome)
        outcomes.append(outcome|dict(door=a.attributes.walmart_door_id,intended_exit=a.attributes.preferred_exit_id,
                                     exit_distance_m=getattr(space,f'distance_to_{a.attributes.preferred_exit_id}_m',None) if space else None))
    outcome_hash=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    verification=None
    if verify_archive:
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
    return dict(schema_version=1,settings=settings,duration_s=model.clock_s,tracks=tracks,
                initial_occupied=initial,occupancy_changes=changes,system=system,outcomes=outcomes,aisle_edges=edges,
                source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT/'panda_abm').rglob('*.py')),ROOT/'data/lot_config.json']},
                population=population.as_dict(),verification=verification,
                summary=dict(drivers=len(agents),parked=len(parked),abandoned=sum(a.state==DriverState.ABANDONED for a in agents),
                             mean_search_s=float(np.mean([o['search_s'] for o in outcomes])),
                             mean_walk_m=float(np.mean([o['walk_m'] for o in parked])) if parked else None,
                             mean_exit_m=float(np.mean([o['exit_distance_m'] for o in parked])) if parked else None))


class LiveSimulation:
    """On-demand 1-second updates; browser timing never changes physical time."""
    def __init__(self,settings):
        import threading
        self.lock=threading.Lock()
        self.settings,self.facility,self.population,self.model=build_replay_model(settings)
        self.agents=sorted(self.model.agents,key=lambda a:a.driver_id)
        self.done=False
        self.initial_occupied=sorted(sid for sid,s in self.model.space_states.items() if s.occupied)
        self.occupied=set(self.initial_occupied)
        self.bound=max(a.arrival_time_s+a.attributes.expected_dwell_duration_s for a in self.agents)+600+sum(e['weight'] for _,_,e in self.model.navigation.graph.edges(data=True))/self.model.search_speed_m_per_s+2000

    def frame(self):
        now={sid for sid,s in self.model.space_states.items() if s.occupied}
        delta=[sorted(now-self.occupied),sorted(self.occupied-now)]
        self.occupied=now
        return dict(time_s=self.model.clock_s,
                    vehicles=[[a.driver_id,a.x_m,a.y_m,a.state.value,a.chosen_space_id,a.search_time_s] for a in self.agents],
                    added=delta[0],removed=delta[1],
                    system=[self.model.clock_s,len(now),sum(a.state in (DriverState.SEARCHING,DriverState.TARGETING) for a in self.agents),
                            sum(a.parking_time_s is not None for a in self.agents),sum(a.state==DriverState.ABANDONED for a in self.agents)])

    def describe(self):
        return dict(settings=self.settings,initial_occupied=self.initial_occupied,
                    tracks=[dict(id=a.driver_id,door=a.attributes.walmart_door_id,intended_exit=a.attributes.preferred_exit_id,
                                 arrival_exit=a.attributes.arrival_exit_id,arrival_s=a.arrival_time_s,samples=[]) for a in self.agents],
                    population=self.population.as_dict(),
                    source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT/'panda_abm').rglob('*.py')),ROOT/'data/lot_config.json']},
                    aisle_edges=[[self.model.navigation.positions[u],self.model.navigation.positions[v]] for u,v in self.model.navigation.graph.edges()],
                    frame=self.frame())

    def advance(self,seconds):
        if type(seconds) is not int or not 1<=seconds<=120:raise ValueError('seconds must be an integer in [1, 120]')
        with self.lock:
            frames=[]
            for _ in range(seconds):
                if self.done:break
                self.model.step();frames.append(self.frame())
                self.done=all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in self.agents)
                if self.model.clock_s>self.bound and not self.done:raise RuntimeError('Live run exceeded model time bound')
            parked=[a for a in self.agents if a.parking_time_s is not None]
            walks=[a.walking_distance_m for a in parked]
            exits=[getattr(self.facility.space_by_id[a.chosen_space_id],f'distance_to_{a.attributes.preferred_exit_id}_m') for a in parked]
            summary=dict(drivers=len(self.agents),parked=len(parked),abandoned=sum(a.state==DriverState.ABANDONED for a in self.agents),
                         mean_search_s=float(np.mean([a.search_time_s for a in self.agents])),
                         mean_walk_m=float(np.mean(walks)) if walks else None,mean_exit_m=float(np.mean(exits)) if exits else None)
            return dict(frames=frames,complete=self.done,time_s=self.model.clock_s,summary=summary)
