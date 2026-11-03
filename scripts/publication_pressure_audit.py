"""Extend the audit to original shopping dwell, high demand and 30 seeds.

Declared after the turnover screen: that screen parked all baseline drivers,
so it does not establish stability near binding capacity. Archive this staged
design separately; do not call it a prospectively preregistered study.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import zipfile
import argparse
from publication_stress_audit import run, VARIANTS, ROOT


def pressure_run(job):
    VARIANTS['resolution_quarter']={'model':{'integration_seconds':.25}}
    return run(job)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/publication_audit_20261027')
    out=parser.parse_args().output
    out.mkdir(parents=True,exist_ok=True);(out/'raw').mkdir(exist_ok=True)
    VARIANTS['resolution_quarter']={'model':{'integration_seconds':.25}}
    variants=[v for v in VARIANTS if v not in ('baseline','repeat','output_30')]
    jobs=[('walmart_pressure','baseline',.95,20.,seed,str(out)) for seed in range(101,131)]
    jobs += [('walmart_pressure',v,.95,20.,seed,str(out)) for v in variants for seed in range(101,104)]
    source=[ROOT/'scripts/publication_stress_audit.py',Path(__file__).resolve()]
    plan=dict(reason='Test binding capacity with 80 drivers and original 900-3599 second dwell; initial background cars static',
        staged_design=True,baseline_seeds=list(range(101,131)),sensitivity_seeds=[101,102,103],jobs=jobs,
        variants={**VARIANTS},runs=len(jobs)*3,
        uncertainty='Paired seed intervals; 30 baseline seeds, sensitivity only three. One-factor screen, no interactions.',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source})
    if (out/'pressure_design.json').exists():raise FileExistsError('Preserve frozen pressure design')
    (out/'pressure_design.json').write_text(json.dumps(plan,indent=2))
    with zipfile.ZipFile(out/'pressure_source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in source:z.write(p,p.relative_to(ROOT))
    # Each spawned interpreter imports VARIANTS afresh. Add quarter-resolution
    # in the imported worker module as well through a top-level wrapper.
    with ProcessPoolExecutor(max_workers=3) as pool:
        for tag,elapsed in pool.map(pressure_run,jobs):print(f'{tag}: {elapsed:.1f}s',flush=True)
