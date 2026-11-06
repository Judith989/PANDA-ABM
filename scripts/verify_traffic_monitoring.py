"""Audit queue instrumentation against per-tick driver states, not real traffic data."""
from pathlib import Path
import collections
import csv
import hashlib
import json
import math
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'paper/platform_evaluation/traffic_monitoring_20261105'


def audit_case(name,settings):
    from panda_abm.twin.replay import LiveSimulation
    from panda_abm.core.traffic import DRIVING
    live=LiveSimulation(settings);model=live.model;opened={};closed=[];series=[];constraints=[];total_delay=0.
    for _ in range(settings['simulation_duration_s']):
        response=live.advance(1);snapshot=model.traffic.snapshot() if model.traffic else dict(enabled=False)
        if not model.traffic:
            series.append(dict(time_s=model.clock_s,queued_vehicles=None,aisles_with_jams=None,cumulative_delay_s=None));continue
        queue=collections.Counter();causes={};delays=collections.Counter()
        for a in model.agents:
            reason=getattr(a,'traffic_reason',None) if a.state in DRIVING and a.route else None
            if not reason:continue
            speed=getattr(a,'traffic_speed_m_s',0.)
            delay=max(0.,1-speed/model.search_speed_m_per_s);total_delay+=delay
            if speed>=.5:continue
            aisle=model.traffic.aisle_at((a.x_m,a.y_m));queue[aisle]+=1;delays[aisle]+=delay
            causes.setdefault(aisle,collections.Counter())[reason]+=1
            constraints.append(dict(time_s=model.clock_s,driver=a.driver_id,aisle=aisle,speed_m_s=speed,reason=reason,blocker=getattr(a,'traffic_blocker',None),x_m=a.x_m,y_m=a.y_m))
        assert dict(queue)==snapshot['queues']
        assert math.isclose(snapshot['cumulative_delay_s'],total_delay,abs_tol=1e-7)
        assert math.isclose(sum(snapshot['aisle_delay_s'].values()),total_delay,abs_tol=1e-7)
        eligible={a:n for a,n in queue.items() if n>=2}
        for aisle,count in eligible.items():
            e=opened.setdefault(aisle,dict(aisle=aisle,start_s=model.clock_s-1,peak_queue=0,cause_active_seconds=collections.Counter(),cause_vehicle_seconds=collections.Counter(),queued_vehicle_delay_s=0.))
            e['peak_queue']=max(e['peak_queue'],count)
            e['cause_active_seconds'].update({k:1 for k in causes[aisle]});e['cause_vehicle_seconds'].update(causes[aisle]);e['queued_vehicle_delay_s']+=delays[aisle]
        for aisle in set(opened)-set(eligible):
            e=opened.pop(aisle);e.update(end_s=model.clock_s-1,duration_s=model.clock_s-1-e['start_s'])
            if e['duration_s']>=5:closed.append(e)
        series.append(dict(time_s=model.clock_s,queued_vehicles=sum(queue.values()),aisles_with_jams=len(eligible),cumulative_delay_s=total_delay))
    snapshot=model.traffic.snapshot() if model.traffic else dict(enabled=False)
    if model.traffic:
        expected=closed+[dict(e,end_s=None,duration_s=model.clock_s-e['start_s']) for e in opened.values() if model.clock_s-e['start_s']>=5]
        key=lambda e:(e['aisle'],e['start_s'])
        actual=sorted(snapshot['jam_episodes'],key=key);expected=sorted(expected,key=key)
        assert len(actual)==len(expected)
        for a,b in zip(actual,expected):
            for field in ('aisle','start_s','end_s','duration_s','peak_queue','cause_active_seconds','cause_vehicle_seconds'):assert a[field]==b[field],(name,field,a[field],b[field])
            assert math.isclose(a['queued_vehicle_delay_s'],b['queued_vehicle_delay_s'],abs_tol=1e-7)
        clock=model.clock_s;before=json.dumps(snapshot,sort_keys=True)
        for _ in range(3):live.frame()
        assert model.clock_s==clock and json.dumps(model.traffic.snapshot(),sort_keys=True)==before
        assert all(e['duration_s']>=5 and e['minimum_queued_vehicles']==2 and e['peak_queue']>=2 for e in actual)
    else:actual=[]
    if name.endswith('single'):assert not actual and snapshot['cumulative_delay_s']==0
    public_settings={k:v for k,v in live.settings.items() if k!='environment'}
    public_settings['environment_id']=live.settings['environment']['id'] if live.settings['environment'] else 'walmart_original'
    env=live.settings['environment']
    provenance=dict(config_sha256=env['config_sha256'] if env else hashlib.sha256((ROOT/'data/lot_config.json').read_bytes()).hexdigest(),environment_sha256=env['environment_sha256'] if env else None)
    row=dict(case=name,model=settings.get('model','cpt'),layout=public_settings['environment_id'],traffic_enabled=bool(model.traffic),drivers=settings['population_size'],initial_free_spaces=settings['initial_free_count'],duration_s=model.clock_s,parked=response['summary']['parked'],jam_episodes=len(actual) if model.traffic else None,ongoing_jams=sum(e['end_s'] is None for e in actual) if model.traffic else None,peak_queued_per_aisle=max(snapshot.get('aisle_peak_queue',{}).values(),default=0) if model.traffic else None,longest_observed_jam_s=max((e['duration_s'] for e in actual),default=0) if model.traffic else None,traffic_delay_vehicle_s=snapshot.get('cumulative_delay_s'),pause_check_passed=True,instrumentation_check_passed=True)
    (OUT/(name+'.json')).write_text(json.dumps(dict(summary=row,settings=public_settings,provenance=provenance,traffic=snapshot,time_series=series,queued_driver_states=constraints),indent=2),encoding='utf8')
    return row


def main():
    from panda_abm.twin.environments import satellite_environment
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    for layout in ('original','satellite'):
        for model in ('deterministic','rum','cpt'):
            settings=dict(model=model,population_size=24,arrival_interval_s=1,simulation_duration_s=180,initial_free_count=5,information='space',traffic_enabled=True,seed=1000)
            if layout=='satellite':settings['environment']=satellite_environment()
            row=audit_case(layout+'_'+model,settings);rows.append(row);print(json.dumps(row),flush=True)
        for condition in ('single','disabled'):
            settings=dict(model='cpt',population_size=1 if condition=='single' else 24,arrival_interval_s=1,simulation_duration_s=180,initial_free_count=5,information='space',traffic_enabled=condition!='disabled',seed=1000)
            if layout=='satellite':settings['environment']=satellite_environment()
            rows.append(audit_case(layout+'_'+condition,settings))
    with (OUT/'summary.csv').open('w',newline='',encoding='utf8') as h:
        writer=csv.DictWriter(h,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    sources=[*sorted((ROOT/'panda_abm').rglob('*.py')),ROOT/'data/lot_config.json',ROOT/'data/lot_config.satellite_estimated.json',Path(__file__)]
    (OUT/'verification.json').write_text(json.dumps(dict(status='passed',cases=10,scope='Native simulation and per-tick recording verification; no browser UI or empirical traffic validation',source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}),indent=2),encoding='utf8')
    print('Saved '+str(OUT),flush=True)

if __name__=='__main__':main()
