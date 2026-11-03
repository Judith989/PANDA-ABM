"""Generate native parity fixtures and measured full-lifecycle CPU timings."""
from pathlib import Path
import argparse
import json
import platform
import statistics
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from panda_abm.twin.platform import simulate, runtime_versions


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fixtures-only',action='store_true');parser.add_argument('--skip-fixtures',action='store_true');args=parser.parse_args()
    cases=[]
    for occupancy in (() if args.skip_fixtures else (.8,.95)):
        for model in ('deterministic','rum','cpt'):
            for information in ('unaided','aisle','space'):
                row=simulate(dict(population_size=3,seed=51,occupancy=occupancy,model=model,information=information))
                cases.append({k:v for k,v in row.items() if k not in ('wall_s','initialize_wall_s')})
    destination=ROOT/'dashboard/engine/native-fixtures.json'
    if not args.skip_fixtures:
        destination.write_text(json.dumps(dict(runtime=runtime_versions(),cases=cases),allow_nan=False),encoding='utf-8')
        print(f'Wrote {len(cases)} native fixtures',flush=True)
    if args.fixtures_only:return
    rows=[]
    for n in (20,80,120):
        for repeat in range(3):
            row=simulate(dict(population_size=n,seed=7000+repeat,occupancy=.8,model='cpt',information='space',arrival_interval_s=20))
            rows.append(dict(population=n,repeat=repeat,wall_s=row['wall_s'],initialize_wall_s=row['initialize_wall_s'],simulated_duration_s=row['simulated_duration_s']))
            print(f"Native {n} drivers, repetition {repeat+1}: {row['wall_s']:.3f} s",flush=True)
    output=ROOT/'paper/platform_evaluation';output.mkdir(exist_ok=True)
    report=dict(measured_utc=datetime.now(timezone.utc).isoformat(),os=platform.platform(),processor=platform.processor(),runtime=runtime_versions(),scope='One process; full trip lifecycle; no trajectory sampling or rendering',timings=rows,
        median_wall_s={str(n):statistics.median(r['wall_s'] for r in rows if r['population']==n) for n in (20,80,120)})
    (output/'native_performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
