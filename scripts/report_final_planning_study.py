"""Complete main-report tables: every completed condition, with paired seed uncertainty."""
from pathlib import Path
import csv,gzip,json,math,sys
from collections import defaultdict
import numpy as np

def report(out):
    out=Path(out);rows=[];groups=defaultdict(list);records=[]
    status=json.loads((out/'status.json').read_text(encoding='utf8'))
    if not status.get('finished') or status.get('failed') or status.get('stopped'):
        raise ValueError('The campaign is incomplete or failed; refusing to generate final paper results.')
    for p in sorted((out/'records').glob('*.json.gz')):
        with gzip.open(p,'rt',encoding='utf8') as f:r=json.load(f)
        # Keep the report's memory bounded; full traces remain in immutable per-job records.
        r={k:r[k] for k in ('job','summary','attributes_sha256','initial_occupancy_sha256','segment_labels','traffic','outcomes')}
        r['traffic']={'aisle_delay_s':r['traffic'].get('aisle_delay_s',{})}
        r['outcomes']=[{k:o.get(k) for k in ('walking_limited','accessible_eligible','information_access','observed_arrival','success','right_censored')} for o in r['outcomes']]
        records.append(r);j=r['job'];key=json.dumps({k:v for k,v in j.items() if k not in ('id','seed')},sort_keys=True)
        groups[key].append(r)
    metrics=sorted({k for r in records for k,v in r['summary'].items() if v is None or isinstance(v,(int,float))})
    def interval(values):
        a=np.asarray(values,dtype=float)
        if not len(a):return None,None,None
        rng=np.random.default_rng(80517)
        means=a[rng.integers(0,len(a),size=(10000,len(a)))].mean(axis=1)
        return float(a.mean()),float(np.quantile(means,.025)),float(np.quantile(means,.975))
    for key,rs in groups.items():
        for metric in metrics:
            vals=[r['summary'][metric] for r in rs if r['summary'].get(metric) is not None]
            mean,lo,hi=interval(vals)
            rows.append(dict(condition=key,metric=metric,simulations=len(rs),contributing_simulations=len(vals),mean=mean,lower95=lo,upper95=hi))
    def write(name,data):
        if not data:return
        with (out/name).open('w',newline='',encoding='utf8') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    write('all_condition_estimates.csv',rows)
    # Information effects preserve all settings and pair by seed, including adverse/null effects.
    byjob={json.dumps({k:v for k,v in r['job'].items() if k!='id'},sort_keys=True):r for r in records}
    effects=defaultdict(list)
    for r in records:
        j=r['job']
        if j['information']=='unaided':continue
        baseline={k:v for k,v in j.items() if k!='id'};baseline['information']='unaided'
        # Adoption/delay experiments use the matched core baseline.
        if j['stage'] in ('adoption','delay'):
            baseline.pop('adoption',None);baseline.pop('delay',None);baseline['stage']='core';baseline['occupancy']=.95
        b=byjob.get(json.dumps(baseline,sort_keys=True))
        if not b:continue
        assert r['attributes_sha256']==b['attributes_sha256']
        assert r['initial_occupancy_sha256']==b['initial_occupancy_sha256']
        condition=json.dumps({k:v for k,v in j.items() if k not in ('id','seed')},sort_keys=True)
        for metric in metrics:
            x=r['summary'].get(metric);y=b['summary'].get(metric)
            if x is not None and y is not None:effects[condition,metric].append(x-y)
    erows=[]
    for (condition,metric),values in effects.items():
        mean,lo,hi=interval(values);erows.append(dict(condition=condition,metric=metric,matched_simulations=len(values),informed_minus_unaided=mean,lower95=lo,upper95=hi))
    write('all_information_effects.csv',erows)
    contrasts=defaultdict(list)
    for r in records:
        j=r['job'];bjob={k:v for k,v in j.items() if k!='id'};stage=j['stage'];label=None
        if stage=='supply':bjob['supply']='pool_closed' if j['supply'].startswith('pool_') else 'baseline';label='supply'
        elif stage=='time_limits':bjob['policy']='unrestricted';label='time_limit'
        elif stage=='accessibility':bjob['accessible']='baseline';label='accessible_allocation'
        elif stage in ('demand','traffic_control','departures','preference_control','cpt_control','timing','signals','through_traffic'):
            for k in ('gap','traffic','background','population_control','dt','cycle','through'):bjob.pop(k,None)
            bjob['stage']='core';bjob['occupancy']=.95;label=stage
            if j['environment']=='walmart_original':bjob['stage']='geometry'
        if not label or bjob=={k:v for k,v in j.items() if k!='id'}:continue
        b=byjob.get(json.dumps(bjob,sort_keys=True))
        if not b:continue
        condition=json.dumps({k:v for k,v in j.items() if k not in ('id','seed')},sort_keys=True)
        for metric in metrics:
            x=r['summary'].get(metric);y=b['summary'].get(metric)
            if x is not None and y is not None:contrasts[condition,metric,label].append(x-y)
    cr=[]
    for (condition,metric,label),vals in contrasts.items():
        m,l,h=interval(vals);cr.append(dict(condition=condition,comparison=label,metric=metric,matched_simulations=len(vals),difference=m,lower95=l,upper95=h))
    write('all_controlled_comparisons.csv',cr)
    model_effects=defaultdict(list)
    for r in records:
        j=r['job']
        if j['model']=='deterministic':continue
        bj={k:v for k,v in j.items() if k!='id'};bj['model']='deterministic'
        b=byjob.get(json.dumps(bj,sort_keys=True))
        if not b:continue
        key=json.dumps({k:v for k,v in j.items() if k not in ('id','seed')},sort_keys=True)
        for metric in metrics:
            x=r['summary'].get(metric);y=b['summary'].get(metric)
            if x is not None and y is not None:model_effects[key,metric].append(x-y)
    mr=[]
    for (condition,metric),vals in model_effects.items():
        m,l,h=interval(vals);mr.append(dict(condition=condition,metric=metric,matched_simulations=len(vals),model_minus_deterministic=m,lower95=l,upper95=h))
    write('all_decision_model_comparisons.csv',mr)
    subgroup=[];hotspots=[]
    for r in records:
        j=r['job']
        for field in ('walking_limited','accessible_eligible','information_access'):
            values={str(o.get(field)) for o in r['outcomes']}
            for value in values:
                osub=[o for o in r['outcomes'] if str(o.get(field))==value and o.get('observed_arrival')]
                if not osub:continue
                subgroup.append(dict(job=j['id'],stage=j['stage'],environment=j['environment'],model=j['model'],information=j['information'],seed=j['seed'],group_field=field,group=value,drivers=len(osub),parked=sum(o.get('success',False) for o in osub),unfinished=sum(o.get('right_censored',False) for o in osub)))
        for segment,delay in r['traffic'].get('aisle_delay_s',{}).items():hotspots.append(dict(job=j['id'],segment=segment,label=json.dumps(r['segment_labels'].get(segment,{})),delay_vehicle_seconds=delay))
    write('all_driver_group_counts.csv',subgroup);write('all_segment_delays.csv',hotspots)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':13,'font.weight':'bold','axes.labelweight':'bold','axes.labelsize':14,'xtick.labelsize':11,'ytick.labelsize':11})
    figs=out/'figures';figs.mkdir(exist_ok=True)
    for metric in ('search_s','success_pct','walk_m','exit_m','failed_claims','traffic_delay_s','jam_clock_s','peak_queue','vehicle_distance_m','pedestrian_wait_s','unfinished_trips','open_supply_utilization_pct'):
        subset=[x for x in erows if x['metric']==metric]
        if not subset:continue
        # Pages preserve every contrast while keeping labels legible.
        for page,start in enumerate(range(0,len(subset),30),1):
            part=subset[start:start+30];fig,ax=plt.subplots(figsize=(12,max(5,len(part)*.32)))
            ys=np.arange(len(part));means=np.array([x['informed_minus_unaided'] for x in part]);lo=np.array([x['lower95'] for x in part]);hi=np.array([x['upper95'] for x in part])
            ax.errorbar(means,ys,xerr=[np.maximum(0,means-lo),np.maximum(0,hi-means)],fmt='o',capsize=3);ax.axvline(0,color='black',lw=1)
            labels=[]
            for x in part:
                d=json.loads(x['condition']);labels.append(' / '.join(str(v) for v in d.values()))
            ax.set_yticks(ys,labels);ax.invert_yaxis();ax.set_xlabel(metric+': informed minus unaided');ax.grid(axis='x',alpha=.2);fig.tight_layout()
            fig.savefig(figs/f'{metric}_{page:02}.pdf',bbox_inches='tight');plt.close(fig)
    def esc(s):return str(s).replace('_',r'\_').replace('%',r'\%').replace('&',r'\&')
    lines=[r'\section{Complete planning simulation results}',r'These are conditional simulation estimates, not calibrated predictions of actual traffic. All planned conditions, including null and adverse estimates, are retained. Intervals resample independent simulation seeds; drivers within a simulation are not treated as independent. Walking summaries concern parked drivers. Ongoing jams and unfinished trips are censored by the observation window.']
    for key in groups:
        lines += [r'\subsection*{'+esc(key)+'}',r'\begin{longtable}{lrrr}',r'Metric & Mean & Lower 95\% & Upper 95\% \\ \hline']
        for row in rows:
            if row['condition']==key and row['mean'] is not None:lines.append(esc(row['metric'])+' & '+' & '.join(f"{row[k]:.3f}" for k in ('mean','lower95','upper95'))+r' \\')
        lines.append(r'\end{longtable}')
    for title,data,value in [('Matched information effects',erows,'informed_minus_unaided'),('Controlled planning comparisons',cr,'difference'),('Decision model comparisons',mr,'model_minus_deterministic')]:
        lines.append(r'\section{'+title+'}')
        for condition in dict.fromkeys(x['condition'] for x in data):
            lines.extend([r'\subsection*{'+esc(condition)+'}',r'\begin{longtable}{lrrr}',r'Metric & Difference & Lower 95\% & Upper 95\% \\ \hline'])
            for x in data:
                if x['condition']==condition:lines.append(esc(x['metric'])+' & '+' & '.join(f"{x[k]:.3f}" for k in (value,'lower95','upper95'))+r' \\')
            lines.append(r'\end{longtable}')
    (out/'complete_results.tex').write_text('\n'.join(lines),encoding='utf8')
    (out/'REPORT_README.md').write_text(f'# Main results package\n\n{len(records)} completed simulations; {len(groups)} condition cells. All cells appear in complete_results.tex (requires longtable). Complete numeric condition and matched-information tables are in CSV. Plot pages retain every computed information contrast. This is a long main report, not a supplementary file. Do not treat a partial campaign as final. Inspect status.json and failures.json before interpretation.\n',encoding='utf8')

if __name__=='__main__':report(Path(sys.argv[1]))
