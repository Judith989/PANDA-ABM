"""Frozen E2b/A1/E3/E4/E5/E6 campaign with reusable verified controls."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
from itertools import product
from dataclasses import asdict
import argparse,gc,hashlib,importlib.metadata,json,platform,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.environment import load_facility_from_lot_config
from panda_abm.behavior.continuous import make_population
from panda_abm.behavior.decision.cpt import LinearProspectDecisionModel
from panda_abm.core.states import DriverState
from panda_abm.simulation.tcss_conditions import ExperimentalParkingModel,SimpleSearchDecisionModel,transfer_facility
from panda_abm.twin.replay import build_replay_model,LiveSimulation

MODES=('unaided','aisle','space');POLICIES=('deterministic','rum','cpt','simple')
INVARIANTS=('exclusive_claims','balanced_release','terminal','finite','elapsed_identity','bounded_search','legal','walking_limits','local_targets','no_future_reports')


def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()


def signature(model):
    return [dict(driver=a.driver_id,success=a.parking_time_s is not None,search_s=a.search_time_s,
        search_distance_m=a.search_distance_m,walk_m=a.walking_distance_m if a.parking_time_s is not None else None,
        chosen_space=a.chosen_space_id if a.parking_time_s is not None else None,
        lost_claims=a.lost_space_events,parking_time_s=a.parking_time_s)
        for a in sorted(model.agents,key=lambda a:a.driver_id)]


def simulate(job):
    out=Path(job['output']);j={k:v for k,v in job.items() if k!='output'}
    tag=j['id'];folder=out/'replications';seed=j['seed'];occ=j['occupancy'];name=j['model'];mode=j['information']
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    if j.get('layout')=='transfer':facility=transfer_facility(facility)
    pop=make_population(facility,size=80,seed=seed)
    policy=LinearProspectDecisionModel() if name=='linear_cpt' else SimpleSearchDecisionModel() if name=='simple' else name
    model=ExperimentalParkingModel(facility,pop,policy,seed=seed,initial_occupancy_rate=occ,
        information_mode=mode,run_id=f'information_{seed}_{occ}',scenario_id=j['stage'],
        replication_id=f'seed_{seed}',decision_seed_namespace='information_matched',
        adoption_rate=j.get('adoption',1.),report_delay_s=j.get('delay',0.),
        background_median_s=j.get('turnover'),integration_seconds=j.get('integration',1.))
    initial=sorted(s for s,v in model.space_states.items() if v.occupied)
    inputs=dict(population_sha256=digest(pop.as_dict()),initial_occupancy_sha256=digest(initial),
        adoption_draws_sha256=digest(model.adoption_draws),background_schedule_sha256=digest(model.background_schedule))
    model.run_until_complete()
    active={};claims=releases=0;exclusive=finite=local=history=True;selected=[]
    for e in model.event_logger.records:
        if e.utility is not None:finite &= bool(np.isfinite(e.utility))
        if e.event_type=='SpaceClaimSucceeded':
            exclusive &= e.space_id not in active;active[e.space_id]=e.agent_id;claims+=1
        elif e.event_type=='SpaceReleased':
            exclusive &= active.get(e.space_id)==e.agent_id;active.pop(e.space_id,None);releases+=1
        elif e.event_type=='TargetSelected':
            effective=mode if e.agent_id in model.adopters else 'unaided'
            if effective!='space':local &= e.details['target_distance_at_selection_m']<=60+1e-9
            if e.details.get('information_source')=='space_report' and j.get('delay',0):
                history &= e.details['report_time_s']<=max(0,e.time_s-j['delay'])+1e-9
        if e.event_type in ('TargetSelected','InformationSearchAreaSelected','SpaceClaimFailed','BackgroundSpaceReleased','CandidateRejected'):
            selected.append(dict(time_s=e.time_s,event=e.event_type,driver=e.agent_id,space=e.space_id,details=e.details))
    agents=sorted(model.agents,key=lambda a:a.driver_id);rows=[]
    for a in agents:
        success=a.parking_time_s is not None;s=facility.space_by_id.get(a.chosen_space_id) if success else None
        rows.append(j|dict(driver=a.driver_id,adopter=a.driver_id in model.adopters,adoption_draw=model.adoption_draws[a.driver_id],
            success=success,search_s=a.search_time_s,search_distance_m=a.search_distance_m,
            walk_m=a.walking_distance_m if success else None,chosen_space=s.space_id if s else None,
            chosen_aisle=model.navigation.space_aisle[s.space_id] if s else None,
            lost_claims=a.lost_space_events,parking_time_s=a.parking_time_s,
            exit_distance_m=getattr(s,f'distance_to_{a.attributes.preferred_exit_id}_m',None) if s else None,
            mobility_limited=a.attributes.mobility_limitation,eligible=a.attributes.accessibility_eligibility,
            door=a.attributes.walmart_door_id,intended_exit=a.attributes.preferred_exit_id))
    check=j|inputs|dict(exclusive_claims=bool(exclusive),balanced_release=not active and claims==releases,
        terminal=all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in agents),finite=bool(finite),
        elapsed_identity=all(a.search_time_s==a.search_ended_s-a.search_started_s for a in agents),
        bounded_search=all(0<=a.search_time_s<=600 for a in agents),legal=not any(a.violation for a in agents),
        walking_limits=all(a.parking_time_s is None or a.attributes.max_walking_distance_m is None or a.walking_distance_m<=a.attributes.max_walking_distance_m+1e-9 for a in agents),
        local_targets=bool(local),no_future_reports=bool(history),outcome_sha256=digest(signature(model)),
        background_released=sum(e.event_type=='BackgroundSpaceReleased' for e in model.event_logger.records))
    assert all(check[k] for k in INVARIANTS),check
    df=pd.DataFrame(rows);parked=df[df.success]
    summary=j|dict(drivers=80,success=float(df.success.mean()),mean_search_s=float(df.search_s.mean()),
        mean_walk_parked_m=float(parked.walk_m.mean()),mean_exit_parked_m=float(parked.exit_distance_m.mean()),
        claims_per_arrival=float(df.lost_claims.mean()),mean_search_distance_m=float(df.search_distance_m.mean()),
        adopters=int(df.adopter.sum()))
    pd.DataFrame(rows).to_csv(folder/f'{tag}_drivers.csv',index=False)
    (folder/f'{tag}_run.json').write_text(json.dumps(summary),encoding='utf-8')
    (folder/f'{tag}_check.json').write_text(json.dumps(check),encoding='utf-8')
    # Archive complete context inputs once per facility/seed, before pooling outputs.
    (folder/f'{tag}_inputs.json').write_text(json.dumps(dict(population=pop.as_dict(),initial_occupancy=initial,
        background_schedule=model.background_schedule,adoption_draws=model.adoption_draws)),encoding='utf-8')
    (folder/f'{tag}_events.json').write_text(json.dumps(selected),encoding='utf-8')
    print(f'{tag}: success={summary["success"]:.3f}, search={summary["mean_search_s"]:.2f}',flush=True)
    del model;gc.collect();return tag


def equivalence(job):
    out=Path(job['output']);settings=job['settings'];tag=job['id']
    _,_,_,model=build_replay_model(settings);initial=sorted(s for s,v in model.space_states.items() if v.occupied)
    occupied=set(initial);changes=[]
    while True:
        model.step();now={s for s,v in model.space_states.items() if v.occupied}
        if now!=occupied:changes.append([model.clock_s,sorted(now-occupied),sorted(occupied-now)])
        occupied=now
        if all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in model.agents):break
    outcome=digest(signature(model));live=LiveSimulation(settings);live_changes=[];i=0
    while not live.done:
        # No model call during a pause; physical time must stay fixed.
        before=live.model.clock_s;assert live.model.clock_s==before
        update=live.advance((1,17,3,120,29)[i%5]);i+=1
        for f in update['frames']:
            if f['added'] or f['removed']:live_changes.append([f['time_s'],f['added'],f['removed']])
    check=dict(id=tag,settings=settings,signature_equal=outcome==digest(signature(live.model)),
        occupancy_changes_equal=changes==live_changes,initial_occupancy_equal=initial==live.initial_occupied,
        outcome_sha256=outcome,occupancy_changes_sha256=digest(changes))
    assert check['signature_equal'] and check['occupancy_changes_equal'] and check['initial_occupancy_equal']
    (out/'equivalence'/f'{tag}.json').write_text(json.dumps(check),encoding='utf-8')
    print(tag+': equivalent',flush=True);return tag


def design_jobs(out):
    jobs=[]
    def add(stage,occupancies,models,modes,seeds,**options):
        for occ,name,mode,seed in product(occupancies,models,modes,seeds):
            jobs.append(dict(stage=stage,occupancy=occ,model=name,information=mode,seed=seed,**options))
    add('E2b',(.4,.8,.95),('simple',),MODES,range(1000,1030))
    for rate in (.25,.5,.75):add('A1',(.8,.95),POLICIES[:3],('aisle','space'),range(1000,1010),adoption=rate)
    add('E3a',(.8,.95),POLICIES,MODES,range(1000,1010),turnover=1800.)
    add('E3b',(.8,.95),POLICIES,('aisle','space'),range(1000,1010),delay=30.)
    add('E4',(.8,.95),POLICIES,MODES,range(1000,1030),layout='transfer')
    for step in (.5,.25):add('E5',(.95,),POLICIES+('linear_cpt',),MODES,range(1000,1010),integration=step)
    for i,j in enumerate(jobs):j.update(id=f'{i:04d}_{j["stage"]}',output=str(out))
    return jobs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workers',type=int,default=10)
    parser.add_argument('--resume',action='store_true');args=parser.parse_args();out=args.output
    jobs=design_jobs(out)
    eq=[dict(id=f'E6_{i:03d}',output=str(out),settings=dict(seed=seed,population_size=size,occupancy=.8,
        model=model,information=mode,arrival_interval_s=20)) for i,(seed,size,model,mode) in enumerate(
        product(range(4000,4005),(8,80),POLICIES[:3],MODES))]
    files=sorted([*ROOT.glob('panda_abm/**/*.py'),*ROOT.glob('scripts/*.py'),*ROOT.glob('tests/*.py'),
        ROOT/'data/lot_config.json',ROOT/'research/tcss/README.md',ROOT/'requirements.txt',ROOT/'requirements-analysis.txt'])
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if out.exists():
        if not args.resume:raise FileExistsError(out)
        manifest=json.loads((out/'design.json').read_text())
        assert manifest['source_sha256']==hashes,'Source changed; do not mix versions'
    else:
        (out/'replications').mkdir(parents=True);(out/'equivalence').mkdir()
        manifest=dict(status='running',version='tcss_conditions_v3_default_preserves_v2',jobs=jobs,equivalence=eq,
            behavioral_executions=len(jobs),equivalence_executions=len(eq)*2,total_executions=len(jobs)+2*len(eq),
            source_sha256=hashes,python=sys.version,platform=platform.platform(),
            packages={n:importlib.metadata.version(n) for n in ('mesa','numpy','pandas','networkx')},
            baseline='results/tcss_first_batch_20261028',tests_passed=195,
            analysis='Exploratory matched seed contrasts; pointwise intervals, not field validation.')
        (out/'design.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        with zipfile.ZipFile(out/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for p in files:archive.write(p,p.relative_to(ROOT))
        f=transfer_facility(load_facility_from_lot_config(ROOT/'data/lot_config.json'))
        (out/'transfer_layout.json').write_text(json.dumps(asdict(f),default=str),encoding='utf-8')
    # Verify opt-in extensions against the frozen v2 controls before new treatments.
    # These are additional verification executions, not independent study replications.
    old=ROOT/'results/tcss_first_batch_20261028'
    old_design=json.loads((old/'design.json').read_text())
    assert hashlib.sha256((old/'checks.json').read_bytes()).hexdigest()==old_design['output_sha256']['checks.json']
    expected={(c['seed'],c['occupancy'],c['model'],c['information']):c for c in json.loads((old/'checks.json').read_text()) if c['variant']=='base'}
    probes=[];probeout=out/'regression';(probeout/'replications').mkdir(parents=True,exist_ok=True)
    for occ in (.4,.8,.95):
        for name,mode in product(POLICIES[:3]+(('linear_cpt',) if occ!=.4 else ()),MODES):
            probes.append(dict(id=f'probe_{len(probes):02d}',stage='regression',seed=1000,occupancy=occ,
                model=name,information=mode,output=str(probeout)))
    if not (out/'regression_checks.json').exists():
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for _ in pool.map(simulate,probes):pass
        verified=[]
        for j in probes:
            c=json.loads((probeout/'replications'/f'{j["id"]}_check.json').read_text())
            target=expected[(1000,j['occupancy'],j['model'],j['information'])]
            for field in ('outcome_sha256','population_sha256','initial_occupancy_sha256'):assert c[field]==target[field],(j,field)
            verified.append(c)
        (out/'regression_checks.json').write_text(json.dumps(verified,indent=2),encoding='utf-8')
    print('All 33 full-size default-control signatures matched the frozen first batch',flush=True)
    pending=[(simulate,j) for j in jobs if not (out/'replications'/f'{j["id"]}_check.json').exists()]
    pending.extend((equivalence,j) for j in eq if not (out/'equivalence'/f'{j["id"]}.json').exists())
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(fn,j) for fn,j in pending]
        for i,future in enumerate(as_completed(futures),1):future.result();print(f'Completed job {i}/{len(pending)}',flush=True)
    runs=[json.loads(p.read_text()) for p in sorted((out/'replications').glob('*_run.json'))]
    checks=[json.loads(p.read_text()) for p in sorted((out/'replications').glob('*_check.json'))]
    equivalences=[json.loads(p.read_text()) for p in sorted((out/'equivalence').glob('*.json'))]
    assert len(runs)==len(checks)==2050 and len(equivalences)==90
    assert all(all(c[k] for k in INVARIANTS) for c in checks)
    pd.DataFrame(runs).to_csv(out/'runs.csv',index=False)
    pd.concat([pd.read_csv(p) for p in sorted((out/'replications').glob('*_drivers.csv'))],ignore_index=True).to_csv(out/'drivers.csv',index=False)
    (out/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    (out/'equivalence.json').write_text(json.dumps(equivalences,indent=2),encoding='utf-8')
    manifest['verification_executions']=33
    manifest['status']='completed';manifest['outputs']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ('runs.csv','drivers.csv','checks.json','equivalence.json','regression_checks.json')}
    (out/'design.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Completed 2050 behavioral executions and 90 execution-equivalence pairs',flush=True)


if __name__=='__main__':main()
