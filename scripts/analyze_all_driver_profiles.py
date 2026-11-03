"""Discover outcome-free decision-response profiles, then compare ALL ABM arrivals."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,hashlib,importlib.metadata,json,sys,time
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import adjusted_rand_score

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from panda_abm.analysis.response_profiles import MENUS,TIMES,FEATURES,response_fingerprint,fit_profiles,predict_profiles
from panda_abm.behavior.population import DriverAttributes,DriverSpec
from panda_abm.behavior.parameters import BehavioralParameters
from panda_abm.behavior.references import ReferencePoints
from panda_abm.behavior.cpt_parameters import CPTParameters

ARCHIVE=ROOT/'results/tcss_first_batch_20261028'
MODELS=['deterministic','rum','cpt'];TRAIN=list(range(1000,1020));VALID=list(range(1020,1030))

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,data):Path(p).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def driver_from_dict(d):
    assert d['attributes']['persona'] is None
    return DriverSpec(DriverAttributes(**d['attributes']),BehavioralParameters(**d['behavioral_parameters']),
        ReferencePoints(**d['reference_points']),CPTParameters(**d['cpt_parameters']),d['cpt_parameter_source'])

def probe_batch(seed,model,population):
    rows=[];arrays={v:[] for v in ['primary','neutral','perturbed']}
    for d in population:
        driver=driver_from_dict(d);a=driver.attributes
        rows.append(dict(seed=seed,driver=a.driver_id,model=model,mobility_limited=a.mobility_limitation,
            eligible=a.accessibility_eligibility,permit=a.permit_type or '',max_walk_m=a.max_walking_distance_m,
            beta_walk=driver.behavioral_parameters.beta_walk,beta_exit=driver.behavioral_parameters.beta_exit,
            beta_search=driver.behavioral_parameters.beta_search,beta_availability=driver.behavioral_parameters.beta_availability,
            beta_approach=driver.behavioral_parameters.beta_approach,temperature=driver.behavioral_parameters.decision_temperature,
            loss_aversion=driver.cpt_parameters.lambda_loss,search_reference_s=driver.reference_points.r_search_s))
        for variant in arrays:arrays[variant].append(response_fingerprint(driver,model,variant))
    return rows,{v:np.array(a) for v,a in arrays.items()}

def fit_one(model,records,arrays,out):
    result,groups,confidence,selection,fitted=fit_profiles(arrays['primary'],records.seed.to_numpy(),TRAIN,VALID)
    a=records.copy();a['profile']=groups;a['confidence']=confidence;a['heldout']=a.seed.isin(VALID)
    a['supported']=result['supported'];a['probe_continue']=arrays['primary'][:,3::4].mean(axis=1)
    for variant in ['neutral','perturbed']:
        labels=predict_profiles(fitted,arrays[variant]);a[f'{variant}_profile']=labels
        result[f'{variant}_heldout_ari']=float(adjusted_rand_score(groups[a.heldout],labels[a.heldout]))
    a.to_csv(out/f'{model}_assignments.csv',index=False)
    pd.DataFrame(selection).to_csv(out/f'{model}_selection.csv',index=False)
    joblib.dump(fitted,out/f'{model}_fitted.joblib')
    dump(out/f'{model}_diagnostics.json',result)
    return model,result

def bootstrap(values,rng):
    x=np.array(values,dtype=float);x=x[np.isfinite(x)]
    if not len(x):return np.nan,np.nan,np.nan,0
    samples=x[rng.integers(len(x),size=(10000,len(x)))].mean(axis=1)
    return float(x.mean()),float(np.quantile(samples,.025)),float(np.quantile(samples,.975)),len(x)

def outcomes(out,labels):
    design=json.loads((ARCHIVE/'design.json').read_text())
    assert sha(ARCHIVE/'drivers.csv')==design['output_sha256']['drivers.csv']
    x=pd.read_csv(ARCHIVE/'drivers.csv');x=x[(x.variant=='base')&x.model.isin(MODELS)].copy()
    assert len(x)==64800 and x.groupby(['seed','occupancy','model','information']).size().eq(80).all()
    assert not x.duplicated(['seed','occupancy','model','information','driver']).any()
    x=x.merge(labels[['seed','model','driver','profile','heldout','supported']],on=['seed','model','driver'],validate='many_to_one',how='left')
    assert x.profile.notna().all()
    x.to_csv(out/'all_arrivals_with_profiles.csv.gz',index=False)
    rng=np.random.default_rng(20261102);cells=[];effects=[];units=[]
    for split,seeds in [('heldout',VALID),('all',TRAIN+VALID)]:
        sample=x[x.seed.isin(seeds)].copy()
        # Profile 0 is the all-arrival comparator, not a discovered group.
        sample=pd.concat([sample,sample.assign(profile=0)],ignore_index=True)
        for keys,g in sample.groupby(['model','occupancy','information','profile','seed']):
            model,occ,info,profile,seed=keys;parked=g[g.success]
            measures={'success_pct':100*g.success.mean(),'mean_search_s':g.search_s.mean(),
                'failed_claims_per_arrival':g.lost_claims.mean(),'walking_m_parked':parked.walk_m.mean(),
                'exit_m_parked':parked.exit_distance_m.mean(),'search_s_parked':parked.search_s.mean(),
                'search_s_abandoned':g.loc[~g.success,'search_s'].mean()}
            for metric,value in measures.items():cells.append(dict(split=split,model=model,occupancy=occ,information=info,
                profile=profile,seed=seed,metric=metric,value=value,arrivals=len(g),parked=len(parked)))
        base=sample[sample.information=='unaided']
        for info in ['aisle','space']:
            pair=sample[sample.information==info].merge(base,on=['seed','driver','model','occupancy','profile'],suffixes=('_info','_base'),validate='one_to_one')
            assert len(pair)==len(base)
            for keys,g in pair.groupby(['model','occupancy','profile','seed']):
                model,occ,profile,seed=keys;both=g[g.success_info&g.success_base]
                gain=100*(g.success_info&~g.success_base).mean();loss=100*(~g.success_info&g.success_base).mean()
                metrics={'success_pp':100*(g.success_info.astype(int)-g.success_base.astype(int)).mean(),
                    'search_s':(g.search_s_info-g.search_s_base).mean(),
                    'failed_claims_per_arrival':(g.lost_claims_info-g.lost_claims_base).mean(),
                    'success_gain_pp':gain,'success_loss_pp':loss,
                    'walking_m_both_parked':(both.walk_m_info-both.walk_m_base).mean(),
                    'exit_m_both_parked':(both.exit_distance_m_info-both.exit_distance_m_base).mean(),
                    'search_s_both_parked':(both.search_s_info-both.search_s_base).mean(),
                    'search_and_oneway_walk_s_both_parked':((both.search_s_info-both.search_s_base)+(both.walk_m_info-both.walk_m_base)/1.4).mean(),
                    'search_and_roundtrip_walk_s_both_parked':((both.search_s_info-both.search_s_base)+2*(both.walk_m_info-both.walk_m_base)/1.4).mean()}
                assert np.isclose(metrics['success_pp'],gain-loss)
                for metric,value in metrics.items():units.append(dict(split=split,model=model,occupancy=occ,information=info,
                    profile=profile,seed=seed,metric=metric,value=value,arrivals=len(g),both_parked=len(both)))
    cell=pd.DataFrame(cells);cell.to_csv(out/'profile_cells_by_seed.csv',index=False)
    units=pd.DataFrame(units);units.to_csv(out/'information_effects_by_seed.csv',index=False)
    for table,name in [(cell,'profile_outcomes.csv'),(units,'information_effects.csv')]:
        summary=[]
        for keys,g in table.groupby(['split','model','occupancy','information','profile','metric']):
            mean,lo,hi,n=bootstrap(g.value,rng)
            summary.append(dict(zip(['split','model','occupancy','information','profile','metric'],keys))|dict(mean=mean,ci_low=lo,ci_high=hi,seeds=n,total_arrivals=int(g.arrivals.sum())))
        pd.DataFrame(summary).to_csv(out/name,index=False)
    # Direct paired differences in information effects, not comparisons of separate CIs.
    interactions=[]
    for keys,g in units.groupby(['split','model','occupancy','information','metric']):
        wide=g.pivot(index='seed',columns='profile',values='value')
        for profile in wide.columns:
            if profile==0:continue
            delta=wide[profile]-wide[0];mean,lo,hi,n=bootstrap(delta,rng)
            interactions.append(dict(zip(['split','model','occupancy','information','metric'],keys))|
                dict(profile=profile,comparison='profile_effect_minus_overall_effect',mean=mean,ci_low=lo,ci_high=hi,seeds=n))
    pd.DataFrame(interactions).to_csv(out/'profile_information_interactions.csv',index=False)
    return x

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,default=ROOT/'research/tcss/all_driver_profiles_20261102')
    ap.add_argument('--workers',type=int,default=3);ap.add_argument('--resume',action='store_true');args=ap.parse_args();out=args.output
    if out.exists() and not args.resume:raise FileExistsError(out)
    out.mkdir(exist_ok=True,parents=True);cache=out/'cache';cache.mkdir(exist_ok=True)
    archive_design=json.loads((ARCHIVE/'design.json').read_text());sources={};populations={}
    for name,h in archive_design['source_sha256'].items():
        if name.startswith('panda_abm/behavior/decision/') or name.endswith(('behavior/parameters.py','behavior/references.py','environment/parking_space.py')):
            assert sha(ROOT/name)==h,name;sources[name]=h
    for seed in TRAIN+VALID:
        drivers=[]
        for occ in [.4,.8,.95]:
            p=ARCHIVE/'core/populations'/f'{seed}_{occ}.json';data=json.loads(p.read_text())['drivers']
            sources[p.relative_to(ROOT).as_posix()]=sha(p)
            if drivers:assert drivers==data,'Population changes across occupancy'
            drivers=data
        assert len(drivers)==80 and all(d['attributes']['persona'] is None for d in drivers)
        populations[seed]=drivers
    sources['results/tcss_first_batch_20261028/drivers.csv']=sha(ARCHIVE/'drivers.csv')
    assert sources['results/tcss_first_batch_20261028/drivers.csv']==archive_design['output_sha256']['drivers.csv']
    plan=dict(status='frozen_before_probe_generation',date='2026-11-02',new_abm_simulations=0,existing_trials=810,
        unique_drivers=2400,outcome_records=64800,models=MODELS,menus=MENUS,elapsed_probe_times=TIMES,features=FEATURES,
        primary='Implemented final-version decision rules; actual constraints; expected final action probabilities; no sampled-action noise.',
        validation='Fit on seeds 1000--1019, outcomes assessed on 1020--1029; all-30-seed descriptive results also supplied.',
        selection=dict(k_range=[1,6],pca_variance=.95,pca_max_dimensions=6,n_init=5,bootstrap_refits=20,
            bic_improvement=10,minimum_group_mass=.05,minimum_mean_jaccard=.75,posterior_threshold=.8,minimum_confident_fraction=.5,
            heldout_logscore_bootstrap=5000,outcome_bootstrap=10000),
        limitations='Exploratory profiles of controlled decision responses, not empirical human personas. Known aggregate outcomes were previously inspected. Group labels are model-specific and fixed across information/occupancy by design. Components at upper bound do not establish an exact number of types.',
        input_sha256=sources,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'panda_abm/analysis/response_profiles.py']},
        packages={p:importlib.metadata.version(p) for p in ['numpy','pandas','scikit-learn','scipy','joblib']})
    if (out/'design.json').exists():
        old=json.loads((out/'design.json').read_text());assert old['input_sha256']==sources
        assert old['selection']==plan['selection'] and old['menus']==json.loads(json.dumps(MENUS))
    else:dump(out/'design.json',plan)
    jobs=[(s,m,populations[s]) for s in TRAIN+VALID for m in MODELS if not (cache/f'{s}_{m}.npz').exists()]
    start=time.perf_counter();print(f'Frozen design: 2,400 drivers, all constraints retained; {len(jobs)} probe batches pending.',flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(probe_batch,*j):(j[0],j[1]) for j in jobs}
        for i,future in enumerate(as_completed(futures)):
            seed,model=futures[future];rows,arrays=future.result()
            np.savez_compressed(cache/f'{seed}_{model}.npz',**arrays);dump(cache/f'{seed}_{model}.json',rows)
            print(f'Probes {i+1}/{len(jobs)}: seed {seed}, {model}; {time.perf_counter()-start:.0f}s',flush=True)
    frames={};all_arrays={}
    for model in MODELS:
        frames[model]=pd.DataFrame([row for seed in TRAIN+VALID for row in json.loads((cache/f'{seed}_{model}.json').read_text())])
        all_arrays[model]={v:np.vstack([np.load(cache/f'{s}_{model}.npz')[v] for s in TRAIN+VALID]) for v in ['primary','neutral','perturbed']}
        np.savez_compressed(out/f'{model}_response_features.npz',**all_arrays[model])
        frames[model].to_csv(out/f'{model}_driver_inputs.csv',index=False)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(fit_one,m,frames[m],all_arrays[m],out) for m in MODELS if not (out/f'{m}_diagnostics.json').exists()]
        for f in as_completed(futures):
            m,d=f.result();print(f'{m}: {d["components"]} candidate groups, supported={d["supported"]}, min Jaccard={d["min_bootstrap_jaccard"]:.3f}',flush=True)
    labels=pd.concat([pd.read_csv(out/f'{m}_assignments.csv',keep_default_na=False) for m in MODELS],ignore_index=True)
    labels.to_csv(out/'all_driver_profile_assignments.csv',index=False)
    x=outcomes(out,labels)
    assert len(x[x.heldout])==21600 and len(x[~x.success])>0
    dump(out/'verification.json',dict(all_64800_records_retained=True,all_21600_heldout_records_retained=True,
        unsuccessful_records=int((~x.success).sum()),walking_limited_records=int(x.mobility_limited.sum()),
        eligible_records=int(x.eligible.sum()),unmatched_profile_records=int(x.profile.isna().sum()),
        profiles_fixed_across_information_and_occupancy=True,new_abm_simulations=0))
    plan['status']='completed';plan['elapsed_seconds']=time.perf_counter()-start;dump(out/'design.json',plan)
    dump(out/'output_sha256.json',{p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='output_sha256.json'})
    print('Completed all-driver profiling and matched outcome comparisons.',flush=True)

if __name__=='__main__':main()
