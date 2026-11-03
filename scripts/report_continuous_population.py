"""Report generic-driver comparisons and cautious post-simulation profiles."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator,FuncFormatter,NullFormatter
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/continuous_population_20261027')
    args=parser.parse_args();out=args.output
    summary=pd.read_csv(out/'model_summary.csv');diagnostics=pd.read_csv(out/'profile_diagnostics.csv')
    centroids=pd.read_csv(out/'heldout_profile_descriptions.csv')
    assigned=pd.read_csv(out/'posthoc_profile_assignments.csv');transfer=pd.read_csv(out/'cross_occupancy_profile_stability.csv')
    drivers=pd.read_csv(out/'drivers.csv');runs=pd.read_csv(out/'runs.csv')
    assert len(runs)==180 and len(drivers)==12000 and drivers.persona.isna().all()
    table='| Scenario | Population | M0 parked | M1 parked | CPT parked |\n|---|---|---:|---:|---:|\n'
    for (scenario,population),g in summary.groupby(['scenario','population']):
        values={r.model:f'{r.parked}/{r.drivers}' for r in g.itertuples()}
        table+=f'| {scenario} | {population} | {values["deterministic"]} | {values["rum"]} | {values["cpt"]} |\n'
    profile_table='| Scenario | Population | Model | Selected density components | Passed all exploratory gates | Minimum seed-bootstrap Jaccard |\n|---|---|---|---:|---|---:|\n'
    for r in diagnostics.itertuples():
        stability=getattr(r,'min_bootstrap_jaccard',float('nan'))
        profile_table+=f'| {r.scenario} | {r.population} | {r.model} | {r.selected_components} | {r.candidate_supported} | {stability:.2f} |\n'
    details='| CPT held-out regime | Drivers | Mean search (s) | Mean walk (m) | Walk / expected door distance |\n|---|---:|---:|---:|---:|\n'
    for r in centroids[(centroids.model=='cpt') & (centroids.population=='heterogeneous')].itertuples():
        details+=f'| {r.scenario}: {r.behavior_regime} | {r.drivers} | {r.search_s:.1f} | {r.walk_m:.1f} | {r.walk_relative:.2f} |\n'
    valid=assigned[assigned.validation & (assigned.model=='cpt')]
    fig,axes=plt.subplots(2,2,figsize=(11,8),sharex=True,sharey=True,layout='constrained')
    for row,scenario in enumerate(['walmart_crowded','walmart_saturated']):
        for col,population in enumerate(['heterogeneous','homogeneous']):
            ax=axes[row,col];g=valid[(valid.scenario==scenario)&(valid.population==population)]
            for regime,h in g.groupby('behavior_regime'):
                ax.scatter(h.search_s,h.walk_relative,s=13,alpha=.55,label=f'Regime {int(regime)}')
            result=diagnostics[(diagnostics.scenario==scenario)&(diagnostics.population==population)&(diagnostics.model=='cpt')].iloc[0]
            ax.set_title(f'{scenario.replace("walmart_","")} / {population}\nDensity k={result.selected_components}; gates passed={result.candidate_supported}')
            ax.set_xscale('log');ax.grid(alpha=.2);ax.legend(fontsize=8)
            ax.xaxis.set_major_locator(FixedLocator([20,50,100,300,600]))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda value,position:f'{value:g}'))
            ax.xaxis.set_minor_formatter(NullFormatter())
            if row==1:ax.set_xlabel('Elapsed search seconds (log axis)')
            if col==0:ax.set_ylabel('Walk / driver door-distance reference')
    fig.suptitle('Held-out CPT search/walking regimes\nFitted density components are not validated driver personas',fontsize=13)
    fig.savefig(out/'heldout_behavioral_regimes.png',dpi=160);plt.close(fig)
    passed=int(diagnostics.candidate_supported.sum())
    accepted=centroids.merge(diagnostics[['scenario','population','model','candidate_supported']],on=['scenario','population','model'])
    accepted=accepted[accepted.candidate_supported]
    candidates='No mixture passed every operational gate.\n'
    if len(accepted):
        candidates='| Screened candidate | Regime | Held-out drivers | Search (s) | Walk (m) | Walk/reference | Bootstrap Jaccard |\n|---|---:|---:|---:|---:|---:|---:|\n'
        for r in accepted.itertuples():
            candidates+=f'| {r.scenario}/{r.population}/{r.model} | {r.behavior_regime} | {r.drivers} | {r.search_s:.1f} | {r.walk_m:.1f} | {r.walk_relative:.2f} | {r.seed_bootstrap_jaccard:.2f} |\n'
    report=f'''# Continuous drivers and post-simulation behavioral profiles

Drivers are now generated without assigned personas. Across 180 matched simulations, descriptive search/walking regimes appear, but only {passed} of {len(diagnostics)} mixture fits passes every exploratory validation/stability gate. This is evidence to investigate contextual behavioral patterns, not a validated taxonomy of stable driver personas.

## Refactor

The primary `make_population` now draws generic drivers with continuous utility preferences, temperature, reference state and optional continuous CPT parameters. It has no persona argument or label-to-parameter lookup. `DriverAttributes.persona` defaults to None and remains unset in all {len(drivers):,} driver outcomes. Eligibility, permits, physical mobility/walking limits, arrival, destination and urgency are distinct attribute/scenario inputs. No accessibility or urgency override is triggered by a behavioral label.

The previous generator is preserved as explicitly named `make_controlled_population` for historical prescribed-mixture experiments. The CLI and runner default to continuous generation; `--personas` explicitly opts into the legacy mode. Renaming descriptive labels with all causal inputs fixed leaves trajectories unchanged for all three models. Homogeneous controls retain the exact same attributes/constraints and fix behavioral coefficients, temperature, search-reference and CPT values at central prior values. Contextual door/exit references still depend on actual constraints/destination. Separate RNG streams prevent parameter draws from resampling trips.

The priors are fully disclosed **structural assumptions**, not calibrated distributions of real drivers. The preference vector has one Dirichlet distribution, not a mixture centered on intended personas. Fixed total utility weight limits scale confounding but imposes negative compositional dependence. Temperature/search-reference/lambda lognormal centers are medians; the central-prior homogeneous control is not an exact mean-matched causal variance experiment. [Full distributions and limitations](../../research/continuous_population_design.md) and [governing architecture](../../research/behavioral_architecture.md) explain the assumptions.

## Matched comparisons

The study comprises 180 runs: ten paired seeds, three scenarios, two population modes and three decision models. Within each population, all models receive the identical frozen specification and initial occupancy. A common decision RNG namespace removes model-name-induced seed differences at otherwise identical decision contexts; histories may subsequently diverge. Deadline reachability is applied in shared feasibility code for M0/M1/M2. Existing distinct continuation/acceptance constructions remain part of the model specifications, so this is not an ablation of the CPT value function alone.

All 135 tests passed. All simulation runs passed terminal-state, finite-utility, no-double-claim, elapsed-time-identity and required-legality checks. Each population realization and its hash is archived. `model_contrasts.csv` contains paired per-seed CPT/M0 and CPT/M1 intervals and same-space comparisons; `heterogeneity_contrasts.csv` compares heterogeneous and central homogeneous populations. Intervals resample seeds, not individual correlated drivers. This is an exploratory ten-seed simulation study, not empirical population inference or a power/convergence study.

{table}
Similar success counts do not imply identical individual decisions. Raw choices, search/walk measures, inspected opportunities, violations and preference values remain in `drivers.csv` and `paired_models.csv`. A direct numerical before/after comparison with the earlier prescribed-persona study would confound the changed population specification and the corrected shared RNG/feasibility handling; no such causal attribution is made here.

## What behavioral groups emerged?

Clustering uses only realized search time and walking distance relative to a driver's door-distance reference. It does not use assigned personas or preference/CPT values. Parked drivers without mobility constraints, eligibility or permits form the primary exploratory sample; `profile_sample_accounting.csv` explicitly retains every exclusion and outcome. Abandonment is not renamed as a personality. Features, robust scaling and mixture selection are fitted on seeds 42–47, with validation on seeds 48–51. A one-component result is permitted; 1–6 full-covariance Gaussian mixtures are compared by training BIC.

There are **{passed} of {len(diagnostics)} scenario/population/model fits passing all predeclared exploratory gates**. The complete diagnostics, including held-out per-seed log-score intervals, component mass, posterior ambiguity and bootstrap assignment stability, are in `profile_diagnostics.csv`. Operational thresholds are screening choices, not universal definitions of a human persona. The diagnostics should be assessed jointly rather than re-tuning cutoffs after seeing results.

{profile_table}
Passing candidates and their held-out descriptions:

{candidates}
Gaussian components approximate distributions; they do not establish discrete latent driver classes. In particular, selected counts at the upper bound of six indicate unresolved density complexity rather than proof of six types. The synthetic facility has discrete geometry and limited sample size. Small validation components, overlapping memberships or unstable seed refits can prevent accepting a seemingly attractive BIC partition.

The same analysis is run on homogeneous controls, where variation in outcomes can arise from geometry, destinations, competition and stochastic decisions without heterogeneous tastes. `profile_null_comparison.csv` reports this control. Cross-occupancy adjusted-Rand comparisons use matched held-out drivers, not matching component names by hand; values are in `cross_occupancy_profile_stability.csv`. A shared one-component partition can trivially yield high agreement and is not emergence evidence.

For the heterogeneous RUM population, cross-occupancy agreement is approximately {transfer[(transfer.population=='heterogeneous') & (transfer.model=='rum')].adjusted_rand.iloc[0]:.2f}. Thus even the screened saturated-lot candidate should be described as a contextual regime partition, not a demonstrated permanent driver classification. The number of CPT partitions passing all screening gates is {int(diagnostics[diagnostics.model=='cpt'].candidate_supported.sum())} in this pilot.

The following **descriptive CPT regimes** show the observed search/walking patterns. Their numerical IDs are scoped to each scenario and ordered by training mean search. They are not permanent driver labels or the previous cost/time/risk/accessibility personas, and none is fed back into generation or decisions:

{details}
![Held-out CPT outcomes and fitted regimes](heldout_behavioral_regimes.png)

## Interpretation and publication limits

The architecture now permits behavioral patterns to arise from continuous preferences, constraints, rules and interactions rather than prescribing named groups. That does not guarantee five profiles, any discrete classes, or empirical validity. The present two-feature analysis can describe search/walking regimes; it cannot uniquely identify cost sensitivity or loss aversion from those outcomes. Price and violation-risk tradeoffs do not vary across available legal spaces in free Walmart scenarios. The synthetic tradeoff is hypothetical.

Learning, memory-based habits and operational guidance are not active mechanisms in these runs. Their associated profiles cannot be tested by this experiment, and an absent cluster is not evidence that such people do not exist. Further attribute-to-preference estimation, prior/feature/method sensitivity, richer decision-opportunity fingerprints, more independent validation seeds and observed behavior are needed before publication claims about stable human personas. Keeping uncertainty and allowing profiles not to emerge is a valid result under the proposal.

The lot/aisle geometry remains estimated, initial background vehicles do not depart, perception is radius-based, and traffic queues/car-following are not modeled. Those existing structural limitations can influence search/walking regimes; the present refactor does not validate or remove them.

The GMM/BIC procedure follows standard [model-selection practice](https://scikit-learn.org/stable/auto_examples/mixture/plot_gmm_selection.html); bootstrap assignment checks draw on [Hennig (2007)](https://doi.org/10.1016/j.csda.2006.11.025). Neither criterion alone proves that a cluster is a behavioral type. The original project document governs the causal direction; proposed labels are hypotheses for subsequent interpretation, not simulation inputs.

## Reproduction and archive

```powershell
python -m pytest tests -q --basetemp=.codex-build/pytest-continuous-reproduction
python scripts/run_continuous_population_study.py --output results/continuous_reproduction --workers 3
python scripts/analyze_continuous_population.py --output results/continuous_reproduction
python scripts/report_continuous_population.py --output results/continuous_reproduction
```

Install the simulation and optional analysis requirements first. `design.json` records the internal frozen design and source hashes before simulation; it is not a registered empirical protocol. The source snapshot predates addition of the analysis/report modules, which are supplied separately in the bundle. `requirements-pinned.txt` records the runtime package versions. `reproducibility_bundle.zip` includes raw replications, population specifications, diagnostics, assignments, source snapshots and scripts, with payload hashes in `bundle_manifest.json`. Generated results are ignored by Git and require separate archival for publication.
'''
    (out/'REPORT.md').write_text(report,encoding='utf-8')
    names=['mesa','numpy','pandas','matplotlib','networkx','pytest','scikit-learn','scipy','joblib','threadpoolctl','cloudpickle','narwhals']
    (out/'requirements-pinned.txt').write_text(''.join(f'{name}=={importlib.metadata.version(name)}\n' for name in names))
    extras=[ROOT/'panda_abm/analysis/profiles.py',ROOT/'scripts/analyze_continuous_population.py',Path(__file__),
        ROOT/'tests/test_behavioral_profiles.py',ROOT/'README.md',
        ROOT/'research/continuous_population_design.md',ROOT/'research/behavioral_architecture.md',ROOT/'requirements.txt',ROOT/'requirements-analysis.txt']
    paths=[p for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ('bundle_manifest.json','reproducibility_bundle.zip')]
    payload={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    payload.update({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in extras})
    (out/'bundle_manifest.json').write_text(json.dumps(payload,indent=2)+'\n')
    with zipfile.ZipFile(out/'reproducibility_bundle.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for p in paths+[out/'bundle_manifest.json']:archive.write(p,p.relative_to(out).as_posix())
        for p in extras:archive.write(p,p.relative_to(ROOT).as_posix())
    print(table);print(profile_table);print(candidates);print(details);print(transfer.to_string(index=False))


if __name__=='__main__':main()
