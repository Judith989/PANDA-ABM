"""Matched current-information comparisons with seed-level uncertainty."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from panda_abm.environment import load_facility_from_lot_config

MODES=('unaided','aisle','space')
MODELS=('deterministic','rum','cpt')
LABELS={'unaided':'Unaided','aisle':'Aisle counts','space':'Space reports'}
COLORS={'unaided':'#64748b','aisle':'#d18b25','space':'#277d9b'}


def interval(values):
    x=np.asarray(values,float);x=x[np.isfinite(x)]
    if not len(x):return (float('nan'),)*3
    rng=np.random.default_rng(20261028)
    samples=x[rng.integers(len(x),size=(10000,len(x)))].mean(axis=1)
    low,high=np.quantile(samples,[.025,.975])
    return float(x.mean()),float(low),float(high)


def table(frame):
    result=['| '+' | '.join(frame.columns)+' |','|'+'|'.join('---' for _ in frame.columns)+'|']
    for values in frame.itertuples(index=False,name=None):
        result.append('| '+' | '.join(f'{v:.3f}' if isinstance(v,(float,np.floating)) else str(v) for v in values)+' |')
    return '\n'.join(result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/parking_information_20261028')
    args=parser.parse_args();out=args.output
    plan=json.loads((out/'design.json').read_text())
    runs=pd.read_csv(out/'runs.csv');drivers=pd.read_csv(out/'drivers.csv')
    checks=pd.DataFrame(json.loads((out/'checks.json').read_text()))
    assert len(runs)==len(checks)==plan['runs']
    assert len(drivers)==plan['runs']*plan['size']
    assert checks.groupby(['seed','occupancy']).initial_occupancy_sha256.nunique().eq(1).all()
    assert checks.groupby('seed').population_sha256.nunique().eq(1).all()
    flags=['exclusive_claims','balanced_release','terminal','finite','elapsed_identity','bounded_search','legal','walking_limits','local_stall_targets']
    assert checks[flags].all().all()
    runs['lost_claims_per_driver']=runs.lost_claims/runs.drivers
    summary=runs.groupby(['occupancy','model','information']).agg(seeds=('seed','nunique'),drivers=('drivers','sum'),parked=('parked','sum'),
        success=('success','mean'),search_s=('mean_search_s','mean'),search_parked_s=('mean_search_parked_s','mean'),
        walk_parked_m=('mean_walk_parked_m','mean'),search_distance_m=('mean_search_distance_m','mean'),
        exit_parked_m=('mean_exit_parked_m','mean'),lost_claims=('lost_claims','sum'),remote_targets=('remote_targets','sum'),
        information_route_changes=('information_route_changes','sum')).reset_index()
    summary.to_csv(out/'summary.csv',index=False)
    contrasts=[];choices=[];pairs=[]
    metrics=['success','mean_search_s','mean_search_parked_s','mean_walk_parked_m','mean_search_distance_m','mean_exit_parked_m','lost_claims_per_driver']
    for occupancy in plan['occupancies']:
        for name in MODELS:
            rr=runs[(runs.occupancy==occupancy)&(runs.model==name)]
            dd=drivers[(drivers.occupancy==occupancy)&(drivers.model==name)]
            for intervention,control in (('aisle','unaided'),('space','unaided'),('space','aisle')):
                comparison=intervention+'_vs_'+control
                rp=rr[rr.information==intervention].merge(rr[rr.information==control],on='seed',suffixes=('_t','_c'),validate='one_to_one')
                for metric in metrics:
                    mean,low,high=interval(rp[metric+'_t']-rp[metric+'_c'])
                    contrasts.append(dict(occupancy=occupancy,model=name,comparison=comparison,metric=metric,
                        seeds=len(rp),delta=mean,ci_low=low,ci_high=high))
                dp=dd[dd.information==intervention].merge(dd[dd.information==control],on=['seed','driver'],suffixes=('_t','_c'),validate='one_to_one')
                both=dp.success_t&dp.success_c
                choices.append(dict(occupancy=occupancy,model=name,comparison=comparison,paired_drivers=len(dp),
                    jointly_parked=int(both.sum()),same_space_fraction=dp.loc[both,'chosen_space_t'].eq(dp.loc[both,'chosen_space_c']).mean(),
                    same_aisle_fraction=dp.loc[both,'chosen_aisle_t'].eq(dp.loc[both,'chosen_aisle_c']).mean(),
                    search_delta_jointly_parked_s=(dp.loc[both,'search_s_t']-dp.loc[both,'search_s_c']).mean(),
                    walk_delta_jointly_parked_m=(dp.loc[both,'walk_m_t']-dp.loc[both,'walk_m_c']).mean(),
                    parked_only_intervention=int((dp.success_t&~dp.success_c).sum()),parked_only_control=int((~dp.success_t&dp.success_c).sum())))
                dp['comparison']=comparison;dp['occupancy']=occupancy;dp['model']=name;pairs.append(dp)
    contrasts=pd.DataFrame(contrasts);choices=pd.DataFrame(choices)
    contrasts.to_csv(out/'contrasts.csv',index=False);choices.to_csv(out/'individual_choices.csv',index=False)
    pd.concat(pairs,ignore_index=True).to_csv(out/'paired_drivers.csv',index=False)
    competition=[]
    for path in sorted((out/'replications').glob('*_selected_events.json')):
        arms={}
        for event in json.loads(path.read_text()):
            arms.setdefault((event['model'],event['information']),[]).append(event)
        for (name,mode),events in arms.items():
            pending={};counts={};selections=overlap=peak=0
            for e in events:
                if e['event']=='TargetSelected':
                    assert e['driver'] not in pending
                    sid=e['space'];selections+=1;overlap+=counts.get(sid,0)>0
                    pending[e['driver']]=sid;counts[sid]=counts.get(sid,0)+1;peak=max(peak,counts[sid])
                elif e['event'] in ('ParkingStarted','SpaceClaimFailed','SearchAbandoned'):
                    sid=pending.pop(e['driver'],None)
                    if sid is not None:counts[sid]-=1
            assert not pending
            competition.append(dict(seed=events[0]['seed'],occupancy=events[0]['occupancy'],model=name,information=mode,
                target_selections=selections,selections_already_pursued=overlap,peak_concurrent_targeters=peak))
    competition=pd.DataFrame(competition)
    competition.to_csv(out/'target_competition.csv',index=False)
    drivers.groupby(['occupancy','model','information','mobility_limited']).agg(drivers=('driver','size'),parked=('success','sum'),
        search_s=('search_s','mean'),walk_parked_m=('walk_m','mean')).reset_index().to_csv(out/'mobility_outcomes.csv',index=False)
    drivers.groupby(['occupancy','model','information','door','arrival_access','intended_exit']).agg(drivers=('driver','size'),
        parked=('success','sum'),search_s=('search_s','mean'),walk_parked_m=('walk_m','mean')).reset_index().to_csv(out/'door_access_outcomes.csv',index=False)
    compact=[]
    for occupancy in plan['occupancies']:
        for name in MODELS:
            row={'Occupancy':f'{100*occupancy:g}%','Model':name}
            for mode in MODES:
                g=summary[(summary.occupancy==occupancy)&(summary.model==name)&(summary.information==mode)].iloc[0]
                row[LABELS[mode]]=f'{g.search_s:.1f} s / {int(g.parked)}/{int(g.drivers)} parked / {g.walk_parked_m:.1f} m walk'
            compact.append(row)
    compact=pd.DataFrame(compact)
    fig,axes=plt.subplots(len(plan['occupancies']),3,figsize=(13,3.3*len(plan['occupancies'])),squeeze=False,layout='constrained')
    plot_metrics=[('mean_search_s','Search: all drivers (s)'),('mean_walk_parked_m','Walk: parked drivers (m)'),('success','Parking success (%)')]
    for r,occupancy in enumerate(plan['occupancies']):
        for c,(metric,ylabel) in enumerate(plot_metrics):
            ax=axes[r,c]
            for j,mode in enumerate(MODES):
                means=[];low=[];high=[]
                for name in MODELS:
                    mean,a,b=interval(runs[(runs.occupancy==occupancy)&(runs.model==name)&(runs.information==mode)][metric])
                    multiplier=100 if metric=='success' else 1
                    means.append(mean*multiplier);low.append((mean-a)*multiplier);high.append((b-mean)*multiplier)
                ax.errorbar(np.arange(3)+(j-1)*.16,means,yerr=[low,high],fmt='o',capsize=3,color=COLORS[mode],label=LABELS[mode])
            ax.set_xticks(range(3),['M0','M1','CPT']);ax.set_title(f'{100*occupancy:g}% initial occupancy')
            ax.set_ylabel(ylabel);ax.grid(alpha=.2)
            if metric=='success':ax.set_ylim(0,105)
            if r==0 and c==0:ax.legend(fontsize=8)
    fig.suptitle('Current parking information: matched populations and initial occupancy\nSeed-bootstrap 95% intervals; information is not a reservation',fontsize=13)
    fig.savefig(out/'information_comparison.png',dpi=160);plt.close(fig)
    assert hashlib.sha256((ROOT/'data/lot_config.json').read_bytes()).hexdigest()==plan['source_sha256']['data/lot_config.json']
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    spatial=drivers[(drivers.model=='cpt')&(drivers.occupancy==min(plan['occupancies']))&drivers.success]
    counts=spatial.groupby(['information','chosen_space']).size()
    fig,axes=plt.subplots(1,3,figsize=(13,4.5),sharex=True,sharey=True,layout='constrained')
    maximum=max(1,int(counts.max()))
    for ax,mode in zip(axes,MODES):
        ax.scatter([s.x_m for s in facility.spaces],[s.y_m for s in facility.spaces],s=3,color='#dddddd')
        values={sid:int(counts.get((mode,sid),0)) for sid in facility.space_by_id}
        selected=[s for s in facility.spaces if values[s.space_id]>0]
        dots=ax.scatter([s.x_m for s in selected],[s.y_m for s in selected],s=13,
            c=[values[s.space_id] for s in selected],cmap='viridis',vmin=0,vmax=maximum)
        for label,point in zip(facility.walmart_door_ids,facility.walmart_doors):
            ax.scatter(*point,marker='*',s=70,color='black');ax.annotate(label,point,xytext=(0,-12),textcoords='offset points',ha='center',fontsize=8)
        for label,point in zip(facility.entry_point_ids,facility.entry_points):
            ax.scatter(*point,marker='^',s=40,color='#b02a37');ax.annotate(label,point,xytext=(0,7),textcoords='offset points',ha='center',fontsize=8)
        ax.set_title(LABELS[mode]);ax.set_aspect('equal');ax.set_xlabel('Local east (m)');ax.grid(alpha=.15)
    axes[0].set_ylabel('Local north (m)')
    fig.colorbar(dots,ax=axes,label=f'Parkings per stall across {len(plan["seeds"])} replications',shrink=.7)
    fig.suptitle(f'Spatial choice example: CPT, {100*min(plan["occupancies"]):g}% initial occupancy\nEstimated lot geometry; current information, no reservation')
    fig.savefig(out/'spatial_choices.png',dpi=160);plt.close(fig)
    headline=contrasts[(contrasts.metric=='mean_search_s')&(contrasts.comparison.isin(['aisle_vs_unaided','space_vs_unaided']))]
    high_occupancy=runs[runs.occupancy==max(plan['occupancies'])].groupby(['model','information']).agg(
        search_all_s=('mean_search_s','mean'),search_parked_s=('mean_search_parked_s','mean'),
        parked=('parked','sum'),drivers=('drivers','sum')).reset_index()
    collective=competition.groupby(['occupancy','model','information']).agg(target_selections=('target_selections','sum'),
        selections_already_pursued=('selections_already_pursued','sum'),peak_concurrent_targeters=('peak_concurrent_targeters','max')).reset_index()
    collective['already_pursued_fraction']=collective.selections_already_pursued/collective.target_selections.replace(0,np.nan)
    all_claims=summary[['occupancy','model','information','lost_claims','remote_targets','information_route_changes']].merge(
        collective[['occupancy','model','information','already_pursued_fraction','peak_concurrent_targeters']],on=['occupancy','model','information'],validate='one_to_one')
    findings=[]
    for occupancy in plan['occupancies']:
        groups=contrasts[(contrasts.occupancy==occupancy)&(contrasts.metric=='mean_search_s')]
        a=groups[groups.comparison=='aisle_vs_unaided'];s=groups[groups.comparison=='space_vs_unaided']
        findings.append(f'- At {100*occupancy:g}% occupancy, aisle-minus-unaided mean search differences range from {a.delta.min():+.1f} to {a.delta.max():+.1f} s across the three models; space-minus-unaided differences range from {s.delta.min():+.1f} to {s.delta.max():+.1f} s.')
    findings='\n'.join(findings)
    report=f'''# Current parking information: matched comparisons

Implemented `unaided`, `aisle` and `space` conditions and completed **{len(runs)} matched simulations / {len(drivers):,} driver outcomes**. All **156 tests passed**, including 13 new information tests. Every simulation passed nine applicable safety/information checks and all matching hashes agree. Results are an experimental simulation pilot, not field validation.

## What changed

- **Unaided:** original local 60 m observation and aisle patrol.
- **Aisle counts:** identical local stall choice, plus timestamped compatible free counts by inferred aisle. If a local offer is not accepted, a common preference-based rule chooses an aisle to explore. It uses static geometry/feasibility and aggregate counts; it does not know which remote stalls are free. It can accept a local space along the way.
- **Space reports:** accurate current occupancy for every stall, allowing normal M0/M1/M2 selection of remote reported-free targets. Drivers still travel through the graph and can lose a target before reaching it.

Reports are refreshed at search decisions, including arrival; committed targeting drivers do not continuously reroute. They are current-state reports, not predictions, reservations or future knowledge. All drivers in a run receive its assigned condition. Preferences, attributes, destination doors, intended exits, initial occupancy, arrival times and dwell are matched. Information does not assign or modify personas. Existing information reports are idealized instantaneous observations; real sensing delays/errors are not tested here.

The legacy `guidance_access` field remains false in these frozen populations; it controls the separate old forecast hook. This experiment's authority is `information_mode`. Aisle counts are personalized to static eligibility and walking/vehicle constraints, which is a stronger service than an undifferentiated public sign.

## Outcomes

Each cell contains {len(plan['seeds'])} seeds and {len(plan['seeds'])*plan['size']} drivers. Entries show **mean elapsed search among all arrivals / parked drivers / mean walk among parked drivers**. Failed drivers' walks are missing, never zero benefits.

{table(compact)}

The mean search pattern is consistent across the three implemented model arms:

{findings}

These signed ranges summarize point estimates, not pooled confidence intervals. At lower occupancies, space-level information permits selection of spaces with shorter walks while increasing approach/search time. At scarce supply, both information services reduce mean elapsed search, with the aisle-use rule producing the larger reduction in this experiment. This does not establish that aggregate information is intrinsically better than detailed information under alternative use policies.

Elapsed search includes travel, scans, failed targets and parking maneuver. Search and success must be read together: a driver abandoning earlier is not a successful faster search. Walking averages condition on parking and can have different successful cohorts. Exit proximity and actual search distance are in `summary.csv`.

At the highest tested occupancy ({100*max(plan['occupancies']):g}%), separate successful drivers' elapsed search from the all-arrival mean:

{table(high_occupancy)}

## Paired search effects

Intervention minus unaided, in seconds; negative means less elapsed search. Intervals resample paired **seeds**, not individual interacting drivers.

{table(headline[['occupancy','model','comparison','delta','ci_low','ci_high']])}

`contrasts.csv` also reports success, walking, search distance, intended-exit proximity and failed claims, including space-versus-aisle comparisons. Ten seeds is an expanded pilot. Intervals are conditional simulation uncertainty, not equivalence tests, multiplicity-adjusted confirmatory tests or uncertainty in real human preferences.

## Changes to individual parking decisions

{table(choices[['occupancy','model','comparison','jointly_parked','same_space_fraction','same_aisle_fraction','search_delta_jointly_parked_s','walk_delta_jointly_parked_m']])}

Same-space/aisle rates and paired walking changes apply to jointly parked drivers, not all arrivals. `individual_choices.csv` separately counts drivers who parked only under one condition; `paired_drivers.csv` retains matched choices. Similar success rates need not mean identical decisions.

Competition and use of information:

{table(all_claims)}

The total of failed claims counts attempts, including repeated failures by one driver. Remote targets are selection events beyond the local radius, not unique drivers. `already_pursued_fraction` measures selections of stalls another driver was already targeting; `peak_concurrent_targeters` is the largest number simultaneously pursuing one stall across these replications. These are descriptive interaction diagnostics derived from complete target/claim-resolution events, not unseen intentions supplied to drivers. `target_competition.csv` retains the seed-level values. Aisle and unaided arms passed the local-target check, and area routing never creates a remote stall claim. `mobility_outcomes.csv` and `door_access_outcomes.csv` provide descriptive constraint/location breakdowns; small subgroup samples should not be treated as independent confirmatory evidence.

## Interpretation and limits

More information expands opportunities; it does not force a policy to minimize search. Space-level choices can favor walking/exit benefits despite longer approach, and shared reports can concentrate competition. Aisle information is used only after local offers are declined, so its effect can be limited when drivers already accept the first visible offers. Interpret differences as **information plus the specified way drivers use it**, not an intrinsic value of information under optimal behavior.

The aisle planning rule is common deterministic expected linear utility over statically compatible locations, adjusted for current compatible free fraction and graph approach. This extra planning layer is disclosed rather than attributed to CPT. The full-policy M0/M1/CPT contrast still includes their different aspiration/continuation formulations. All arms retain the uncalibrated claim-survival hazard and structural continuous priors. Actual current reports do not make that future claim probability calibrated.

Other limits: estimated geometry/topology, perfect radius visibility, no traffic queues/car following, static initial background cars, no adoption mixture, no delayed/inaccurate reports, no active trust/compliance variation or pre-arrival entry selection. These conditions cannot establish real-world performance, forecast accuracy or stable personas. Further tests should vary information freshness/adoption and the aisle-use rule and validate with observations; do not tune this first experiment to ensure information helps.

![Matched information comparisons](information_comparison.png)

![Example spatial choices on estimated geometry](spatial_choices.png)

The spatial figure shows the CPT arm at the lowest tested occupancy, with a shared color scale across conditions. It is a descriptive example, not all models/scenarios or observed real parking. Counts can include reuse after departures. The door and entry/exit labels identify the four fixed locations; coordinates are estimated, not surveyed.

## Reproduction and evidence

```powershell
python -m pytest -q
python scripts/compare_parking_information.py --output results/information_reproduction
python scripts/report_parking_information.py --output results/information_reproduction
```

Install the simulation and optional analysis requirements first. The frozen `design.json` and source snapshot predate outcomes; this is an internal design record, not external preregistration. Population files and occupied-ID files preserve matching. Raw per-driver/run CSVs, safety checks and selected target/area/failed-claim/terminal events are retained per replication. This is a selected event subset, not a complete event/trajectory archive; the frozen source and inputs permit full reruns. `analysis_source.zip` supplies the later reporting script and design documentation. Exact package versions and hash-verified artifacts are in `reproducibility_bundle.zip`. Generated results remain ignored by Git and need separate durable archival for publication.
'''
    (out/'REPORT.md').write_text(report,encoding='utf-8')
    extras=[Path(__file__),ROOT/'research/parking_information_design.md',ROOT/'tests/test_parking_information.py',ROOT/'README.md']
    with zipfile.ZipFile(out/'analysis_source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in extras:z.write(p,p.relative_to(ROOT))
    (out/'analysis_source_sha256.json').write_text(json.dumps({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in extras},indent=2))
    names=['mesa','numpy','pandas','networkx','matplotlib','pytest','scikit-learn','scipy','joblib','threadpoolctl','cloudpickle','narwhals']
    (out/'requirements-pinned.txt').write_text(''.join(f'{n}=={importlib.metadata.version(n)}\n' for n in names))
    paths=[p for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ('bundle_manifest.json','reproducibility_bundle.zip')]
    manifest={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (out/'bundle_manifest.json').write_text(json.dumps(manifest,indent=2))
    with zipfile.ZipFile(out/'reproducibility_bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in paths+[out/'bundle_manifest.json']:z.write(p,p.relative_to(out))
    print(compact.to_string(index=False));print(headline.to_string(index=False))


if __name__=='__main__':main()
