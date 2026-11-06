"""Checkpointed planning campaign. Resume with the same output directory."""
from pathlib import Path
import argparse,concurrent.futures,gzip,hashlib,itertools,json,os,sys,time,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from planning_study_engine import simulate,MODELS,INFOS,digest

def design():
    jobs=[]
    def add(stage,envs,models=MODELS[:3],infos=INFOS,seeds=20,**grid):
        keys=list(grid)
        for values in itertools.product(envs,models,infos,range(1000,1000+seeds),*grid.values()):
            env,model,info,seed,*rest=values
            j=dict(stage=stage,environment=env,model=model,information=info,seed=seed,**dict(zip(keys,rest)))
            j['id']=digest(j)[:20];jobs.append(j)
    # The satellite geometry is the physical Walmart case; the retained original
    # inventory is a geometry-sensitivity case, not a surveyed traffic layout.
    primary=['walmart_satellite','downtown']
    add('core',primary,MODELS,seeds=30,occupancy=[.4,.8,.95])
    add('geometry',['walmart_original','synthetic'],occupancy=[.8,.95])
    add('scarcity',primary,free_count=[0,5])
    add('demand',primary,gap=[2,60])
    add('traffic_control',['walmart_original','walmart_satellite'],traffic=[False])
    add('adoption',primary,infos=INFOS[1:],adoption=[.25,.5,.75])
    add('delay',primary,infos=INFOS[1:],delay=[30,60])
    add('departures',primary,background=['residual'])
    add('time_limits',['downtown'],policy=['configured','unrestricted'],gap=[30,60],through=['off','medium'],visit=['mixed'],background=['residual'],demand_s=[3600],horizon=[21600])
    add('through_traffic',['downtown'],through=['low','medium','high'])
    for env in primary:
        add('supply',[env],infos=['unaided','space'],supply=['baseline','close_door','close_exit','close_spread','pool_closed','pool_door','pool_exit','pool_spread'],gap=[30],demand_s=[3600],horizon=[21600],background=['residual'],visit=['mixed' if env=='downtown' else 'baseline'])
    add('accessibility',primary,infos=['unaided','space'],accessible=['baseline','near_doors','spread'])
    add('preference_control',primary,population_control=['mean_preferences'])
    add('cpt_control',primary,models=['cpt'],population_control=['central_cpt'])
    add('timing',primary,MODELS,infos=['unaided','space'],seeds=10,dt=[.5,.25])
    add('signals',['downtown'],cycle=[72,120])
    return jobs

def execute(job,out):
    p=Path(out)/'records'/f"{job['id']}.json.gz"
    manifest=Path(out)/'source_manifest.json'
    source_hash=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if p.exists():
        with gzip.open(p,'rt',encoding='utf8') as f:r=json.load(f)
        if r['job']!=job:raise ValueError('Checkpoint does not match design')
        if r.get('source_manifest_sha256')!=source_hash:raise ValueError('Checkpoint belongs to another source version')
        return job['id'],r['wall_s'],True
    r=simulate(job)
    r['source_manifest_sha256']=source_hash
    assert all(r['invariants'].values()),r['invariants']
    temp=p.with_suffix('.tmp')
    with gzip.open(temp,'wt',encoding='utf8') as f:json.dump(r,f,allow_nan=False,separators=(',',':'))
    os.replace(temp,p)
    return job['id'],r['wall_s'],False

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--workers',type=int,default=4);ap.add_argument('--limit',type=int);args=ap.parse_args()
    out=Path(args.output).resolve();(out/'records').mkdir(parents=True,exist_ok=True)
    manifest=json.loads((out/'source_manifest.json').read_text(encoding='utf8'))
    for relative,expected in manifest['files'].items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=expected:
            raise ValueError('Frozen source mismatch: '+relative)
    jobs=design();jobs=jobs[:args.limit] if args.limit else jobs
    design_path=out/'design.json'
    if design_path.exists() and json.loads(design_path.read_text())!=jobs:
        raise ValueError('Refusing to mix different experiment designs in one directory')
    design_path.write_text(json.dumps(jobs,indent=2),encoding='utf8')
    from map_final_planning_study import maps
    maps(out)
    start=time.time();done=0;fail=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(execute,j,str(out)):j for j in jobs}
        for future in concurrent.futures.as_completed(futures):
            j=futures[future]
            try:
                _,wall,cached=future.result();done+=1
            except Exception:
                fail.append(dict(job=j,error=traceback.format_exc()));wall=None;cached=False
            status=dict(total=len(jobs),completed=done,failed=len(fail),elapsed_s=time.time()-start,last_job=j,last_wall_s=wall,cached=cached,finished=done+len(fail)==len(jobs))
            (out/'status.json').write_text(json.dumps(status,indent=2),encoding='utf8')
            if fail:(out/'failures.json').write_text(json.dumps(fail,indent=2),encoding='utf8')
            print(json.dumps(status),flush=True)
    if fail:raise SystemExit(1)
    from report_final_planning_study import report
    report(out)

if __name__=='__main__':main()
