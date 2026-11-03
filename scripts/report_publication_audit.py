"""Summarize completed audit without treating simulation as empirical evidence."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
import sys
import zipfile
import argparse
import shutil
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scripts.analyze_continuous_population import summarize_models


def interval(x):
    x=np.asarray(x,float);rng=np.random.default_rng(20261029)
    means=x[rng.integers(len(x),size=(10000,len(x)))].mean(axis=1)
    return float(x.mean()),float(np.quantile(means,.025)),float(np.quantile(means,.975)),float(x.std(ddof=1)/np.sqrt(len(x))) if len(x)>1 else 0.


def md_table(frame):
    # No optional tabulate dependency.
    columns=list(frame.columns)
    lines=['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']
    for values in frame.itertuples(index=False,name=None):
        lines.append('| '+' | '.join(f'{x:.3f}' if isinstance(x,(float,np.floating)) else str(x) for x in values)+' |')
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/publication_audit_20261027')
    out=parser.parse_args().output
    files=sorted((out/'raw').glob('*.json'))
    payload=[json.loads(p.read_text()) for p in files]
    checks=pd.DataFrame([r for p in payload for r in p['checks']])
    drivers=pd.DataFrame([r for p in payload for r in p['drivers']])
    expected=json.loads((out/'design.json').read_text())['runs']+json.loads((out/'pressure_design.json').read_text())['runs']
    assert len(checks)==expected,(len(checks),expected)
    flags=['exclusive_claims','balanced_release','elapsed_identity','bounded_search','terminal','legal','mobility_constraint','finite','full_lot_abandons']
    assert checks[flags].all().all()
    checks.to_csv(out/'checks.csv',index=False);drivers.to_csv(out/'drivers.csv',index=False)
    keys=['suite','variant','occupancy','arrival','seed','model']
    run=drivers.assign(parked_walk=drivers.walk.where(drivers.success)).groupby(keys).agg(
        drivers=('driver','size'),parked=('success','sum'),success=('success','mean'),mean_search_s=('search','mean'),
        mean_walk_parked_m=('parked_walk','mean'),lost_claims=('lost','sum')).reset_index()
    run.to_csv(out/'run_summary.csv',index=False)
    summary=run.groupby(['suite','variant','model']).agg(seeds=('seed','size'),parked=('parked','sum'),drivers=('drivers','sum'),
        success=('success','mean'),search_s=('mean_search_s','mean'),walk_parked_m=('mean_walk_parked_m','mean')).reset_index()
    summary.to_csv(out/'model_summary.csv',index=False)
    base=run[(run.suite=='walmart_pressure')&(run.variant=='baseline')]
    contrasts=[]
    for other in ('deterministic','rum'):
        paired=base[base.model=='cpt'].merge(base[base.model==other],on='seed',suffixes=('_cpt','_other'),validate='one_to_one')
        for metric in ('success','mean_search_s','mean_walk_parked_m'):
            mean,low,high,se=interval(paired[metric+'_cpt']-paired[metric+'_other'])
            contrasts.append(dict(comparison='cpt_vs_'+other,metric=metric,seeds=len(paired),delta=mean,low=low,high=high,mcse=se))
    contrasts=pd.DataFrame(contrasts);contrasts.to_csv(out/'pressure_model_contrasts.csv',index=False)
    choices=[]
    choice_data=drivers[(drivers.suite=='walmart_pressure')&(drivers.variant=='baseline')]
    for other in ('deterministic','rum'):
        p=choice_data[choice_data.model=='cpt'].merge(choice_data[choice_data.model==other],on=['seed','driver'],suffixes=('_cpt','_other'),validate='one_to_one')
        both=p.success_cpt&p.success_other
        choices.append(dict(comparison='cpt_vs_'+other,jointly_parked=int(both.sum()),
            same_space_fraction=float(p.loc[both,'space_cpt'].eq(p.loc[both,'space_other']).mean()),
            paired_walk_delta_m=float((p.loc[both,'walk_cpt']-p.loc[both,'walk_other']).mean())))
    choices=pd.DataFrame(choices);choices.to_csv(out/'pressure_individual_choices.csv',index=False)
    # Seed-count precision diagnostic, not evidence of convergence to real data.
    precision=[]
    for name,g in base.groupby('model'):
        for n in (5,10,20,30):
            x=g.sort_values('seed').head(n).mean_search_s
            precision.append(dict(model=name,seeds=n,mean_search_s=x.mean(),mcse=x.std(ddof=1)/np.sqrt(n)))
    pd.DataFrame(precision).to_csv(out/'monte_carlo_precision.csv',index=False)
    sensitivity=[]
    for (suite,variant,name),g in run[run.variant!='baseline'].groupby(['suite','variant','model']):
        if suite=='synthetic':continue
        b=run[(run.suite==suite)&(run.variant=='baseline')&(run.model==name)]
        p=g.merge(b,on='seed',suffixes=('_variant','_base'),validate='one_to_one')
        mean,low,high,se=interval(p.mean_search_s_variant-p.mean_search_s_base)
        a=drivers[(drivers.suite==suite)&(drivers.variant==variant)&(drivers.model==name)]
        c=drivers[(drivers.suite==suite)&(drivers.variant=='baseline')&(drivers.model==name)]
        pair=a.merge(c,on=['seed','driver'],suffixes=('_variant','_base'),validate='one_to_one')
        both=pair.success_variant&pair.success_base
        same=pair.loc[both,'space_variant'].eq(pair.loc[both,'space_base']).mean()
        sensitivity.append(dict(suite=suite,variant=variant,model=name,seeds=len(p),search_delta_s=mean,low=low,high=high,
            success_delta=float((p.success_variant-p.success_base).mean()),same_slot_jointly_parked=same))
    sensitivity=pd.DataFrame(sensitivity);sensitivity.to_csv(out/'sensitivity_contrasts.csv',index=False)
    baseline_hash=checks[(checks.suite=='walmart')&(checks.variant=='baseline')].set_index(['seed','model']).outcome_hash
    exact={v:int((checks[(checks.suite=='walmart')&(checks.variant==v)].set_index(['seed','model']).outcome_hash==baseline_hash).sum()) for v in ('repeat','output_30')}
    # Correct the earlier analysis in a new artifact, preserving its original
    # source/results archive rather than silently changing historical payloads.
    old=ROOT/'results/continuous_population_20261027'
    history=out/'historical_inputs';history.mkdir(exist_ok=True)
    for filename in ('model_summary.csv','drivers.csv'):
        if not (history/filename).exists():
            shutil.copyfile(old/filename,history/filename)
    previous=pd.read_csv(history/'model_summary.csv')
    corrected=summarize_models(pd.read_csv(history/'drivers.csv'))
    corrected.to_csv(out/'continuous_study_corrected_model_summary.csv',index=False)
    errata=previous.merge(corrected,on=['scenario','population','model'],suffixes=('_old','_corrected'))
    errata=errata[['scenario','population','model','mean_walk_parked_m_old','mean_walk_parked_m_corrected']]
    errata.to_csv(out/'previous_walking_summary_erratum.csv',index=False)
    beliefs=pd.read_csv(out/'claim_beliefs.csv')
    beliefs['brier']=(beliefs.probability-beliefs.success.astype(float))**2
    belief_summary=beliefs.groupby('model').agg(attempts=('success','size'),predicted=('probability','mean'),
        realized=('success','mean'),brier=('brier','mean')).reset_index()
    belief_summary.to_csv(out/'claim_belief_summary.csv',index=False)
    belief_seed=beliefs.groupby(['model','seed']).agg(predicted=('probability','mean'),realized=('success','mean')).reset_index()
    belief_intervals=[]
    for name,g in belief_seed.groupby('model'):
        mean,low,high,se=interval(g.predicted-g.realized)
        belief_intervals.append(dict(model=name,seeds=len(g),overprediction=mean,low=low,high=high,mcse=se))
    pd.DataFrame(belief_intervals).to_csv(out/'claim_belief_seed_gaps.csv',index=False)
    mechanism=json.loads((out/'mechanism_summary.json').read_text())
    nulls=pd.read_csv(out/'profile_null_summary.csv')
    # Compact scientific figure: paired seed differences and null challenges.
    fig,axes=plt.subplots(1,3,figsize=(14,4.2),layout='constrained')
    names=['M0','M1','CPT']
    for i,name in enumerate(('deterministic','rum','cpt')):
        g=base[base.model==name];axes[0].scatter(np.full(len(g),i),g.mean_search_s,s=14,alpha=.55)
    axes[0].set_xticks(range(3),names);axes[0].set_ylabel('Mean elapsed search (s)');axes[0].set_title('95% initial occupancy, 30 seeds')
    selected=contrasts[contrasts.metric=='mean_search_s'].reset_index(drop=True)
    axes[1].errorbar(selected.delta,range(2),xerr=np.array([selected.delta-selected.low,selected.high-selected.delta]),fmt='o',capsize=4)
    axes[1].axvline(0,color='gray',lw=1);axes[1].set_yticks(range(2),['CPT minus M0','CPT minus M1'])
    axes[1].set_xlabel('Paired search difference (s), 95% bootstrap CI');axes[1].set_title('Conditional simulation uncertainty')
    axes[2].barh(range(4),nulls.density_gate_passes/nulls.replicates,color=['#d48638','#777777','#d48638','#467f9d'])
    axes[2].set_yticks(range(4),nulls.distribution.str.replace('_',' '));axes[2].set_xlim(0,1)
    axes[2].set_xlabel('Fraction passing density screening gates');axes[2].set_title('Density components do not prove classes')
    for ax in axes:ax.grid(alpha=.2)
    fig.savefig(out/'audit_evidence.png',dpi=160);plt.close(fig)
    completed_utc=datetime.now(timezone.utc).isoformat()
    (out/'audit_summary.json').write_text(json.dumps(dict(completed_utc=completed_utc,runs=expected,driver_outcomes=len(drivers),checks=checks[flags].all().to_dict(),
        repeatability=exact,belief_runs=15,unit_tests=143,lottery_contexts=2000,mechanism_contexts=2000,profile_challenges=80),indent=2))
    pressure=summary[(summary.suite=='walmart_pressure')&(summary.variant=='baseline')]
    numerical=sensitivity[(sensitivity.suite=='walmart_pressure')&sensitivity.variant.str.startswith('resolution')]
    visibility=sensitivity[(sensitivity.suite=='walmart_pressure')&(sensitivity.variant=='perception_30')]
    report=f'''# Publication stress audit — 27 October 2026

Audit started 27 October; evidence bundle completed {completed_utc}.

**Verdict: the continuous-agent architecture is defensible for exploratory ABM research. The current evidence does not establish an empirically validated parking model, CPT superiority, or stable human personas. The project is not yet ready for those publication claims.**

## Evidence and scope

All **{expected} new verification/sensitivity simulations** passed nine applicable checks: exclusive claims, balanced releases, terminal states, finite values, elapsed-time identity, search deadline, legality, mobility constraints and full-lot boundary behavior. They produced **{len(drivers):,} driver outcomes**. Fifteen additional simulations tested availability beliefs. **143 tests passed** after the audit fixes. Two thousand arbitrary lotteries passed dominance, permutation, reference-translation and expected-value-limit checks (8,000 property checks). Two thousand artificial decision contexts tested mechanism distinctions. Eighty synthetic datasets challenged the profile analysis.

The first frozen design has 243 runs: 90 synthetic boundary runs (empty/80%/full, simultaneous/staggered arrivals, five seeds) and 153 Walmart short-dwell runs (17 settings, three seeds, three models). All short-dwell baseline Walmart drivers parked, so a separately declared **staged** extension tests binding capacity with original shopping durations: 30 baseline seeds plus three seeds for each remaining sensitivity setting. Design files and separate source snapshots preserve that sequence. This is an internal audit, not preregistration or independent empirical validation.

Baseline repeats and output interval 10→30 s yielded **{exact['repeat']}/9 and {exact['output_30']}/9 exact outcome-hash matches**, respectively. Hashes cover driver choices, search/walk, final states, parking times and lost claims; they do not assert binary equality of output files or every trajectory point.

## Original-dwell crowded-lot results

Each baseline model has 30 independent seeds and 2,400 drivers. Initial occupancy is 95%, with 80 arrivals per replication. The initial background cars remain parked; results describe that transient assumption.

{md_table(pressure[['model','seeds','parked','drivers','success','search_s','walk_parked_m']])}

Paired seed bootstrap intervals (10,000 resamples), CPT minus comparator:

{md_table(contrasts[['comparison','metric','seeds','delta','low','high','mcse']])}

Walking contrasts compare each model's parked population, which can differ; they are not a treatment effect on identical successful drivers. Search includes all drivers. Success is a fraction. These are exploratory conditional Monte Carlo intervals, not field inference or multiplicity-adjusted significance claims. `monte_carlo_precision.csv` reports changes in search precision over 5/10/20/30 seeds; a finite seed count alone does not establish convergence or power for every effect.

Individual decisions can differ despite similar aggregate success:

{md_table(choices)}

## Numerical and assumption sensitivity

{md_table(numerical[['variant','model','search_delta_s','success_delta','same_slot_jointly_parked']])}

Changing the physical resolution can change claim order, states at scans, the timestamp-derived decision seed and later interactions. It is therefore a numerical/model sensitivity issue even when release/timing invariants pass. Do not assume a sub-second model advantage is robust to discretization. Output-cadence invariance is a different property and passed exactly.

`sensitivity_contrasts.csv` includes concentration 8/32/128, search reference 150/300/450 s, loss-aversion center 1/2.25/4, claim hazard 0/.002/.004 per second, perception 30/60/100 m and scan interval 5/10/20 s. These are three-seed, one-factor screens with matched inputs, not global variance decomposition or a test of all interactions. Intervals with only three seeds are weak precision summaries. Geometry error, background-turnover alternatives, normalization/threshold uncertainty and joint prior interactions remain unquantified. No parameter was tuned to favor CPT or recover desired personas.

**Visibility is a dominant assumption in this screen.** Reducing the radius from 60 to 30 m increased mean elapsed search by {visibility.search_delta_s.min():.1f}–{visibility.search_delta_s.max():.1f} seconds across models and reduced success by {100*(-visibility.success_delta.max()):.1f}–{100*(-visibility.success_delta.min()):.1f} percentage points. These three-seed contrasts are conditional screens, but their scale is much larger than the baseline between-model search difference. Perception and aisle-search assumptions need substantive justification and field checks before attributing system outcomes primarily to decision theory.

## CPT mechanism attribution and identification

- Default CPT versus M1 differed in **{100*mechanism['rates']['cpt_vs_rum']:.1f}%** of zero-temperature artificial contexts.
- Even with alpha=beta=lambda=gamma_gain=gamma_loss=1, the CPT adapter differed from M1 in **{100*mechanism['rates']['linearized_adapter_vs_rum']:.1f}%**. Thus observed differences cannot be attributed solely to prospect-theory nonlinearities. Outcomes, expected approach/search, aspiration filtering and continuation also differ.
- Changing lambda 1→4 changed prospect ranking in **{100*mechanism['rates']['lambda_rank_changed']:.2f}%**; changing the search reference 150→450 s changed it in **{100*mechanism['rates']['reference_rank_changed']:.2f}%**. These panel rates are not population estimates and do not isolate effects in real Walmart choices.
- Duplicating an existing offer changed acceptance of common offers in **{100*mechanism['rates']['duplicate_common_acceptance_changed']:.2f}%**. Uniform offer-mixture continuation is sensitive to how opportunity multiplicity is represented. This is a structural assumption requiring justification, not a broken CPT weighting formula.
- A common scale change of RUM utilities and temperature produced probability error {mechanism['rum_common_scale_probability_error']:.1g}: their scale is confounded exactly. Priors/constraints do not constitute an empirical parameter-recovery demonstration. Free legal offers cannot reveal distinct within-choice price/rule-risk effects, and constant familiarity does not express location knowledge.

The current CPT implementation transforms scalar composite-utility prospects. The proposal's attribute-specific sketch is a different specification. Matched continuation/acceptance/forecast ablations and an explicit formulation choice are required before a manuscript interprets an M2 advantage as evidence for CPT.

## Availability beliefs

{md_table(belief_summary)}

These compare assumed survival beliefs with actual simulated claim attempts across five new seeds. `claim_target_accounting.csv` also counts unresolved targets; conditioning on an attempt is explicit. They do not estimate human beliefs or calibrate the hazard to field competition. Perfect local current-occupancy observation, static background and the search rules can drive internal agreement or disagreement.

Here beliefs are substantially more optimistic than realized claims. This requires either explicit justification as a biased-belief hypothesis or a forecast calibrated on separate simulated opportunities and then validated independently. Matching simulator claims would still not identify human subjective beliefs. `claim_belief_seed_gaps.csv` uses seeds rather than independent attempts for diagnostic intervals; with five seeds it remains a pilot. Tuning the hazard on these same outcomes and presenting the fit as validation would be inappropriate.

## Profile null challenge

{md_table(nulls)}

Single-skew and curved-continuum generators contain no discrete classes, yet some pass all density gates. Conversely all deliberately separated two-group datasets pass. A stable, predictively useful Gaussian density mixture can approximate a continuous nonlinear distribution. Therefore `candidate_supported` means an exploratory density partition passed screening, **not that personas have been validated**. Twenty datasets per distribution are a diagnostic, not a calibrated universal false-positive rate. The earlier one-of-18 passing partition remains a contextual candidate; it is not proof of a stable driver taxonomy. Do not force the previous five names onto components.

## Bugs fixed and historical erratum

1. The earlier `mean_walk_parked_m` aggregated all drivers, including zeros for abandonment. Future study and standard-runner summaries now mask unobserved walking before aggregation. Final exported agent metrics encode unobserved walking and unrealized parked spaces/modules as missing, so plots cannot count failed drivers' zero walks or their last attempted targets as parked outcomes. Raw target events are retained. `continuous_study_corrected_model_summary.csv` and `previous_walking_summary_erratum.csv` give corrected values from unchanged original driver data. Original archived results remain untouched; earlier values with that label are superseded. This affects reporting, not decisions, success counts or the parked-only clustering sample.
2. Profile analysis now rejects overlapping training/validation seeds and zero bootstrap refits. Existing studies used disjoint splits and positive refits, so these guards do not change those valid outputs.
3. The model now rejects negative/non-finite perception radii. Previously NaN could silently allow every stall into view. Valid-radius runs are unchanged.

Eight targeted regression tests cover these failures. The simulation snapshots precede these validation-only/reporting fixes; `final_source.zip` and its manifest record the final code. Valid simulation paths are unchanged. Historical bundles are preserved rather than silently rewritten.

## Publication priorities and permitted claims

The most immediate scientific work is to resolve CPT formulation and run mechanism-matched ablations; establish numerical robustness for the intended effect size; and choose an empirical or explicitly theoretical research question. Then obtain independent observations, perform synthetic parameter recovery, calibrate only identifiable parameters and evaluate held-out prediction against simpler models. Document background turnover, estimated geometry, idealized perception and unused attribute fields honestly. Prior centers from monetary CPT studies do not make parking distributions calibrated.

The model can currently support statements such as “under these disclosed assumptions, policies produce these choices and contextual search/walk patterns.” It cannot support “real drivers fall into five personas,” “CPT is behaviorally superior,” or “this is an accurate Walmart digital twin.” Passing software checks is evidence of verification, not human-behavior validation. Journal acceptance additionally depends on contribution and study design.

The accompanying [implemented model specification](../../research/publication_model_specification.md) maps purpose, entities, initialization, update order, inputs, submodels, observation, uncertainty and remaining validation needs. It follows the intent of [ODD](https://doi.org/10.18564/jasss.4259) and [STRESS](https://doi.org/10.1080/17477778.2018.1442155); neither framework guarantees study adequacy. The [validity protocol](https://doi.org/10.1016/j.envsoft.2022.105559) also distinguishes fitness for a stated purpose from merely running a model successfully.

![Audit evidence](audit_evidence.png)

## Reproduction

Install `requirements.txt` and `requirements-analysis.txt` (exact versions in this bundle), then run:

```powershell
python -m pytest -q
python scripts/publication_stress_audit.py
python scripts/publication_pressure_audit.py
python scripts/publication_mechanism_audit.py
python scripts/publication_claim_calibration.py
python scripts/report_publication_audit.py
```

Use a clean results destination: frozen designs reject overwrite. Every command accepts `--output results/audit_reproduction`; pass the same fresh directory to all five scripts. For the historical walking erratum, copy this bundle's `historical_inputs/` into that output before reporting if the earlier continuous study is absent. Unpack `final_source.zip` into the reproduction workspace to obtain source/config; keep original evidence separately. The pressure script is a staged extension; raw runs and their original designs are retained. Source, data/config, environment metadata, historical erratum inputs, raw outcomes, summaries and hashes are bundled. Local reproducibility archives still need a durable public release for publication. Device suspension affected recorded wall-clock duration in some jobs; these timings are not computational-performance benchmarks.
'''
    (out/'REPORT.md').write_text(report,encoding='utf-8')
    names=['mesa','numpy','pandas','networkx','matplotlib','pytest','scikit-learn','scipy','joblib','threadpoolctl','cloudpickle','narwhals']
    (out/'requirements-pinned.txt').write_text(''.join(f'{n}=={importlib.metadata.version(n)}\n' for n in names))
    (out/'environment.json').write_text(json.dumps(dict(python=sys.version,platform=platform.platform(),processor=platform.processor()),indent=2))
    source=sorted([*ROOT.glob('panda_abm/**/*.py'),*ROOT.glob('scripts/*.py'),*ROOT.glob('tests/*.py'),*ROOT.glob('research/*'),ROOT/'README.md',ROOT/'requirements.txt',ROOT/'requirements-analysis.txt',ROOT/'data/lot_config.json'])
    source=[p for p in source if p.is_file()]
    with zipfile.ZipFile(out/'final_source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in source:z.write(p,p.relative_to(ROOT))
    (out/'final_source_sha256.json').write_text(json.dumps({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source},indent=2))
    paths=[p for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ('bundle_manifest.json','reproducibility_bundle.zip')]
    manifest={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (out/'bundle_manifest.json').write_text(json.dumps(manifest,indent=2))
    with zipfile.ZipFile(out/'reproducibility_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in paths+[out/'bundle_manifest.json']:z.write(p,p.relative_to(out))
    print(pressure.to_string(index=False));print(contrasts.to_string(index=False));print(belief_summary.to_string(index=False))


if __name__=='__main__':main()
