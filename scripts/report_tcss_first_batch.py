"""Seed-paired descriptive reporting for the versioned TCSS first batch."""
from pathlib import Path
from itertools import combinations
import argparse
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior.continuous import PREFERENCE_MEANS

METRICS={'mean_search_s':'seconds','success':'fraction','mean_walk_parked_m':'metres among parked',
         'mean_exit_parked_m':'metres among parked','claims_per_arrival':'claims per arrival'}


def interval(values):
    a=np.asarray(values,dtype=float)
    assert np.isfinite(a).all()
    draws=np.random.default_rng(20261028).choice(a,(10000,len(a)),replace=True).mean(axis=1)
    low,high=np.quantile(draws,[.025,.975])
    return float(a.mean()),float(low),float(high)


def save(frame,path):
    frame.to_csv(path.with_suffix('.csv'),index=False)
    fmt=frame.map(lambda v:f'{v:.4f}' if isinstance(v,float) else str(v))
    lines=['| '+' | '.join(fmt.columns)+' |','| '+' | '.join('---' for _ in fmt.columns)+' |']
    lines+=['| '+' | '.join(row)+' |' for row in fmt.itertuples(index=False,name=None)]
    path.with_suffix('.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    args=parser.parse_args();folder=args.input;out=folder/'analysis';out.mkdir(exist_ok=True)
    design=json.loads((folder/'design.json').read_text());assert design['status']=='completed'
    for name,digest in design['output_sha256'].items():assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
    population_checks=[]
    for stage in ('tastes','cpt_central'):
        for path in sorted((folder/stage/'populations').glob('*.json')):
            baseline=json.loads((folder/'core/populations'/path.name).read_text())
            controlled=json.loads(path.read_text())
            assert len(baseline['drivers'])==len(controlled['drivers'])
            for a,b in zip(baseline['drivers'],controlled['drivers']):
                assert a['attributes']==b['attributes']
                assert a['reference_points']==b['reference_points']
                if stage=='tastes':
                    assert a['cpt_parameters']==b['cpt_parameters']
                    expected=dict(a['behavioral_parameters'],**PREFERENCE_MEANS)
                    assert b['behavioral_parameters']==expected
                else:
                    assert a['behavioral_parameters']==b['behavioral_parameters']
                    assert b['cpt_parameters']==dict(alpha=.88,beta=.88,lambda_loss=2.25,gamma=.61,gamma_loss=.69)
            population_checks.append(dict(stage=stage,population=path.name,drivers=len(controlled['drivers']),passed=True,
                base_sha256=hashlib.sha256((folder/'core/populations'/path.name).read_bytes()).hexdigest(),
                control_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (out/'population_manipulation_checks.json').write_text(json.dumps(population_checks,indent=2),encoding='utf-8')
    runs=pd.read_csv(folder/'runs.csv');drivers=pd.read_csv(folder/'drivers.csv')
    runs['claims_per_arrival']=runs.lost_claims/runs.drivers
    save(runs.groupby(['variant','occupancy','model','information'])[list(METRICS)].mean().reset_index(),out/'cell_means')
    effects=[];series={}
    for (variant,occ,model),g in runs.groupby(['variant','occupancy','model']):
        for info in ('aisle','space'):
            for metric,unit in METRICS.items():
                paired=g.pivot(index='seed',columns='information',values=metric)
                delta=paired[info]-paired.unaided
                mean,lo,hi=interval(delta)
                effects.append(dict(variant=variant,occupancy=occ,model=model,information=info,metric=metric,
                    unit=unit,seeds=len(delta),delta=mean,ci_low=lo,ci_high=hi))
                series[(variant,occ,model,info,metric)]=delta
    save(pd.DataFrame(effects),out/'information_effects')
    controls=[]
    for variant in ('homogeneous_tastes','homogeneous_cpt'):
        for (occ,model,info),g in runs[runs.variant==variant].groupby(['occupancy','model','information']):
            base=runs[(runs.variant=='base')&(runs.occupancy==occ)&(runs.model==model)&(runs.information==info)]
            for metric,unit in METRICS.items():
                pair=g.set_index('seed')[metric].to_frame('control').join(base.set_index('seed')[metric].rename('base'),how='inner')
                mean,lo,hi=interval(pair.control-pair.base)
                controls.append(dict(variant=variant,occupancy=occ,model=model,information=info,metric=metric,
                    unit=unit,seeds=len(pair),control_minus_base=mean,ci_low=lo,ci_high=hi))
    save(pd.DataFrame(controls),out/'heterogeneity_controls')
    transforms=[]
    for (occ,info),g in runs[(runs.variant=='base')&(runs.model.isin(['cpt','linear_cpt']))].groupby(['occupancy','information']):
        if g.model.nunique()!=2:continue
        for metric,unit in METRICS.items():
            pair=g.pivot(index='seed',columns='model',values=metric)
            mean,lo,hi=interval(pair.cpt-pair.linear_cpt)
            transforms.append(dict(occupancy=occ,information=info,metric=metric,unit=unit,seeds=len(pair),
                cpt_minus_linear=mean,ci_low=lo,ci_high=hi))
    save(pd.DataFrame(transforms),out/'prospect_transform_effects')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':20,'font.weight':'bold','axes.labelweight':'bold',
        'axes.labelsize':20,'xtick.labelsize':18,'ytick.labelsize':18,'pdf.fonttype':42})
    fig,axes=plt.subplots(1,3,figsize=(16,6),sharey=True)
    order=[(occ,info) for occ in (.8,.95) for info in ('unaided','aisle','space')]
    transformation=pd.DataFrame(transforms).set_index(['occupancy','information','metric'])
    for ax,(metric,label,scale) in zip(axes,[('mean_search_s','Search time (s)',1),
            ('mean_walk_parked_m','Walking among parked (m)',1),('success','Parking success (pp)',100)]):
        rows=[transformation.loc[(occ,info,metric)] for occ,info in order]
        x=np.array([r.cpt_minus_linear for r in rows])*scale
        low=np.array([r.ci_low for r in rows])*scale;high=np.array([r.ci_high for r in rows])*scale
        ax.errorbar(x,np.arange(6),xerr=np.vstack((x-low,high-x)),fmt='o',color='#075b78',capsize=5,linewidth=2,markersize=8)
        ax.axvline(0,color='black',linewidth=1)
        ax.set_xlabel('CPT minus linear control\n'+label)
        ax.set_yticks(np.arange(6),[f'{occ:.0%} / {info}' for occ,info in order])
        ax.grid(axis='x',alpha=.2)
    axes[0].invert_yaxis();fig.tight_layout()
    for suffix in ('png','pdf'):fig.savefig(out/f'prospect_transform_effects.{suffix}',dpi=220,bbox_inches='tight')
    plt.close(fig)
    interactions=[]
    for occ in (.4,.8,.95):
        models=['deterministic','rum','cpt']+(['linear_cpt'] if occ!=.4 else [])
        for a,b in combinations(models,2):
            for info in ('aisle','space'):
                for metric,unit in METRICS.items():
                    x=series[('base',occ,a,info,metric)]-series[('base',occ,b,info,metric)]
                    mean,lo,hi=interval(x)
                    interactions.append(dict(occupancy=occ,model_a=a,model_b=b,information=info,metric=metric,
                        unit=unit,seeds=len(x),difference_of_effects=mean,ci_low=lo,ci_high=hi))
    save(pd.DataFrame(interactions),out/'model_information_interactions')
    choices=[]
    base=drivers[drivers.variant=='base']
    for occ in (.8,.95):
        a=base[(base.model=='cpt')&(base.occupancy==occ)]
        b=base[(base.model=='linear_cpt')&(base.occupancy==occ)]
        pair=a.merge(b,on=['seed','occupancy','information','driver'],suffixes=('_cpt','_linear'),validate='one_to_one')
        for (seed,info),g in pair.groupby(['seed','information']):
            both=g[g.success_cpt&g.success_linear]
            choices.append(dict(occupancy=occ,seed=seed,information=info,jointly_parked=len(both),
                same_stall=float((both.chosen_space_cpt==both.chosen_space_linear).mean()),
                same_aisle=float((both.chosen_aisle_cpt==both.chosen_aisle_linear).mean()),
                success_changed=float((g.success_cpt!=g.success_linear).mean())))
    save(pd.DataFrame(choices),out/'linear_cpt_choice_agreement')
    old=pd.read_csv(ROOT/'results/parking_information_20261028/drivers.csv')
    signatures=['success','search_s','search_distance_m','walk_m','chosen_space','lost_claims','parking_time_s']
    pair=base.merge(old,on=['seed','occupancy','model','information','driver'],suffixes=('_new','_old'),validate='one_to_one')
    comparisons=[]
    for name,g in pair.groupby('model'):
        equal=np.ones(len(g),dtype=bool)
        for key in signatures:
            equal &= ((g[key+'_new']==g[key+'_old'])|(g[key+'_new'].isna()&g[key+'_old'].isna())).to_numpy()
        comparisons.append(dict(model=name,matched_driver_records=len(g),identical_outcomes=int(equal.sum()),changed_outcomes=int((~equal).sum())))
    save(pd.DataFrame(comparisons),out/'pilot_version_comparison')
    # Original policies untouched by CPT semantics must retain their exact outcomes.
    assert all(r['changed_outcomes']==0 for r in comparisons if r['model'] in ('deterministic','rum'))
    inputs={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ('design.json','runs.csv','drivers.csv','checks.json')}
    (out/'provenance.json').write_text(json.dumps(dict(inputs=inputs,bootstrap_seed=20261028,bootstrap_draws=10000,
        pilot_drivers_sha256=hashlib.sha256((ROOT/'results/parking_information_20261028/drivers.csv').read_bytes()).hexdigest(),
        intervals='Exploratory paired-seed percentile intervals; pointwise, not multiplicity-adjusted.',
        report_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2),encoding='utf-8')
    print(json.dumps(dict(runs=len(runs),outcomes=len(drivers),version_comparison=comparisons),indent=2))


if __name__=='__main__':main()
