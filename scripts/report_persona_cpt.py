"""Build a traceable report and local archive for the persona CPT pilot."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import zipfile
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/persona_cpt_20261027'


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    OUT=parser.parse_args().output
    design=json.loads((OUT/'design.json').read_text())
    assert len(design['seeds'])==10
    runs=pd.read_csv(OUT/'runs.csv');assert len(runs)==60
    summary=pd.read_csv(OUT/'paired_persona_summary.csv')
    replay=pd.read_csv(OUT/'replay_comparisons.csv')
    grid=pd.read_csv(OUT/'sensitivity_decisions.csv')
    oat=pd.read_csv(OUT/'oat_decisions.csv')
    checks=json.loads((OUT/'checks.json').read_text());assert len(checks)==60
    assert all(all(v for k,v in row.items() if k not in ('scenario','seed','arm')) for row in checks)
    unchanged=replay[replay.persona!='risk_averse']
    assert not unchanged.profile_changed_choice.any()
    assert not unchanged.zero_noise_changed_choice.any()
    assert (unchanged.profile_probability_tv==0).all()
    # Validate shared arm against the preceding exact-seed baseline.
    prior=pd.read_csv(ROOT/'results/cpt_continuation_20261027/stress/per_run.csv')
    prior=prior[(prior.model=='cpt') & prior.scenario.isin(runs.scenario.unique())]
    common=runs[(runs.arm=='shared') & runs.seed.isin([42,43,44])].merge(prior,on=['scenario','seed'],suffixes=('_new','_old'),validate='one_to_one')
    assert len(common)==9
    assert (common.parked_new==common.parked_old).all()
    assert (common.mean_search_s-common.mean_search_all_s).abs().max()<1e-9
    total_table='| Scenario | Shared parked | Persona parked | Mean search, shared / persona (s) |\n|---|---:|---:|---:|\n'
    for scenario,g in runs.groupby('scenario'):
        a=g[g.arm=='shared'];b=g[g.arm=='persona']
        total_table+=f'| {scenario} | {a.parked.sum()}/{a.drivers.sum()} | {b.parked.sum()}/{b.drivers.sum()} | {a.mean_search_s.mean():.2f} / {b.mean_search_s.mean():.2f} |\n'
    risk=summary[summary.persona=='risk_averse']
    risk_table='| Risk-averse scenario | Parked, shared / persona | Success difference, pp [seed-bootstrap 95% interval] | Mean search difference, s [interval] | Same space among jointly parked |\n|---|---:|---:|---:|---:|\n'
    for r in risk.itertuples():
        risk_table+=f'| {r.scenario} | {r.parked_shared} / {r.parked_persona} of {r.drivers} | {r.success_delta*100:.2f} [{r.success_ci_low*100:.2f}, {r.success_ci_high*100:.2f}] | {r.search_delta_s:.3f} [{r.search_ci_low:.3f}, {r.search_ci_high:.3f}] | {r.same_space_fraction:.1%} |\n'
    r=replay[(replay.persona=='risk_averse') & replay.multi]
    replay_table='| Risk-averse replay scenario | Contexts | Different sampled choice | Different choice at zero response noise | Mean probability total variation | Different from M0 at zero noise, shared / persona |\n|---|---:|---:|---:|---:|---:|\n'
    for scenario,g in r.groupby('scenario'):
        replay_table+=f'| {scenario} | {len(g)} | {g.profile_changed_choice.mean():.1%} | {g.zero_noise_changed_choice.mean():.1%} | {g.profile_probability_tv.mean():.4f} | {g.shared_differs_m0.mean():.1%} / {g.persona_differs_m0.mean():.1%} |\n'
    sensitivity=grid[(grid.persona=='risk_averse') & (grid.lambda_loss==3)].groupby(['hazard_multiplier','reference_multiplier']).agg(contexts=('driver','count'),changed_choice=('changed_choice','mean')).reset_index()
    sensitivity.to_csv(OUT/'risk_sensitivity.csv',index=False)
    certain=sensitivity[sensitivity.hazard_multiplier==0]
    # A lambda change alone cannot reorder deterministic scalar prospects in
    # these contexts under the zero-temperature, same-reference control.
    assert (certain.changed_choice==0).all()
    table='| Hazard multiplier | Door-reference multiplier | Contexts | Risk lambda=3 versus 2.25: different choice, no response noise |\n|---|---:|---:|---:|\n'
    for row in sensitivity.itertuples():table+=f'| {row.hazard_multiplier:g} | {row.reference_multiplier:g} | {row.contexts} | {row.changed_choice:.1%} |\n'
    report=f'''# Persona CPT profiles: evidence, paired comparisons and sensitivity pilot

## What was implemented

Each driver now has an independently configurable, serializable five-parameter CPT record. Values flow through the population, decision context, actual prospect calculation, event diagnostics and final metrics. Explicit model-level parameters take precedence for controlled experiments. CLI/profile mode `shared` reproduces the earlier benchmark; `persona` selects the profile registry.

Risk-averse lambda is 3.00 versus the shared 2.25. Alpha=beta=.88, gain weighting=.61 and loss weighting=.69 remain shared. Other personas have separate records but unchanged numerical values. No unsupported ordering of loss aversion for cost-, time- or accessibility-seeking drivers is imposed. In identical contexts their decisions/probabilities are exactly unchanged, as verified in this study. Their dynamic final outcomes may still change if risk-averse drivers change competition.

The higher 3.00 value was selected as a rounded experimental perturbation before these reruns. It is **not a literature estimate for risk-averse parking drivers**. The benchmark values are published monetary-lottery estimates; the persona shift and its mapping to a scalar parking-utility prospect are modeling assumptions. [Parameter provenance](../../research/cpt_parameter_provenance.md) and [bibliography](../../research/cpt_sources.bib) distinguish these explicitly.

## Design and robustness scope

The internal frozen design is `design.json`, written before simulation along with `source_snapshot.zip`. This is not a registered empirical study. It records ten paired seeds (42–51), three scenarios, profile values, endpoints, sensitivity ranges, package versions, configuration/source hashes and base Git commit. The source archive captures the working copy, including changes beyond that commit. Each arm uses identical initial occupancy, driver attributes, utility preferences, door/exit references and run IDs; only the CPT profile differs. Both arms use common RNG streams initially, with endogenous search histories allowed to diverge. All 60 runs passed finite-utility, no-double-claim, completion, elapsed-time-identity and required-legality checks. The nine overlapping shared-arm runs exactly reproduce the preceding three-seed baseline's parked counts and mean search times.

All 118 tests passed. New tests check profile configuration, matching, parameter precedence, serialization, fixed-lottery loss sensitivity and exact unchanged-profile controls. Existing tests cover cumulative lottery math, route/timing consistency and resource safety.

The analysis resamples paired seed-level contrasts 5,000 times for percentile 95% intervals. Drivers within a replication are not treated as independent. These are exploratory simulation-replication intervals conditional on fixed geometry, profiles and scenarios, not uncertainty in human preference estimates. Ten seeds are an expanded pilot rather than a power/convergence demonstration. A degenerate interval with no observed paired changes must not be interpreted as statistical equivalence or proof of a zero effect outside the tested runs.

## Dynamic outcomes

{total_table}
{risk_table}
`paired_persona_summary.csv` reports the same contrasts for all five personas, including walking and believed claim-availability differences among jointly parked drivers. Conditioning on parking is explicit: those distance/belief contrasts are not unconditional causal effects.

## Identical-information comparisons

Shared-CPT trajectories supply the first three nonempty contexts per driver; snapshots are archived in `replay_contexts.jsonl`. All comparisons use identical candidates, approach times, probabilities, preferences, references and common RNG seeds. Sampling and competition feedback cannot explain zero-temperature ranking/action changes. Snapshot selection is based on the shared arm, so this is not an unbiased sample of all persona-arm opportunities.

{replay_table}
The replay contains {len(replay)} contexts in total. M0/M1 outcomes and probability distributions are also evaluated on those same contexts. For the four unchanged profiles, every paired shared/persona choice and probability vector matches exactly; this is a negative control rather than evidence that their preferences are identical to one another.

Changing loss aversion can change response probabilities without changing the best-ranked action: if every relevant prospect is entirely a loss, multiplying lambda scales all CPT values together, effectively changing response noise at fixed softmax temperature. Mixed gain/loss consequences can also change relative rankings. Both mechanisms are reported, and a temperature sensitivity control is retained.

## Sensitivity and transfer limits

The frozen factorial grid varies lambda in [1,1.6,2.25,3,4], claim hazard by [0,.5,1,2] and the door reference by [.75,1,1.25]. Mobility caps remain fixed, and perturbed reference distances are capped by the driver's walking constraint. Because baseline beliefs are exponential survival probabilities with no additional forecast, hazard multipliers are implemented by exponentiating those beliefs. Each comparison holds the other grid settings fixed. The subset uses the first two multi-feasible contexts per scenario/seed/persona, independently of their outcomes. It is balanced by design strata, not by all encountered context frequencies. Curvature/weighting controls compare lambda=3 versus 2.25 under the same perturbed function parameters; temperature and generalized-utility-unit controls additionally check response-scale confounding. These grids are stress ranges, not empirical priors or confidence limits.

There are {len(grid)} factorial and {len(oat)} additional one-at-a-time sensitivity evaluations. Risk-averse results at lambda=3 versus 2.25:

{table}
The certainty control produces no zero-temperature lambda-induced choice changes in these contexts. Sensitivity to hazard and references is not a nuisance to conceal: it determines how much loss aversion can matter. The composite utility representation prevents interpreting lambda as a specifically monetary, walking or time loss-aversion coefficient. Other profile values, outcome probabilities, continuation and geometry remain uncalibrated.

## Literature and publication claims

The common benchmark is from [Tversky and Kahneman (1992)](https://doi.org/10.1007/BF00122574), journal pp. 311–312. [Booij et al. (2010)](https://doi.org/10.1007/s11238-009-9144-4) show that estimates differ across samples and methods (pooled loss aversion about 1.6 in their general-population study). [Cao et al. (2024)](https://doi.org/10.3390/su16041596) provide a parking application with time/money preference groups, not coefficients for our five personas or Walmart spaces. No source reviewed establishes the proposed risk-persona value 3.00 or the assumed mapping of these labels to five CPT parameters.

These results support a conditional simulation sensitivity claim. They do not establish empirically distinct persona CPT distributions, better real-world prediction than M0/M1, a validated risk-persona ordering, or publication readiness of the whole ABM. An empirical prediction paper still needs identified/elicited preference and reference estimates, a parameter-recovery/identifiability study, independently held-out predictions, justified persona classification, empirical occupancy/navigation validation and a broader replication/convergence assessment. A simulation-methods paper can instead explicitly define hypothetical profiles and limit its claims to those experiments. The full calibration/validation gaps are listed in the version-controlled provenance note.

## Reproduce and archive

```powershell
python -m pytest tests -q --basetemp=.codex-build/pytest-persona-cpt-report
python scripts/compare_persona_cpt.py --output results/persona_cpt_reproduction
python scripts/analyze_persona_cpt.py --output results/persona_cpt_reproduction
python scripts/report_persona_cpt.py --output results/persona_cpt_reproduction
```

The comparison script requires a fresh output directory to prevent overwriting a frozen design. `reproducibility_bundle.zip` includes raw runs/drivers, replay contexts, safety checks, design/source archive, analysis/report scripts, provenance and bibliography. The initial source snapshot predates addition of the analysis/report scripts, so those are included separately with hashes in `bundle_manifest.json`. Generated results are ignored by Git and need separate institutional/journal archival before submission. No result is uploaded or published by these scripts.
'''
    (OUT/'REPORT.md').write_text(report,encoding='utf-8')
    requirements=[line.strip() for line in (ROOT/'requirements.txt').read_text().splitlines() if line.strip()]
    (OUT/'requirements-pinned.txt').write_text(''.join(f'{name}=={importlib.metadata.version(name)}\n' for name in requirements))
    extras=[ROOT/'scripts/analyze_persona_cpt.py',ROOT/'scripts/report_persona_cpt.py',ROOT/'research/cpt_parameter_provenance.md',ROOT/'research/cpt_sources.bib',ROOT/'requirements.txt']
    paths=[p for p in OUT.iterdir() if p.is_file() and p.suffix in ('.csv','.json','.jsonl','.txt','.md','.zip') and p.name not in ('reproducibility_bundle.zip','bundle_manifest.json')]
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    manifest.update({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in extras})
    (OUT/'bundle_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    paths.append(OUT/'bundle_manifest.json')
    with zipfile.ZipFile(OUT/'reproducibility_bundle.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for p in paths:archive.write(p,p.name)
        for p in extras:archive.write(p,str(p.relative_to(ROOT)))
    print(total_table);print(risk_table);print(replay_table);print(table)


if __name__=='__main__':main()
