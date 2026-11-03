"""Frozen matched current-information experiments; no prediction or reservation."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import gc
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
import zipfile
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior.continuous import make_population,PopulationPriors
from panda_abm.behavior.continuous import PREFERENCE_MEANS, sample_cpt
from panda_abm.behavior.decision.cpt import LinearProspectDecisionModel
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.environment import load_facility_from_lot_config

MODES=('unaided','aisle','space')
MODELS=('deterministic','rum','cpt')


def replication(job):
    seed,occupancy,size,output,*extra=job;out=Path(output)
    options=extra[0] if extra else {}
    variant=options.get('variant','base')
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    pop=make_population(facility,size=size,seed=seed)
    base_hash=hashlib.sha256(json.dumps(pop.as_dict(),sort_keys=True).encode()).hexdigest()
    if variant=='homogeneous_tastes':
        pop=replace(pop,drivers=tuple(replace(d,behavioral_parameters=replace(
            d.behavioral_parameters,**PREFERENCE_MEANS)) for d in pop.drivers))
    elif variant=='homogeneous_cpt':
        central=sample_cpt(None,PopulationPriors(),heterogeneous=False)
        pop=replace(pop,drivers=tuple(replace(d,cpt_parameters=central,
            cpt_parameter_source='tcss_central_parameter_control') for d in pop.drivers))
    elif variant!='base':raise ValueError(variant)
    serialized=json.dumps(pop.as_dict(),sort_keys=True)
    pop_hash=hashlib.sha256(serialized.encode()).hexdigest()
    tag=f'{seed}_{occupancy}'
    (out/'populations'/f'{tag}.json').write_text(serialized,encoding='utf-8')
    drivers=[];runs=[];checks=[];selected_events=[];initial=None;initial_hash=None
    for name in options.get('models',MODELS):
        for mode in MODES:
            started=time.perf_counter()
            policy=LinearProspectDecisionModel() if name=='linear_cpt' else name
            model=ParkingModel(facility,pop,policy,seed=seed,initial_occupancy_rate=occupancy,
                information_mode=mode,scenario_id=f'occupancy_{occupancy}',run_id=f'information_{seed}_{occupancy}',
                replication_id=f'seed_{seed}',decision_seed_namespace='information_matched')
            occupied=sorted(sid for sid,s in model.space_states.items() if s.occupied)
            if initial is None:
                initial=occupied;initial_hash=hashlib.sha256(json.dumps(occupied).encode()).hexdigest()
                (out/'initial_occupancy'/f'{tag}.json').write_text(json.dumps(occupied))
            assert occupied==initial
            model.run_until_complete();active={};exclusive=True;releases=0;claims=0;local=True;finite=True
            for e in model.event_logger.records:
                if e.utility is not None:finite &= bool(np.isfinite(e.utility))
                if e.event_type=='SpaceClaimSucceeded':
                    exclusive &= e.space_id not in active;active[e.space_id]=e.agent_id;claims+=1
                elif e.event_type=='SpaceReleased':
                    exclusive &= active.get(e.space_id)==e.agent_id;active.pop(e.space_id,None);releases+=1
                elif e.event_type=='TargetSelected' and mode!='space':
                    local &= e.details['target_distance_at_selection_m']<=model.perception_radius_m+1e-9
                if e.event_type in ('InformationSearchAreaSelected','TargetSelected','SpaceClaimFailed','SearchAbandoned','ParkingStarted'):
                    selected_events.append(dict(seed=seed,occupancy=occupancy,model=name,information=mode,
                        driver=e.agent_id,time_s=e.time_s,event=e.event_type,space=e.space_id,
                        details={k:v for k,v in e.details.items() if k in (
                            'aisle_id','free_count','compatible_capacity','report_time_s','area_score','entry_node','end_node',
                            'target_distance_at_selection_m','information_source')}))
            agents=sorted(model.agents,key=lambda a:a.driver_id)
            arm=[]
            for a in agents:
                parked=a.parking_time_s is not None
                space=facility.space_by_id.get(a.chosen_space_id) if parked else None
                arm.append(dict(seed=seed,occupancy=occupancy,model=name,information=mode,variant=variant,driver=a.driver_id,
                    success=parked,search_s=a.search_time_s,search_distance_m=a.search_distance_m,
                    walk_m=a.walking_distance_m if parked else None,chosen_space=space.space_id if space else None,
                    chosen_aisle=model.navigation.space_aisle[space.space_id] if space else None,
                    lost_claims=a.lost_space_events,rejected_candidates=a.rejected_spaces,
                    reports=a.information_reports_received,information_route_changes=a.information_route_changes,
                    remote_targets=a.remote_targets_selected,door=a.attributes.walmart_door_id,
                    arrival_access=a.attributes.arrival_exit_id,intended_exit=a.attributes.preferred_exit_id,
                    exit_distance_m=getattr(space,f'distance_to_{a.attributes.preferred_exit_id}_m',None) if space else None,
                    mobility_limited=a.attributes.mobility_limitation,eligible=a.attributes.accessibility_eligibility,
                    permit=a.attributes.permit_type,violation=a.violation,parking_time_s=a.parking_time_s))
            signature=[{k:r[k] for k in ('driver','success','search_s','search_distance_m','walk_m','chosen_space','lost_claims','parking_time_s')} for r in arm]
            check=dict(seed=seed,occupancy=occupancy,model=name,information=mode,variant=variant,population_sha256=pop_hash,base_population_sha256=base_hash,
                initial_occupancy_sha256=initial_hash,exclusive_claims=bool(exclusive),balanced_release=not active and claims==releases,
                terminal=all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in agents),finite=bool(finite),
                elapsed_identity=all(a.search_time_s==a.search_ended_s-a.search_started_s for a in agents),
                bounded_search=all(0<=a.search_time_s<=600 for a in agents),legal=not any(a.violation for a in agents),
                walking_limits=all(a.parking_time_s is None or a.attributes.max_walking_distance_m is None or
                    a.walking_distance_m<=a.attributes.max_walking_distance_m+1e-9 for a in agents),local_stall_targets=bool(local),
                outcome_sha256=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest())
            assert all(check[k] for k in ('exclusive_claims','balanced_release','terminal','finite','elapsed_identity','bounded_search','legal','walking_limits','local_stall_targets')),check
            drivers.extend(arm);checks.append(check)
            frame=pd.DataFrame(arm);parked_frame=frame[frame.success]
            runs.append(dict(seed=seed,occupancy=occupancy,model=name,information=mode,variant=variant,drivers=size,parked=int(frame.success.sum()),
                success=frame.success.mean(),mean_search_s=frame.search_s.mean(),mean_search_parked_s=parked_frame.search_s.mean(),
                mean_walk_parked_m=parked_frame.walk_m.mean(),mean_search_distance_m=frame.search_distance_m.mean(),
                mean_exit_parked_m=parked_frame.exit_distance_m.mean(),lost_claims=int(frame.lost_claims.sum()),
                remote_targets=int(frame.remote_targets.sum()),information_route_changes=int(frame.information_route_changes.sum()),
                seconds=time.perf_counter()-started))
            print(f'{tag} {name}/{mode}: {int(frame.success.sum())}/{size}, search {frame.search_s.mean():.1f}s',flush=True)
            del model;gc.collect()
    pd.DataFrame(drivers).to_csv(out/'replications'/f'{tag}_drivers.csv',index=False)
    pd.DataFrame(runs).to_csv(out/'replications'/f'{tag}_runs.csv',index=False)
    (out/'replications'/f'{tag}_checks.json').write_text(json.dumps(checks,indent=2))
    (out/'replications'/f'{tag}_selected_events.json').write_text(json.dumps(selected_events))
    return tag


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/parking_information_20261028')
    parser.add_argument('--seeds',type=int,nargs='+',default=list(range(1000,1010)))
    parser.add_argument('--occupancies',type=float,nargs='+',default=[.4,.8,.95])
    parser.add_argument('--size',type=int,default=80)
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args();out=args.output
    if (out/'design.json').exists():raise FileExistsError('Preserve frozen study; choose fresh output')
    for p in (out,out/'replications',out/'populations',out/'initial_occupancy'):p.mkdir(parents=True,exist_ok=True)
    source=sorted([*ROOT.glob('panda_abm/**/*.py'),*ROOT.glob('scripts/*.py'),*ROOT.glob('tests/*.py'),*ROOT.glob('research/*'),
        ROOT/'data/lot_config.json',ROOT/'README.md',ROOT/'requirements.txt',ROOT/'requirements-analysis.txt'])
    source=[p for p in source if p.is_file()]
    design=dict(seeds=args.seeds,occupancies=args.occupancies,size=args.size,information_modes=MODES,models=MODELS,
        runs=len(args.seeds)*len(args.occupancies)*9,information='Accurate current reports at search scans; no prediction, reservation or continuous target rerouting',
        aisle_policy='Personal compatible free counts; static mean utility and free fraction guide route only after local offers declined',
        matching='Frozen identical population and initial occupied IDs across nine arms; shared run ID/decision RNG namespace; population reused across occupancies',
        prior_status='Uncalibrated continuous structural priors; no personas assigned',
        uncertainty='Paired seed bootstrap pilot; no independent-driver inference or presumed superiority',
        python=sys.version,platform=platform.platform(),packages={n:importlib.metadata.version(n) for n in ('mesa','numpy','pandas','networkx')},
        source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source})
    (out/'design.json').write_text(json.dumps(design,indent=2))
    with zipfile.ZipFile(out/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in source:z.write(p,p.relative_to(ROOT))
    jobs=[(seed,occupancy,args.size,str(out)) for occupancy in args.occupancies for seed in args.seeds]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(replication,j) for j in jobs]
        for f in as_completed(futures):print('Completed '+f.result(),flush=True)
    for suffix in ('drivers','runs'):
        pd.concat([pd.read_csv(p) for p in sorted((out/'replications').glob(f'*_{suffix}.csv'))],ignore_index=True).to_csv(out/f'{suffix}.csv',index=False)
    checks=[r for p in sorted((out/'replications').glob('*_checks.json')) for r in json.loads(p.read_text())]
    (out/'checks.json').write_text(json.dumps(checks,indent=2))
    print(f'Completed {len(checks)} matched runs',flush=True)


if __name__=='__main__':main()
