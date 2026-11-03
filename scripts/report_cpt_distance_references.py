"""Compare the fixed-inventory reference experiment with the prior stress run."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.parameters import PERSONA_PARAMETER_PROFILES
from panda_abm.environment import load_facility_from_lot_config


def main():
    output = ROOT/'results/cpt_distance_references_20261027'
    old = pd.read_csv(ROOT/'results/search_timing_cpt_20261027/stress/summary.csv')
    new = pd.read_csv(output/'stress/summary.csv')
    comparison = old.merge(new,on=['scenario','model'],suffixes=('_before','_after'))
    comparison.to_csv(output/'comparison.csv',index=False)
    checks = json.loads((output/'stress/checks.json').read_text())
    assert len(checks) == 72
    assert all(all(value for key,value in check.items() if key!='run_id') for check in checks)
    # These models ignore references; unchanged results are a matched-run control.
    controls = comparison[comparison.model!='cpt']
    for field in ['parked','mean_search_all_s','mean_rejected']:
        assert (controls[f'{field}_before']-controls[f'{field}_after']).abs().max() < 1e-9
    facility = load_facility_from_lot_config(ROOT/'data/lot_config.json')
    references = []
    for seed in [42,43,44]:
        for driver in make_population(facility,size=80,seed=seed,personas=tuple(PERSONA_PARAMETER_PROFILES),cpt_profile_mode='shared').drivers:
            references.append(dict(seed=seed,driver=driver.driver_id,persona=driver.attributes.persona,
                door=driver.attributes.walmart_door_id,exit=driver.attributes.preferred_exit_id,
                **driver.reference_points.as_dict()))
    frame = pd.DataFrame(references)
    frame.to_csv(output/'walmart_reference_points.csv',index=False)
    table = '| CPT scenario | Parked before | Parked after | Mean rejected candidates before → after | Mean search seconds before → after |\n|---|---:|---:|---:|---:|\n'
    for row in comparison[comparison.model=='cpt'].itertuples():
        table += f'| {row.scenario} | {row.parked_before}/{row.drivers_before} | {row.parked_after}/{row.drivers_after} | {row.mean_rejected_before:.1f} → {row.mean_rejected_after:.1f} | {row.mean_search_all_s_before:.1f} → {row.mean_search_all_s_after:.1f} |\n'
    ranges = frame.groupby(['door','exit']).agg(walk_min=('r_walk_m','min'),walk_max=('r_walk_m','max'),exit_min=('r_exit_m','min'),exit_max=('r_exit_m','max'))
    (output/'REPORT.md').write_text('''# CPT distance-reference experiment

Generated drivers now expect the median distance to their chosen door and preferred exit among their static legal, vehicle-compatible spaces, filtered by permanent closures, permits, accessibility eligibility and maximum walking distance. Both main and side spaces participate. References stay fixed: no conditioning on occupancy, visibility, current candidates or elapsed search. Search references, preference weights, CPT mathematics, aspiration thresholds, routes and timing are unchanged. Prior RNG draws are retained so all other generated attributes remain matched. Explicit custom reference points remain supported. An empty usable inventory preserves explicit fallback values without relaxing constraints.

The medians represent a typical feasible space, not the nearest possible space. They are geometry-based priors rather than empirically measured driver expectations. Door distance is straight-line walking distance; exit distance is the existing straight-line exit feature. Neither is a surveyed travel distance. Familiarity-dependent learning and empirically fitted persona expectations remain future calibration work.

## Verification and comparisons

94 tests passed. All 72 stress simulations completed with finite utilities, no double claims, no parking in a full lot and no illegal parking in legal-only scenarios. Deterministic and random-utility controls have exactly unchanged parked counts, mean search and mean rejection in every scenario. The comparison uses the same three seeds, initial occupancy and five-persona mix; three seeds do not establish a general model ranking.

'''+table+'''
“Rejected candidates” counts candidate evaluations rejected across scans, including repeat observations of the same space; it is not a count of distinct spaces. Mean search includes drivers who abandon after 600 seconds.

## Reference audit

`walmart_reference_points.csv` records each driver's door, exit, reference distances and usable inventory size. `stress/drivers.csv` records references beside outcomes. `comparison.csv` contains every model/scenario comparison; raw runs and safety checks are in `stress/`.

Door/exit combinations in this balanced population, with reference ranges in metres:

```
'''+ranges.round(2).to_string()+'''
```

These results assess sensitivity to the reference assumption. Improved acceptance does not establish real-world accuracy. Fixed search expectations, outcome probabilities and continuation assumptions can still cause rejection, and wider seed/empirical calibration is still needed.

## Reproduce

```powershell
python -m pytest tests -q --basetemp=.codex-build/pytest-distance-references-report
python scripts/stress_test_decisions.py --cpt-profile-mode shared --output results/cpt_distance_references_20261027/stress
python scripts/report_cpt_distance_references.py
```
''',encoding='utf-8')
    print(table.replace('→', '->'))
    print(ranges.round(2).to_string())


if __name__=='__main__':
    main()
