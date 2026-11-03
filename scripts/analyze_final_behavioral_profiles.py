"""Frozen exploratory profile reanalysis of final TCSS outcomes, not new ABM runs."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from panda_abm.analysis.profiles import explore_behavioral_regimes

MODELS=['deterministic','rum','cpt']
MODES=['unaided','aisle','space']
SETTINGS=dict(max_components=6,n_init=10,bootstrap_repetitions=20,min_train=80,min_validation=40)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def prepare_records():
    first=ROOT/'results/tcss_first_batch_20261028'
    later=ROOT/'results/tcss_robustness_20261028'
    design=json.loads((first/'design.json').read_text())
    checksums=json.loads((later/'artifact_checksums.json').read_text())
    sources={}
    for folder,hashes in [(first,design['output_sha256']),(later,checksums)]:
        for name in ['drivers.csv','checks.json']:
            p=folder/name;assert sha(p)==hashes[name],p
            sources[p.relative_to(ROOT).as_posix()]=sha(p)
    f=pd.read_csv(first/'drivers.csv')
    f=f[f.model.isin(MODELS)&f.variant.isin(['base','homogeneous_tastes'])].copy()
    restored=[]
    for (variant,seed,occ),g in f.groupby(['variant','seed','occupancy']):
        stage='core' if variant=='base' else 'tastes'
        p=first/stage/'populations'/f'{seed}_{occ}.json'
        pop=json.loads(p.read_text());sources[p.relative_to(ROOT).as_posix()]=sha(p)
        lookup={d['attributes']['driver_id']:d for d in pop['drivers']}
        for d in lookup.values():assert d['attributes']['persona'] is None
        g['r_walk_m']=g.driver.map(lambda key:lookup[key]['reference_points']['r_walk_m'])
        for col in ['beta_walk','beta_search','decision_temperature']:
            g[col]=g.driver.map(lambda key:lookup[key]['behavioral_parameters'][col])
        g['context']='walmart';g['population']=variant
        restored.append(g)
    base=pd.concat(restored,ignore_index=True)
    l=pd.read_csv(later/'drivers.csv')
    transfer=l[(l.stage=='E4')&l.model.isin(MODELS)].copy()
    checks=json.loads((later/'checks.json').read_text())
    restored=[]
    for seed,g in transfer.groupby('seed'):
        cc=[x for x in checks if x['stage']=='E4' and x['seed']==seed]
        assert len({x['population_sha256'] for x in cc})==1
        p=later/'replications'/f"{cc[0]['id']}_inputs.json"
        pop=json.loads(p.read_text())['population']
        assert hashlib.sha256(json.dumps(pop,sort_keys=True).encode()).hexdigest()==cc[0]['population_sha256']
        sources[p.relative_to(ROOT).as_posix()]=sha(p)
        lookup={d['attributes']['driver_id']:d for d in pop['drivers']}
        g=g.copy()
        g['permit']=g.driver.map(lambda key:lookup[key]['attributes']['permit_type'])
        g['r_walk_m']=g.driver.map(lambda key:lookup[key]['reference_points']['r_walk_m'])
        for col in ['beta_walk','beta_search','decision_temperature']:
            g[col]=g.driver.map(lambda key:lookup[key]['behavioral_parameters'][col])
        g['context']='synthetic';g['population']='base'
        restored.append(g)
    transfer=pd.concat(restored,ignore_index=True)
    columns=['context','population','occupancy','seed','model','information','driver','success',
        'search_s','walk_m','r_walk_m','mobility_limited','eligible','permit','chosen_space',
        'beta_walk','beta_search','decision_temperature']
    records=pd.concat([base[columns],transfer[columns]],ignore_index=True)
    assert len(records)==122400,len(records)
    assert not records.duplicated(['context','population','occupancy','seed','model','information','driver']).any()
    records['analysis_eligible']=records.success&~records.mobility_limited&~records.eligible&records.permit.isna()
    records['exclusion_reason']=np.select([~records.success,records.mobility_limited,records.eligible,records.permit.notna()],
        ['not_parked','walking_constraint','accessible_eligibility','permit'],default='included')
    assert (records.r_walk_m>0).all()
    records['walk_relative']=records.walk_m/records.r_walk_m
    return records,sources

def evaluate(payload):
    meta,frame,train,validation=payload
    if meta['family']=='null':
        rng=np.random.default_rng(50100+meta['replicate']);n=600;z=rng.normal(size=(n,2))
        family=meta['context']
        if family=='single_gaussian':x=np.column_stack((4+.35*z[:,0],.7+.08*z[:,1]))
        elif family=='single_skewed':x=np.column_stack((3+.5*rng.gamma(2,1,n),.3+.15*rng.gamma(2,1,n)))
        elif family=='curved_continuum':x=np.column_stack((4+.4*z[:,0],.5+.15*z[:,0]**2+.05*z[:,1]))
        else:
            group=rng.integers(2,size=n)
            x=np.column_stack((3+2*group+.15*z[:,0],.3+.7*group+.04*z[:,1]))
        frame=pd.DataFrame(dict(seed=np.repeat(np.arange(10),60),driver=np.arange(n),
            search_s=np.expm1(x[:,0]),walk_relative=np.expm1(x[:,1])))
    result,assigned,selection=explore_behavioral_regimes(frame,train,validation,**SETTINGS)
    for key,value in meta.items():
        if not assigned.empty:assigned[key]=value
        if not selection.empty:selection[key]=value
    return meta|result,assigned,selection

def job_list(records):
    jobs=[]
    def add(family,context,pop,occ,model,info,seeds,train,validation):
        g=records[(records.context==context)&(records.population==pop)&np.isclose(records.occupancy,occ)&
            records.model.eq(model)&records.information.eq(info)&records.seed.isin(seeds)&records.analysis_eligible].copy()
        meta=dict(fit_id=f'{family}_{context}_{occ}_{model}_{info}',family=family,context=context,
            population=pop,occupancy=occ,model=model,information=info)
        jobs.append((meta,g,train,validation))
    for occ in [.4,.8,.95]:
        for model in MODELS:
            for info in MODES:add('core','walmart','base',occ,model,info,range(1000,1030),list(range(1000,1020)),list(range(1020,1030)))
    for occ in [.8,.95]:
        for model in MODELS:
            for info in MODES:
                for pop,family in [('base','matched_base'),('homogeneous_tastes','constant_preferences')]:
                    add(family,'walmart',pop,occ,model,info,range(1000,1010),list(range(1000,1006)),list(range(1006,1010)))
                add('transfer','synthetic','base',occ,model,info,range(1000,1030),list(range(1000,1020)),list(range(1020,1030)))
    for family in ['single_gaussian','single_skewed','curved_continuum','two_separated_groups']:
        for replicate in range(20):
            jobs.append((dict(fit_id=f'null_{family}_{replicate:02d}',family='null',context=family,replicate=replicate),None,list(range(6)),list(range(6,10))))
    assert len(jobs)==161
    return jobs

def summarize(out,jobs):
    diagnostic=pd.DataFrame([json.loads((out/'fits'/f'{j[0]["fit_id"]}.json').read_text()) for j in jobs])
    diagnostic.to_csv(out/'profile_diagnostics.csv',index=False)
    summaries=[];assignments=[];selection=[]
    for meta,_,_,_ in jobs:
        key=meta['fit_id']
        for suffix,target in [('assignments',assignments),('selection',selection)]:
            p=out/'fits'/f'{key}_{suffix}.csv'
            if p.exists() and p.stat().st_size>2:target.append(pd.read_csv(p))
    assigned=pd.concat(assignments,ignore_index=True)
    assigned.to_csv(out/'profile_assignments.csv.gz',index=False)
    pd.concat(selection,ignore_index=True).to_csv(out/'mixture_selection.csv',index=False)
    heldout=assigned[assigned.validation].copy()
    desc=heldout.groupby(['fit_id','behavior_regime']).agg(drivers=('driver','size'),search_s=('search_s','mean'),
        walk_m=('walk_m','mean'),walk_relative=('walk_relative','mean'),beta_walk=('beta_walk','mean'),
        beta_search=('beta_search','mean'),assignment_stability=('seed_bootstrap_jaccard','first')).reset_index()
    desc.to_csv(out/'heldout_profile_descriptions.csv',index=False)
    transfers=[]
    for family in ['core','transfer']:
        g=heldout[heldout.family==family]
        for model in MODELS:
            for info in MODES:
                for low,high in ([(.4,.8),(.8,.95)] if family=='core' else [(.8,.95)]):
                    a=g[(g.model==model)&(g.information==info)&np.isclose(g.occupancy,low)]
                    b=g[(g.model==model)&(g.information==info)&np.isclose(g.occupancy,high)]
                    pair=a.merge(b,on=['seed','driver'],suffixes=('_a','_b'),validate='one_to_one')
                    if len(pair):transfers.append(dict(family=family,model=model,information=info,occupancy_a=low,occupancy_b=high,
                        jointly_eligible_heldout=len(pair),components_a=a.behavior_regime.nunique(),components_b=b.behavior_regime.nunique(),
                        adjusted_rand=adjusted_rand_score(pair.behavior_regime_a,pair.behavior_regime_b)))
    pd.DataFrame(transfers).to_csv(out/'cross_occupancy_consistency.csv',index=False)
    a=diagnostic[diagnostic.family=='matched_base'];b=diagnostic[diagnostic.family=='constant_preferences']
    a.merge(b,on=['occupancy','model','information'],suffixes=('_varying','_constant'),validate='one_to_one').to_csv(out/'matched_preference_controls.csv',index=False)
    diagnostic[diagnostic.family=='null'].groupby('context').agg(datasets=('replicate','size'),
        screening_passes=('candidate_supported','sum'),mean_components=('selected_components','mean')).to_csv(out/'null_challenges.csv')
    summary=diagnostic.groupby('family').agg(fits=('fit_id','size'),screening_passes=('candidate_supported','sum'),
        min_components=('selected_components','min'),max_components=('selected_components','max'))
    summary.to_csv(out/'screening_summary.csv')
    print(summary.to_string(),flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'research/tcss/profile_reanalysis_20261030')
    parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--prepared',type=Path)
    args=parser.parse_args();out=args.output
    if out.exists() and not args.resume:raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=True);(out/'fits').mkdir(exist_ok=True)
    if args.prepared:
        records=pd.read_csv(args.prepared);sources={str(args.prepared):sha(args.prepared)}
    elif args.resume and (out/'prepared_records.csv.gz').exists():
        records=pd.read_csv(out/'prepared_records.csv.gz');sources=json.loads((out/'design.json').read_text())['input_sha256']
    else:records,sources=prepare_records()
    if not (out/'prepared_records.csv.gz').exists():records.to_csv(out/'prepared_records.csv.gz',index=False)
    jobs=job_list(records)
    plan=dict(status='frozen_before_profile_fitting',new_abm_simulations=0,unique_simulation_trials=1530,
        outcome_records=len(records),analysis_fits=81,null_datasets=80,features=['log1p(search_s)','log1p(walk_m/r_walk_m)'],
        settings=SETTINGS,core_training_seeds=list(range(1000,1020)),core_validation_seeds=list(range(1020,1030)),
        matched_control_training_seeds=list(range(1000,1006)),matched_control_validation_seeds=list(range(1006,1010)),
        sample='Parked drivers without walking limitation, accessible-space eligibility or a permit; exclusions retained separately.',
        support_gates=dict(components_above_one=True,bic_improvement_above=10,heldout_logscore_ci_lower_above=0,
            minimum_training_and_validation_mass=.05,minimum_mean_bootstrap_jaccard=.75,minimum_confident_posterior_fraction=.5,posterior_threshold=.8),
        interpretation='Exploratory density partitions, not validated human classes. Constant-preference controls remove taste-weight variation only; temperature, references and CPT draws can still vary. No outcome-dependent tuning.',
        input_sha256=sources,prepared_sha256=sha(out/'prepared_records.csv.gz'),
        analysis_source_sha256={str(Path(__file__).relative_to(ROOT)):sha(__file__),
            'panda_abm/analysis/profiles.py':sha(ROOT/'panda_abm/analysis/profiles.py')},
        environment=dict(python=platform.python_version(),packages={k:importlib.metadata.version(k) for k in ['numpy','pandas','scikit-learn','scipy','threadpoolctl']}))
    if (out/'design.json').exists():
        previous=json.loads((out/'design.json').read_text());assert previous['prepared_sha256']==plan['prepared_sha256'];assert previous['settings']==plan['settings']
    else:write_json(out/'design.json',plan)
    records.groupby(['context','population','occupancy','model','information','exclusion_reason']).size().rename('drivers').to_csv(out/'sample_accounting.csv')
    pending=[j for j in jobs if not (out/'fits'/f'{j[0]["fit_id"]}.json').exists()]
    print(f'Frozen {len(records):,} outcomes from 1,530 existing trials. Pending fits: {len(pending)} / {len(jobs)}.',flush=True)
    started=time.perf_counter();completed=len(jobs)-len(pending)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(evaluate,j):j[0]['fit_id'] for j in pending}
        for future in as_completed(futures):
            result,assigned,selection=future.result();key=result['fit_id']
            if not assigned.empty and result['family']!='null':assigned.to_csv(out/'fits'/f'{key}_assignments.csv',index=False)
            if not selection.empty:selection.to_csv(out/'fits'/f'{key}_selection.csv',index=False)
            write_json(out/'fits'/f'{key}.json',result);completed+=1
            print(f'{completed}/{len(jobs)} {key}: k={result["selected_components"]}, pass={result["candidate_supported"]}; {time.perf_counter()-started:.0f}s',flush=True)
    summarize(out,jobs)
    plan['status']='completed';plan['elapsed_seconds']=time.perf_counter()-started
    write_json(out/'design.json',plan)
    write_json(out/'output_sha256.json',{p.relative_to(out).as_posix():sha(p) for p in out.iterdir() if p.is_file() and p.name!='output_sha256.json'})

if __name__=='__main__':main()
