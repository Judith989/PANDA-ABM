"""Explore post-simulation regimes with held-out seeds and homogeneous nulls."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score
from panda_abm.analysis.profiles import explore_behavioral_regimes


def bootstrap_contrast(values):
    values=np.asarray(values,float);rng=np.random.default_rng(20261027)
    bootstrap=values[rng.integers(len(values),size=(5000,len(values)))].mean(axis=1)
    low,high=np.quantile(bootstrap,[.025,.975])
    return float(values.mean()),float(low),float(high)


def summarize_models(drivers):
    """Do not count an abandoned driver's unobserved walk as zero benefit."""
    observed=drivers.assign(walk_m=drivers.walk_m.where(drivers.success))
    return observed.groupby(['scenario','population','model']).agg(drivers=('driver','count'),parked=('success','sum'),
        success=('success','mean'),mean_search_s=('search_s','mean'),mean_walk_parked_m=('walk_m','mean'),
        violations=('violation','sum'),mean_rejected_candidates=('rejected_candidates','mean')).reset_index()


def compare_models(out,drivers,runs):
    records=[];pairs=[]
    for population in ('heterogeneous','homogeneous'):
        cpt=drivers[(drivers.model=='cpt') & (drivers.population==population)]
        for other in ('deterministic','rum'):
            b=drivers[(drivers.model==other) & (drivers.population==population)]
            p=cpt.merge(b,on=['scenario','seed','driver','population'],suffixes=('_cpt','_other'),validate='one_to_one')
            p['comparison']='cpt_vs_'+other;p['both_parked']=p.success_cpt & p.success_other
            p['same_space']=p.both_parked & (p.chosen_space_cpt==p.chosen_space_other)
            pairs.append(p)
            for scenario,g in p.groupby('scenario'):
                seed_effects=g.groupby('seed').apply(lambda x:pd.Series(dict(
                    success=float(x.success_cpt.mean()-x.success_other.mean()),
                    search=float((x.search_s_cpt-x.search_s_other).mean()))),include_groups=False)
                a=bootstrap_contrast(seed_effects.success);b=bootstrap_contrast(seed_effects.search)
                both=g[g.both_parked]
                records.append(dict(scenario=scenario,population=population,comparison='cpt_vs_'+other,
                    seeds=len(seed_effects),drivers=len(g),success_delta=a[0],success_ci_low=a[1],success_ci_high=a[2],
                    search_delta_s=b[0],search_ci_low=b[1],search_ci_high=b[2],both_parked=len(both),same_space=both.same_space.mean(),
                    absolute_walk_delta_m=(both.walk_m_cpt-both.walk_m_other).abs().mean()))
    pd.concat(pairs,ignore_index=True).to_csv(out/'paired_models.csv',index=False)
    pd.DataFrame(records).to_csv(out/'model_contrasts.csv',index=False)
    p=runs[runs.population=='heterogeneous'].merge(runs[runs.population=='homogeneous'],on=['scenario','seed','model'],suffixes=('_het','_hom'),validate='one_to_one')
    contrasts=[]
    for (scenario,model),g in p.groupby(['scenario','model']):
        a=bootstrap_contrast(g.parked_het/g.drivers_het-g.parked_hom/g.drivers_hom)
        b=bootstrap_contrast(g.mean_search_s_het-g.mean_search_s_hom)
        contrasts.append(dict(scenario=scenario,model=model,success_delta=a[0],success_ci_low=a[1],success_ci_high=a[2],
            search_delta_s=b[0],search_ci_low=b[1],search_ci_high=b[2]))
    pd.DataFrame(contrasts).to_csv(out/'heterogeneity_contrasts.csv',index=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/continuous_population_20261027')
    args=parser.parse_args();out=args.output
    plan=json.loads((out/'design.json').read_text())
    drivers=pd.read_csv(out/'drivers.csv');runs=pd.read_csv(out/'runs.csv')
    assert drivers.persona.isna().all()
    expected=len(plan['seeds'])*len(plan['scenarios'])*6
    assert len(runs)==expected
    checks=json.loads((out/'checks.json').read_text());assert len(checks)==expected
    assert all(all(row[k] for k in ('no_double_claims','finite','terminal','elapsed_identity','legal_if_required')) for row in checks)
    assert runs.groupby(['scenario','seed','population']).population_sha256.nunique().max()==1
    compare_models(out,drivers,runs)
    descriptive=summarize_models(drivers)
    descriptive.to_csv(out/'model_summary.csv',index=False)
    drivers['analysis_eligible']=drivers.success & ~drivers.eligible & ~drivers.mobility_limited & drivers.permit.isna()
    drivers['exclusion_reason']=np.select([~drivers.success,drivers.mobility_limited,drivers.eligible,drivers.permit.notna()],
        ['not_parked','mobility_constraint','accessible_eligibility','permit'],'included')
    drivers.groupby(['scenario','population','model','exclusion_reason']).size().reset_index(name='drivers').to_csv(out/'profile_sample_accounting.csv',index=False)
    selected=drivers[drivers.analysis_eligible].copy()
    summaries=[];assignments=[];selections=[]
    cp=plan['clustering']
    for (scenario,population,model),g in selected.groupby(['scenario','population','model']):
        result,assigned,selection=explore_behavioral_regimes(g,cp['train_seeds'],cp['validation_seeds'],
            n_init=cp['settings']['n_init'],bootstrap_repetitions=20,
            min_train=cp['minimum_train'],min_validation=cp['minimum_validation'])
        metadata=dict(scenario=scenario,population=population,model=model)
        summaries.append(dict(**metadata,**result))
        if len(assigned):assignments.append(assigned)
        if len(selection):
            for key,value in metadata.items():selection[key]=value
            selections.append(selection)
        pd.DataFrame(summaries).to_csv(out/'profile_diagnostics.csv',index=False)
        print(f'{scenario}/{population}/{model}: k={result["selected_components"]}, supported={result["candidate_supported"]}, status={result["status"]}',flush=True)
    diagnostics=pd.DataFrame(summaries)
    null=diagnostics[diagnostics.population=='homogeneous'][['scenario','model','candidate_supported','selected_components']].rename(
        columns={'candidate_supported':'homogeneous_candidate_supported','selected_components':'homogeneous_components'})
    comparison=diagnostics[diagnostics.population=='heterogeneous'].merge(null,on=['scenario','model'],validate='one_to_one')
    comparison['heterogeneity_specific_candidate']=comparison.candidate_supported & ~comparison.homogeneous_candidate_supported
    comparison.to_csv(out/'profile_null_comparison.csv',index=False)
    if assignments:
        a=pd.concat(assignments,ignore_index=True)
        a.to_csv(out/'posthoc_profile_assignments.csv',index=False)
        validation=a[a.validation]
        features=['search_s','walk_m','walk_relative','rejected_decisions','nonempty_scans','module_switches',
            'beta_walk','beta_search','beta_price','beta_availability','beta_risk','beta_approach','beta_exit',
            'decision_temperature','cpt_lambda_loss','violation','lost_claims']
        centroids=validation.groupby(['scenario','population','model','behavior_regime'])[features].mean()
        centroids['drivers']=validation.groupby(['scenario','population','model','behavior_regime']).size()
        centroids['seed_bootstrap_jaccard']=validation.groupby(['scenario','population','model','behavior_regime']).seed_bootstrap_jaccard.first()
        centroids.reset_index().to_csv(out/'heldout_profile_descriptions.csv',index=False)
        transfers=[]
        for (population,model),g in validation.groupby(['population','model']):
            x=g[g.scenario=='walmart_crowded'];y=g[g.scenario=='walmart_saturated']
            both=x.merge(y,on=['seed','driver'],suffixes=('_crowded','_saturated'),validate='one_to_one')
            if len(both)>=30:
                transfers.append(dict(population=population,model=model,matched_heldout_drivers=len(both),
                    adjusted_rand=adjusted_rand_score(both.behavior_regime_crowded,both.behavior_regime_saturated)))
        pd.DataFrame(transfers).to_csv(out/'cross_occupancy_profile_stability.csv',index=False)
    if selections:pd.concat(selections,ignore_index=True).to_csv(out/'mixture_model_selection.csv',index=False)
    scripts=[Path(__file__),ROOT/'panda_abm/analysis/profiles.py']
    (out/'analysis_source_sha256.json').write_text(json.dumps({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in scripts},indent=2)+'\n')
    print(descriptive.to_string(index=False))


if __name__=='__main__':main()
