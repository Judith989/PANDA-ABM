"""Check a full-size browser comparison against the final study driver archive."""
from pathlib import Path
import csv
import json

ROOT=Path(__file__).resolve().parents[1]


def main():
    folder=ROOT/'paper/platform_evaluation'
    data=json.loads((folder/'browser_80driver_comparison.json').read_text())
    with (ROOT/'results/tcss_first_batch_20261028/drivers.csv').open(newline='') as handle:
        expected={(int(r['seed']),float(r['occupancy']),r['model'],r['information'],r['driver']):r
                  for r in csv.DictReader(handle) if r.get('variant','base')=='base'}
    checks=json.loads((ROOT/'results/tcss_first_batch_20261028/checks.json').read_text())
    errors=[];count=0;raw_population_hashes_match=True;max_population_difference=0.0
    def compare_population(a,b,path='population'):
        nonlocal max_population_difference
        if isinstance(a,dict) and isinstance(b,dict):
            if set(a)!=set(b):errors.append(dict(field=path,reason='Different keys'));return
            for key in a:compare_population(a[key],b[key],path+'.'+key)
        elif isinstance(a,list) and isinstance(b,list):
            if len(a)!=len(b):errors.append(dict(field=path,reason='Different lengths'));return
            for i,(x,y) in enumerate(zip(a,b)):compare_population(x,y,f'{path}[{i}]')
        elif isinstance(a,(float,int)) and not isinstance(a,bool) and isinstance(b,(float,int)) and not isinstance(b,bool):
            difference=abs(a-b);max_population_difference=max(max_population_difference,difference)
            if difference>1e-12:errors.append(dict(field=path,current=a,archived=b))
        elif a!=b:errors.append(dict(field=path,current=a,archived=b))
    for seed,population in data.get('populations',{}).items():
        archived_population=json.loads((ROOT/f"results/tcss_first_batch_20261028/core/populations/{seed}_{data['settings']['occupancy']}.json").read_text())
        compare_population(population,archived_population)
    if not data.get('populations'):errors.append(dict(field='populations',reason='Full input export missing'))
    for run in data['runs']:
        s=run['settings'];archived=next(c for c in checks if c['seed']==s['seed'] and c['occupancy']==s['occupancy']
            and c['model']==s['model'] and c['information']==s['information'] and c.get('variant','base')=='base')
        if run['population_sha256']!=archived['population_sha256']:raw_population_hashes_match=False
        if run['initial_occupancy_sha256']!=archived['initial_occupancy_sha256']:errors.append(dict(settings=s,field='initial_occupancy_sha256'))
        for row in run['outcomes']:
            count+=1;old=expected[(s['seed'],s['occupancy'],s['model'],s['information'],row['driver'])]
            for key in ('success','chosen_space','search_s','search_distance_m','walk_m','exit_distance_m','lost_claims','parking_time_s'):
                a,b=row[key],old[key]
                if key=='success':different=a!=(b=='True')
                elif key=='chosen_space':different=a!=(b or None)
                elif a is None:different=bool(b)
                else:different=not b or abs(a-float(b))>1e-8
                if different:errors.append(dict(settings=s,driver=row['driver'],field=key,current=a,archived=b))
    report=dict(passed=not errors,scenarios=len(data['runs']),driver_scenario_records=count,
        archive='tcss_first_batch_20261028',population=data['settings']['population_size'],
        occupancy=data['settings']['occupancy'],seed=data['settings']['seed'],
        models=data['models'],absolute_tolerance=1e-8,errors=errors,
        population_numeric_tolerance=1e-12,max_absolute_population_difference=max_population_difference,
        raw_population_hashes_match=raw_population_hashes_match,
        bundle_sha256=data.get('source_manifest',{}).get('bundle_sha256'))
    (folder/'full_size_verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report));assert not errors


if __name__=='__main__':main()
