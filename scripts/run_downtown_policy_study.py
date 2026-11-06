"""Matched downtown policy experiment. Defaults to writing a plan, not running it."""
from pathlib import Path
import argparse,json,sys,itertools,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser();p.add_argument('--environment',type=Path,default=ROOT/'data/lot_config.downtown_laramie.json');p.add_argument('--output',type=Path,default=ROOT/'research/downtown_policy_study');p.add_argument('--seeds',type=int,default=20);p.add_argument('--execute',action='store_true');p.add_argument('--limit',type=int);a=p.parse_args()
    if not 1<=a.seeds<=30:p.error('Choose 1–30 seeds')
    from panda_abm.twin.environments import validate_environment
    env=validate_environment(json.loads(a.environment.read_text(encoding='utf8')))
    conditions=list(itertools.product(['configured','unrestricted'],['unaided','aisle','space'],['deterministic','rum','cpt'],['off','medium'],[20,60],range(1000,1000+a.seeds)))
    plan=dict(status='planned_not_executed',simulations=len(conditions),environment_sha256=env['environment_sha256'],policies=['configured','unrestricted'],information=['unaided','aisle','space'],models=['deterministic','rum','cpt'],through_traffic=['off','medium'],arrival_intervals_s=[20,60],seeds=list(range(1000,1000+a.seeds)),background_departures='residual',visit_profile='mixed',parking_demand_duration_s=7200,through_demand_s=7200,observation_duration_s=21600,initial_occupancy=.8,notes=['Assumed demand and activity distributions, not field calibrated.','Match seeds, activity durations, preferences and initial occupancy across within-layout comparisons.','CPT references change when policy changes legal supply.','Six-hour cutoff can leave late-arriving long visits unfinished; report censoring.','No claim of real traffic prediction.'])
    a.output.mkdir(parents=True,exist_ok=True);(a.output/'design.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf8')
    if not a.execute:print(json.dumps(dict(status=plan['status'],simulations=len(conditions),design=str(a.output/'design.json'))));return
    if env['config']['meta'].get('review_required'):raise ValueError('Review the environment first, then export the experimental configuration from the dashboard')
    from panda_abm.twin.platform import simulate
    target=a.output/'simulations.jsonl'
    with target.open('w',encoding='utf8') as h:
        for index,(policy,info,model,through,gap,seed) in enumerate(conditions):
            if a.limit is not None and index>=a.limit:break
            settings=dict(environment=env,parking_policy=policy,information=info,model=model,through_traffic=through,through_demand_s=7200,traffic_enabled=True,arrival_interval_s=gap,seed=seed,background_departures='residual',visit_profile='mixed',demand_duration_s=7200,simulation_duration_s=21600,occupancy=.8)
            result=simulate(settings);h.write(json.dumps(result,allow_nan=False)+'\n');h.flush();print(f'{index+1}/{len(conditions)} {policy} {info} {model} {through} gap={gap} seed={seed}',flush=True)
    plan['status']='executed_subset' if a.limit is not None and a.limit<len(conditions) else 'executed';plan['executed_simulations']=index if a.limit is not None and index>=a.limit else len(conditions)
    plan['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'panda_abm').rglob('*.py')}
    (a.output/'design.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf8')
if __name__=='__main__':main()
