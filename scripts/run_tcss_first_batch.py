"""Versioned TCSS E1/E2a/H1 batch; requires successful E0 verification."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import hashlib
import json
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
import pandas as pd
import compare_parking_information as study


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verification',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--core-seeds',type=int,nargs='+',default=list(range(1000,1030)))
    parser.add_argument('--control-seeds',type=int,nargs='+',default=list(range(1000,1010)))
    args=parser.parse_args();out=args.output
    verification=json.loads(args.verification.read_text())
    assert verification['status']=='passed'
    # A successful oracle from a different implementation cannot unlock a batch.
    for name,digest in verification['source_sha256'].items():
        if name.startswith('panda_abm/'):
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    jobs=[];designs=[]
    scopes=[('core','base',(.4,.8,.95),('deterministic','rum','cpt'),args.core_seeds),
            ('linear','base',(.8,.95),('linear_cpt',),args.core_seeds),
            ('tastes','homogeneous_tastes',(.8,.95),('deterministic','rum','cpt'),args.control_seeds),
            ('cpt_central','homogeneous_cpt',(.8,.95),('cpt',),args.control_seeds)]
    for stage,variant,occupancies,models,seeds in scopes:
        folder=out/stage
        for sub in ('replications','populations','initial_occupancy'):(folder/sub).mkdir(parents=True)
        designs.append(dict(stage=stage,variant=variant,occupancies=occupancies,models=models,seeds=seeds,
            runs=len(occupancies)*len(models)*len(seeds)*3))
        jobs.extend((seed,occ,80,str(folder),dict(variant=variant,models=models)) for occ in occupancies for seed in seeds)
    files=sorted([*ROOT.glob('panda_abm/**/*.py'),*ROOT.glob('scripts/*.py'),*ROOT.glob('tests/*.py'),
        ROOT/'data/lot_config.json',ROOT/'requirements.txt',ROOT/'requirements-analysis.txt',ROOT/'research/tcss/README.md'])
    design=dict(status='running',model_version='tcss_common_reference_v2',stages=designs,
        runs=sum(d['runs'] for d in designs),size=80,
        rationale='CPT failure semantics changed; regenerate baseline controls, do not pool old CPT pilot.',
        matching='Same base populations, initial occupancy, run IDs and information_matched decision namespace; manipulated fields hashed separately.',
        E0=str(args.verification),E0_sha256=hashlib.sha256(args.verification.read_bytes()).hexdigest(),
        python=sys.version,source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (out/'design.json').write_text(json.dumps(design,indent=2),encoding='utf-8')
    with zipfile.ZipFile(out/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in files:archive.write(p,p.relative_to(ROOT))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(study.replication,j):j for j in jobs}
        for i,f in enumerate(as_completed(futures),1):
            f.result();print(f'Completed replication group {i}/{len(jobs)}',flush=True)
    for suffix in ('drivers','runs'):
        tables=[pd.read_csv(p) for p in sorted(out.glob(f'*/replications/*_{suffix}.csv'))]
        pd.concat(tables,ignore_index=True).to_csv(out/f'{suffix}.csv',index=False)
    checks=[c for p in sorted(out.glob('*/replications/*_checks.json')) for c in json.loads(p.read_text())]
    assert len(checks)==design['runs']
    # Physical attributes and initial supply must match across interventions.
    for seed in args.control_seeds:
        for occ in (.8,.95):
            group=[c for c in checks if c['seed']==seed and c['occupancy']==occ]
            assert len({c['base_population_sha256'] for c in group})==1
            assert len({c['initial_occupancy_sha256'] for c in group})==1
    (out/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    design['status']='completed'
    design['output_sha256']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ('drivers.csv','runs.csv','checks.json')}
    (out/'design.json').write_text(json.dumps(design,indent=2),encoding='utf-8')
    print(f'Completed {len(checks)} full executions',flush=True)


if __name__=='__main__':main()
