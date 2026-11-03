"""Report the matched CPT continuation and door-expectation investigation."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'results/cpt_continuation_20261027'
    previous=ROOT/'results/cpt_distance_references_20261027/stress'
    before=pd.read_csv(previous/'summary.csv')
    after=pd.read_csv(out/'stress/summary.csv')
    compared=before.merge(after,on=['scenario','model'],suffixes=('_before','_after'))
    compared.to_csv(out/'comparison.csv',index=False)
    checks=json.loads((out/'stress/checks.json').read_text())
    assert len(checks)==72
    assert all(all(v for k,v in check.items() if k!='run_id') for check in checks)
    for field in ['parked','mean_search_all_s','mean_rejected']:
        control=compared[compared.model!='cpt']
        assert (control[field+'_before']-control[field+'_after']).abs().max()<1e-9
    # Door/exit expectations must be untouched in matched populations.
    old_drivers=pd.read_csv(previous/'drivers.csv')
    new_drivers=pd.read_csv(out/'stress/drivers.csv')
    keys=['scenario','seed','model','driver']
    refs=old_drivers.merge(new_drivers,on=keys,suffixes=('_before','_after'))
    for field in ['r_walk_m','r_exit_m','reference_space_count']:
        assert (refs[field+'_before']==refs[field+'_after']).all()
    table='| CPT scenario | Parked before | Parked after | Mean search, all drivers (s), before / after | Rejected candidates per driver, before / after |\n|---|---:|---:|---:|---:|\n'
    for r in compared[compared.model=='cpt'].itertuples():
        table+=f'| {r.scenario} | {r.parked_before}/{r.drivers_before} | {r.parked_after}/{r.drivers_after} | {r.mean_search_all_s_before:.1f} / {r.mean_search_all_s_after:.1f} | {r.mean_rejected_before:.1f} / {r.mean_rejected_after:.1f} |\n'
    pre=pd.read_csv(out/'before_audit/rejections.csv')
    post=pd.read_csv(out/'after_audit/rejections.csv')
    trace='| Seed-42 occupancy | Rejections with an otherwise acceptable space at/below the door reference, before / after | Rejections despite a space passing both existing gates, before / after |\n|---|---:|---:|\n'
    for occupancy in (.8,.95):
        a=pre[pre.occupancy==occupancy];b=post[post.occupancy==occupancy]
        trace+=f'| {occupancy:.0%} | {int((a.within_door_reference>0).sum())} / {int((b.within_door_reference>0).sum())} | {int((a.gate_acceptable>0).sum())} / {int((b.gate_acceptable>0).sum())} |\n'
    report='''# CPT normal-scenario rejection investigation

## Findings

Door expectations were not hard walking cutoffs. They were fixed legal-inventory medians, with farther spaces producing losses relative to expectations. Actual mobility caps were separate. The investigation found that drivers sometimes rejected even spaces at or below those expected door distances.

The old parking prospect included accumulated search, approach time, reference walking/search expectations, claim failure and lost opportunity. Its continuation comparator was only a certain negative cost for one additional scan. That compared different consequences and time horizons, implicitly omitting future parking distance, claim risk and the existing search burden from continuing. A static distance reference therefore looked like an increasingly difficult acceptance target as time passed.

The old sequence also sampled from all feasible spaces before checking aspiration and continuation gates. A poor sample could reject the entire choice set despite another candidate passing both gates. Matched traces below count this directly; these are decision events, not independent drivers or distinct spaces.

'''+trace+'''
## Changes

- Door and exit references, persona coefficients, CPT value/weighting functions and absolute utility aspirations are unchanged.
- Default continuation is a reduced terminal lottery: a uniform mixture of currently observed feasible offers attempted after one further decision interval. It carries the same reference, elapsed search, success/failure consequences and claim probabilities as parking now, plus the additional search delay. Cumulative weights are applied once to the combined lottery, rather than averaging already transformed CPT values.
- This is a limited one-scan persistence forecast. It assumes observed quality persists, holds claim probabilities fixed over the extra scan, and does not predict unseen spaces or learn future occupancy. It can favor taking an acceptable offer now. It is not an optimal stopping policy or an empirically validated future-opportunity model. Explicit reference-relative terminal lotteries supplied through `continuation_outcomes` override this default; a sufficiently better forecast still causes continuation in regression tests.
- Absolute aspiration and continuation checks happen before response-noise sampling. Failed candidates have zero choice probability when acceptable candidates exist. No absolute threshold or mobility restriction is relaxed.
- The actual remaining search deadline rules out current offers that cannot be reached and removes future-success branches that cannot complete after the additional scan.

## Matched stress results

'''+table+'''
All 106 tests passed. All 72 stress simulations passed completion, finite-value, no-double-claim and full-lot checks. Legal-only scenarios remained legal. Deterministic and random-utility control counts, mean search and mean rejection are unchanged in every scenario. Driver-level door/exit references and usable-inventory counts match the previous experiment exactly.

Counts are pooled over the same three seeds and matched five-persona populations. Mean search includes abandonment. Rejected-candidate counts include repeated evaluations of the same space. Remaining differences across models include ranking, response noise and the assumed continuation forecast; improved parking success alone does not establish real-world accuracy. Initially occupied background vehicles still do not leave.

## Reproduce and audit files

`before_audit/` and `after_audit/` contain matched seed-42 decision-level rejection traces for normal 80% and 95% Walmart scenarios. `comparison.csv` compares all models/scenarios. `stress/` contains raw runs, driver/persona results, conditions and safety checks. The before trace was generated using the previous CPT implementation before editing it.

```powershell
python -m pytest tests -q --basetemp=.codex-build/pytest-cpt-continuation-report
python scripts/audit_cpt_rejections.py --output results/cpt_continuation_20261027/after_audit
python scripts/stress_test_decisions.py --cpt-profile-mode shared --output results/cpt_continuation_20261027/stress
python scripts/report_cpt_continuation.py
```
'''
    (out/'REPORT.md').write_text(report,encoding='utf-8')
    print(trace);print(table)


if __name__=='__main__':main()
