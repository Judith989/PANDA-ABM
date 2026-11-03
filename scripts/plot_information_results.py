"""Build 15 exploratory research figures from a verified matched study.

Does not rerun simulations or change the frozen experiment archive.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from panda_abm.environment import load_facility_from_lot_config

MODES = ('unaided', 'aisle', 'space')
MODELS = ('deterministic', 'rum', 'cpt')
LABELS = dict(unaided='Unaided', aisle='Aisle information', space='Space information')
MODEL_LABELS = dict(deterministic='M0', rum='M1', cpt='CPT')
COLORS = dict(unaided='#566573', aisle='#b56700', space='#0072b2')
STYLE = dict(fontsize=16, fontweight='bold')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interval(values):
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(20261028)
    draws = x[rng.integers(len(x), size=(10000, len(x)))].mean(axis=1)
    return x.mean(), *np.quantile(draws, [.025, .975])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'results/parking_information_20261028')
    parser.add_argument('--output', type=Path, default=ROOT/'research/paper_assets/information_figures_20261028')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    if source == out or source in out.parents:
        raise ValueError('Use a separate output folder to preserve the original evidence archive.')
    inputs = ['design.json', 'drivers.csv', 'runs.csv', 'contrasts.csv',
              'individual_choices.csv', 'target_competition.csv', 'checks.json']
    manifest = json.loads((source/'bundle_manifest.json').read_text())
    for name in inputs:
        if sha(source/name) != manifest[name]:
            raise ValueError(f'Input checksum mismatch: {name}')
    plan = json.loads((source/'design.json').read_text())
    d = pd.read_csv(source/'drivers.csv')
    r = pd.read_csv(source/'runs.csv')
    contrasts = pd.read_csv(source/'contrasts.csv')
    choices = pd.read_csv(source/'individual_choices.csv')
    competition = pd.read_csv(source/'target_competition.csv')
    occs = sorted(r.occupancy.unique())
    assert len(r) == plan['runs'] and len(d) == plan['runs']*plan['size']
    assert not d.duplicated(['seed', 'occupancy', 'model', 'information', 'driver']).any()
    assert d.loc[~d.success, 'walk_m'].isna().all()
    assert r.groupby(['occupancy', 'model', 'information']).seed.nunique().eq(len(plan['seeds'])).all()
    out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.size': 15, 'font.weight': 'bold', 'axes.labelsize': 17,
                         'axes.labelweight': 'bold', 'axes.titlesize': 18,
                         'axes.titleweight': 'bold', 'figure.titlesize': 23,
                         'figure.titleweight': 'bold', 'xtick.labelsize': 14,
                         'ytick.labelsize': 14, 'legend.fontsize': 13,
                         'lines.linewidth': 2.5, 'axes.spines.top': False,
                         'axes.spines.right': False, 'pdf.fonttype': 42})
    records = []

    def save(fig, number, slug, title, caption, legend=True, extra_handles=()):
        stem = f'{number:02d}_{slug}'
        handles = [plt.Line2D([], [], color=COLORS[m], marker='o', label=LABELS[m]) for m in MODES]
        if legend:
            fig.legend(handles=handles+list(extra_handles), loc='outside lower center', ncol=5 if extra_handles else 3, frameon=False)
        fig.savefig(out/(stem+'.png'), dpi=200, bbox_inches='tight')
        fig.savefig(out/(stem+'.pdf'), bbox_inches='tight')
        plt.close(fig)
        records.append(dict(number=number, stem=stem, title=title, caption=caption))

    def grid():
        fig, axes = plt.subplots(len(occs), len(MODELS), figsize=(19, 14), layout='constrained', squeeze=False)
        for i, occ in enumerate(occs):
            for j, model in enumerate(MODELS):
                ax = axes[i, j]
                ax.set_title(f'{MODEL_LABELS[model]} | {100*occ:g}% occupied')
                ax.grid(alpha=.18)
        return fig, axes

    def subset(frame, occ, model, mode):
        return frame[(frame.occupancy == occ) & (frame.model == model) & (frame.information == mode)]

    # 1: Main outcomes, with seed-level intervals, not independent-driver intervals.
    fig, axes = plt.subplots(3, 3, figsize=(19, 14), layout='constrained')
    outcome_metrics = [('mean_search_s', 'Search, all arrivals (s)', 1),
                       ('mean_walk_parked_m', 'Walk, parked drivers (m)', 1),
                       ('success', 'Parking success (%)', 100)]
    for i, occ in enumerate(occs):
        for j, (metric, ylabel, scale) in enumerate(outcome_metrics):
            ax = axes[i, j]
            for k, mode in enumerate(MODES):
                for n, model in enumerate(MODELS):
                    mean, lo, hi = np.asarray(interval(subset(r, occ, model, mode)[metric]))*scale
                    ax.errorbar(n+(k-1)*.18, mean, yerr=[[max(0, mean-lo)], [max(0, hi-mean)]],
                                fmt='o', color=COLORS[mode], capsize=5, markersize=8)
            ax.set_xticks(range(3), ['M0', 'M1', 'CPT'])
            ax.set_ylabel(ylabel); ax.set_title(f'{100*occ:g}% initial occupancy'); ax.grid(alpha=.18)
            if metric == 'success': ax.set_ylim(0, 105)
    save(fig, 1, 'outcome_overview', 'Search, walking and parking success',
         'Equal-weight seed means and 95% seed-bootstrap intervals. Search included all arrivals; walking included only parked drivers. Each cell contained ten seeds of 80 drivers. Overlapping marginal intervals were not a test of paired effects.')

    # 2: Paired effects, maintaining the original paired-seed inference.
    fig, axes = plt.subplots(1, 3, figsize=(20, 10), layout='constrained')
    for ax, (metric, label, scale) in zip(axes, outcome_metrics):
        for i, occ in enumerate(occs):
            for j, model in enumerate(MODELS):
                y = i*3+j
                for k, mode in enumerate(('aisle', 'space')):
                    row = contrasts[(contrasts.occupancy == occ)&(contrasts.model == model)&
                                    (contrasts.metric == metric)&(contrasts.comparison == mode+'_vs_unaided')].iloc[0]
                    mean, lo, hi = np.array([row.delta, row.ci_low, row.ci_high])*scale
                    ax.errorbar(mean, y+(k-.5)*.22, xerr=[[max(0,mean-lo)], [max(0,hi-mean)]], fmt='o',
                                color=COLORS[mode], capsize=4, markersize=8)
        ax.axvline(0, color='black', lw=1); ax.grid(alpha=.18)
        ax.set_yticks(range(9), [f'{100*o:g}% / {MODEL_LABELS[m]}' for o in occs for m in MODELS])
        ax.invert_yaxis(); ax.set_xlabel('Change vs unaided\n'+label.replace('(%)', '(percentage points)'))
    save(fig, 2, 'paired_effects', 'Information effects relative to unaided search',
         'Intervention-minus-unaided differences with 95% paired-seed bootstrap intervals. Success differences were percentage points. Negative search/walk values indicated smaller outcomes. These exploratory contrasts were not multiplicity-adjusted.')

    # 3 and 5: Driver distributions, descriptive only (no pseudo-replicated intervals).
    for number, metric, slug, title, xlabel, parked in [
        (3, 'search_s', 'search_distribution', 'Distribution of elapsed search', 'Elapsed search (s)', False),
        (5, 'walk_m', 'walking_distribution', 'Distribution of walking distance', 'Walking distance (m)', True)]:
        fig, axes = grid()
        for i, occ in enumerate(occs):
            for j, model in enumerate(MODELS):
                ax = axes[i, j]
                for mode in MODES:
                    frame = subset(d, occ, model, mode)
                    if parked: frame = frame[frame.success]
                    x = np.sort(frame[metric].dropna())
                    if len(x): ax.step(x, np.arange(1, len(x)+1)/len(x), color=COLORS[mode], where='post')
                ax.set_xlabel(xlabel); ax.set_ylabel('Cumulative fraction'); ax.set_ylim(0, 1.03)
        save(fig, number, slug, title,
             ('Parked drivers only; failed drivers were excluded, not assigned zero walking. ' if parked else
              'All arrivals, including abandonment; this was an elapsed-outcome ECDF, not a survival estimate of eventual parking. ')+
             'Pooled driver distributions were descriptive; drivers within runs interacted and were not independent replicates.')

    # 4: Long-search tails per seed.
    quantiles = d.groupby(['seed', 'occupancy', 'model', 'information']).search_s.quantile([.5, .9, .95]).rename('seconds').reset_index()
    quantiles = quantiles.rename(columns={'level_4':'quantile'})
    quantiles.to_csv(out/'search_quantiles_by_seed.csv', index=False)
    fig, axes = grid()
    for i, occ in enumerate(occs):
        for j, model in enumerate(MODELS):
            ax = axes[i, j]
            for mode in MODES:
                frame = subset(quantiles, occ, model, mode)
                means = [interval(frame[frame['quantile'] == q].seconds) for q in [.5,.9,.95]]
                means = np.array(means)
                ax.errorbar(range(3), means[:,0], yerr=[np.maximum(0,means[:,0]-means[:,1]), np.maximum(0,means[:,2]-means[:,0])],
                            marker='o', color=COLORS[mode], capsize=4)
            ax.set_xticks(range(3), ['Median','90th','95th']); ax.set_ylabel('Elapsed search (s)')
    save(fig, 4, 'search_tails', 'Typical and long-search outcomes',
         'Mean of within-seed median, 90th and 95th percentiles, with seed-bootstrap intervals. All arrivals were included. These were not quantiles of successful parking time; abandonment could contribute to the tail.')

    # 6: Replication-level tradeoffs, all-arrival search versus conditional walk.
    fig, axes = grid()
    for i, occ in enumerate(occs):
        for j, model in enumerate(MODELS):
            ax = axes[i,j]
            for mode in MODES:
                frame = subset(r, occ, model, mode)
                ax.scatter(frame.mean_search_s, frame.mean_walk_parked_m, color=COLORS[mode], s=55, alpha=.75)
            ax.set_xlabel('Mean search, all arrivals (s)'); ax.set_ylabel('Mean walk, parked (m)')
    save(fig, 6, 'search_walk_tradeoff', 'Search and walking tradeoffs across replications',
         'Each point represented one seed/run. Walking conditioned on successful parking, while search included all arrivals. This descriptive plot did not establish Pareto optimality or a causal individual-level correlation.')

    # Reusable summaries retain one observational unit per seed.
    def bars(number, slug, title, frame, metric, ylabel, caption):
        fig, axes = grid()
        for i, occ in enumerate(occs):
            for j, model in enumerate(MODELS):
                ax = axes[i,j]
                for k, mode in enumerate(MODES):
                    mean, lo, hi = interval(subset(frame, occ, model, mode)[metric])
                    ax.bar(k, mean, color=COLORS[mode], width=.65)
                    ax.errorbar(k, mean, yerr=[[max(0,mean-lo)], [max(0,hi-mean)]], color='black', capsize=5)
                ax.set_xticks(range(3), ['Unaided','Aisle','Space']); ax.set_ylabel(ylabel)
        save(fig, number, slug, title, caption)

    rr = r.assign(failed_claims_per_driver=r.lost_claims/r.drivers)
    bars(7, 'failed_claims', 'Competition experienced at parking claims', rr, 'failed_claims_per_driver',
         'Failed claims per arrival', 'Mean failed claims per arriving driver with 95% seed-bootstrap intervals. Repeated failed attempts by the same driver were counted. A failed claim was distinct from rejecting an offer.')
    competition['overlap_fraction'] = competition.selections_already_pursued/competition.target_selections.replace(0,np.nan)
    bars(8, 'target_competition', 'Selecting spaces already pursued by another driver', competition,
         'overlap_fraction', 'Fraction of target selections',
         'Mean within-run fraction of target selections involving a stall another driver was already pursuing, with 95% seed-bootstrap intervals. Target events, rather than unique drivers, formed the denominator.')

    # 9: Identical aggregate success need not mean identical decisions.
    fig, axes = plt.subplots(1,3,figsize=(20,7),layout='constrained')
    for ax, occ in zip(axes,occs):
        for k, mode in enumerate(('aisle','space')):
            frame=choices[(choices.occupancy==occ)&(choices.comparison==mode+'_vs_unaided')].set_index('model').reindex(MODELS)
            ax.plot(range(3),frame.same_space_fraction,marker='o',color=COLORS[mode],label='Same stall')
            ax.plot(range(3),frame.same_aisle_fraction,marker='s',linestyle='--',color=COLORS[mode],label='Same aisle')
        ax.set_title(f'{100*occ:g}% initial occupancy');ax.set_xticks(range(3),['M0','M1','CPT'])
        ax.set_ylim(0,1.05);ax.set_ylabel('Agreement with unaided');ax.grid(alpha=.18)
    save(fig,9,'choice_agreement','How often did information change parking choices?',
         'Same-stall and same-aisle fractions among matched drivers who parked in both conditions. These were pooled descriptive fractions, not population equivalence tests. Drivers whose success changed were described separately in the success-switch plot.',
         extra_handles=(plt.Line2D([],[],color='black',marker='o',label='Same stall'),
                        plt.Line2D([],[],color='black',marker='s',linestyle='--',label='Same aisle')))

    # 10: Preserve matched driver identity when classifying success changes.
    transitions=[]
    fig, axes=plt.subplots(1,3,figsize=(20,8),layout='constrained')
    for ax,occ in zip(axes,occs):
        for k,mode in enumerate(('aisle','space')):
            frame=choices[(choices.occupancy==occ)&(choices.comparison==mode+'_vs_unaided')].set_index('model').reindex(MODELS)
            gain=frame.parked_only_intervention/frame.paired_drivers*100
            loss=frame.parked_only_control/frame.paired_drivers*100
            x=np.arange(3)+(k-.5)*.28
            ax.bar(x,gain,width=.25,color=COLORS[mode]);ax.bar(x,-loss,width=.25,color=COLORS[mode],hatch='///',alpha=.55)
            for model,g,l in zip(MODELS,gain,loss):transitions.append(dict(occupancy=occ,model=model,information=mode,gained_success_pct=g,lost_success_pct=l))
        ax.axhline(0,color='black',lw=1);ax.set_xticks(range(3),['M0','M1','CPT'])
        ax.set_title(f'{100*occ:g}% initial occupancy');ax.set_ylabel('Matched arrivals (%)');ax.grid(alpha=.18)
    limit=max(1,max(max(t['gained_success_pct'],t['lost_success_pct']) for t in transitions)*1.2)
    for ax,occ in zip(axes,occs):
        ax.set_ylim(-limit,limit)
        if not any(t['gained_success_pct'] or t['lost_success_pct'] for t in transitions if t['occupancy']==occ):
            ax.text(.5,.65,'No success switches',transform=ax.transAxes,ha='center',**STYLE)
    save(fig,10,'success_switches','Drivers who gained or lost parking success',
         'Positive bars: parked only with information. Negative hatched bars: parked only unaided. Both used all matched arrivals as denominator. These descriptive gross switches could offset in the aggregate success difference; no intervals were assigned to individual interacting drivers.')
    pd.DataFrame(transitions).to_csv(out/'success_switches.csv',index=False)

    # 11–13: Subgroup outcomes, avoid pooling driver-level confidence intervals.
    for number,group,slug,title in [(11,'mobility_limited','mobility_success','Parking success by walking constraint'),
                                    (12,'door','destination_walking','Walking distance by destination door'),
                                    (13,'intended_exit','exit_proximity','Distance to the intended vehicle exit')]:
        metric = 'success' if number==11 else ('walk_m' if number==12 else 'exit_distance_m')
        frame=d if number==11 else d[d.success]
        grouped=frame.groupby(['seed','occupancy','model','information',group])[metric].agg(['mean','size']).reset_index()
        grouped.to_csv(out/(slug+'_by_seed.csv'),index=False)
        if number==13:
            exit_table=grouped.pivot_table(index=['occupancy','model','intended_exit'],columns='information',values='mean',aggfunc='mean').reset_index()
            exit_table=exit_table.rename(columns={'unaided':'unaided_m','aisle':'aisle_m','space':'space_m'})
            exit_table['aisle_minus_unaided_m']=exit_table.aisle_m-exit_table.unaided_m
            exit_table['space_minus_unaided_m']=exit_table.space_m-exit_table.unaided_m
            exit_table.to_csv(out/'exit_distance_summary.csv',index=False)
            table_lines=['# Distance to the intended vehicle exit', '',
                         'Equal-weight means of within-seed distances among parked drivers, in metres. Exit A was north; Exit B was east at Vista Drive. Distances were straight-line proximity, not routed driving distance or departure time. These descriptive subgroup means were conditional on parking and were not evidence that information caused faster departures.', '',
                         '| Initial occupancy | Model | Intended exit | Unaided (m) | Aisle information (m) | Space information (m) |',
                         '|---|---|---|---|---|---|']
            for row in exit_table.itertuples():
                table_lines.append(f'| {100*row.occupancy:g}% | {MODEL_LABELS[row.model]} | {row.intended_exit.replace("exit_a","Exit A").replace("exit_b","Exit B")} | {row.unaided_m:.1f} | {row.aisle_m:.1f} | {row.space_m:.1f} |')
            table_lines += ['', 'Source: exit_proximity_by_seed.csv, generated from verified saved driver outcomes. Seed-level successful-driver counts were retained in that table. Groups with no parked drivers did not contribute a distance mean.', '', '[Exit-distance plot](13_exit_proximity.png)']
            (out/'exit_distance_table.md').write_text('\n'.join(table_lines)+'\n',encoding='utf-8')
        levels=sorted(d[group].dropna().unique())
        fig,axes=grid()
        for i,occ in enumerate(occs):
            for j,model in enumerate(MODELS):
                ax=axes[i,j]
                for k,mode in enumerate(MODES):
                    for n,level in enumerate(levels):
                        values=subset(grouped,occ,model,mode)
                        values=values[values[group]==level]['mean']
                        if not len(values):continue
                        mean,lo,hi=np.asarray(interval(values))*(100 if number==11 else 1)
                        ax.errorbar(n+(k-1)*.15,mean,yerr=[[max(0,mean-lo)],[max(0,hi-mean)]],fmt='o',color=COLORS[mode],capsize=4,markersize=8)
                labels = ['No walking limit','Walking limited'] if number==11 else [str(x).replace('door_','Door ').replace('exit_a','Exit A').replace('exit_b','Exit B') for x in levels]
                ax.set_xticks(range(len(levels)),labels)
                ax.set_ylabel('Parking success (%)' if number==11 else 'Distance (m)')
                if number==11:ax.set_ylim(0,105)
        save(fig,number,slug,title,
             'Exploratory subgroup seed means with 95% seed-bootstrap intervals; subgroup sizes were recorded in the companion CSV. '+
             ('Walking constraint was distinct from accessible-space eligibility.' if number==11 else
              'Only parked drivers contributed. Means excluded empty seed/subgroup cells; different successful cohorts could contribute across conditions. Straight-line distances were used, not routed walking or exit travel time.'))

    # 14: Complete CPT occupancy grid, shared counts/replication scale.
    config=ROOT/'data/lot_config.json'
    if sha(config)!=plan['source_sha256']['data/lot_config.json']:
        raise ValueError('Lot geometry differs from the frozen study.')
    facility=load_facility_from_lot_config(config)
    counts=d[(d.model=='cpt')&d.success].groupby(['occupancy','information','chosen_space']).size()/len(plan['seeds'])
    fig,axes=plt.subplots(3,3,figsize=(19,16),layout='constrained',sharex=True,sharey=True)
    for i,occ in enumerate(occs):
        for j,mode in enumerate(MODES):
            ax=axes[i,j]
            spaces=facility.spaces
            ax.scatter([s.x_m for s in spaces],[s.y_m for s in spaces],s=5,color='#d6d6d6')
            selected=[s for s in spaces if counts.get((occ,mode,s.space_id),0)>0]
            dots=ax.scatter([s.x_m for s in selected],[s.y_m for s in selected],s=20,
                            c=[counts.get((occ,mode,s.space_id),0) for s in selected],cmap='viridis',vmin=0,vmax=counts.max())
            for labels,points,marker,color in [(('D1','D2'),facility.walmart_doors,'*','black'),(('A','B'),facility.entry_points,'^','#b02a37')]:
                for label,point in zip(labels,points):
                    ax.scatter(*point,marker=marker,s=110,color=color)
                    ax.annotate(label,point,xytext=(6,6),textcoords='offset points',fontsize=14,fontweight='bold')
            ax.set_title(f'{LABELS[mode]} | {100*occ:g}%');ax.set_aspect('equal')
            if i==2:ax.set_xlabel('Local east (m)')
            if j==0:ax.set_ylabel('Local north (m)')
    fig.get_layout_engine().set(hspace=.09,wspace=.04)
    fig.colorbar(dots,ax=axes,label='Parkings per stall per replication',shrink=.7)
    save(fig,14,'spatial_choices','Where CPT drivers parked across all tested occupancies',
         'Mean selections per stall per replication, with one shared color scale across nine panels. D1/D2 marked doors and A/B marked vehicle access points. Estimated geometry; unselected records were grey. Stall reuse could occur. This spatial example covered CPT; it did not imply the same pattern for all models.',legend=False)

    # 15: Information mechanism diagnostics, not a rerun or a causal mediation test.
    diagnostics=d.groupby(['seed','occupancy','model','information'])[['reports','information_route_changes','remote_targets']].mean().reset_index()
    diagnostics.to_csv(out/'information_use_by_seed.csv',index=False)
    fig,axes=plt.subplots(1,3,figsize=(21,8),layout='constrained')
    for ax,metric,label in zip(axes,['reports','information_route_changes','remote_targets'],['Reports per arrival','Route changes per arrival','Remote targets per arrival']):
        for k,mode in enumerate(MODES):
            means=[]
            for occ in occs:
                means.append(diagnostics[(diagnostics.occupancy==occ)&(diagnostics.information==mode)][metric].mean())
            ax.plot([100*o for o in occs],means,marker='o',color=COLORS[mode])
        ax.set_xticks([100*o for o in occs]);ax.set_xlabel('Initial occupancy (%)');ax.set_ylabel(label);ax.grid(alpha=.18)
    save(fig,15,'information_use','How drivers used each information service',
         'Equal-weight means across model/seed cells, pooling all three decision models for a compact mechanism diagnostic. Reports, exploration-route changes and remote-target selections counted events, including repeated events by one driver. This descriptive view was not a mediation or significance analysis; per-model seed data were retained.')

    records.sort(key=lambda x:x['number'])
    lines=['# Expanded information-study figures', '',
           'Fifteen exploratory figures were generated from the existing 270 matched runs and 21,600 driver outcomes. No simulations were rerun. All seven input files were verified against the original archive manifest.', '',
           'Figures used bold labels and larger fonts. PNG previews and vector PDF versions were provided. Choose a smaller set for the main paper and place supporting analyses in supplementary material; figure count did not establish publication readiness.', '',
           'Interacting drivers were not independent experimental replications. Intervals resampled seeds, not drivers. Ten seeds per cell remained a pilot; the additional figures did not increase replication or validate behavioral assumptions.', '',
           '[Exit A/B distance table](exit_distance_table.md) | [Exit summary CSV](exit_distance_summary.csv)', '',
           '## Reproduce', '', '```powershell',
           'python scripts/plot_information_results.py --source results/parking_information_20261028 --output research/paper_assets/information_figures_20261028', '```', '']
    for item in records:
        lines += ['---', '',
                  f'![{item["title"]}]({item["stem"]}.png)', '', item['caption'], '',
                  f'[Vector PDF]({item["stem"]}.pdf)', '']
    (out/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    # Contact sheet is for review, not a manuscript figure.
    from PIL import Image, ImageOps, ImageDraw
    sheet=Image.new('RGB',(1800,5*420),'white')
    draw=ImageDraw.Draw(sheet)
    for n,item in enumerate(records):
        im=Image.open(out/(item['stem']+'.png')).convert('RGB')
        thumb=ImageOps.contain(im,(590,385))
        x=(n%3)*600;y=(n//3)*420
        sheet.paste(thumb,(x+(600-thumb.width)//2,y+25))
        draw.text((x+12,y+6),f'{item["number"]:02d} {item["stem"][3:]}',fill='black')
    sheet.save(out/'contact_sheet.jpg',quality=90)
    artifacts={p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='provenance.json'}
    provenance=dict(source=str(source),input_sha256={n:sha(source/n) for n in inputs},
                    source_manifest_sha256=sha(source/'bundle_manifest.json'),
                    script_sha256=sha(Path(__file__)),python=sys.version,
                    versions=dict(numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__),
                    figures=records,artifacts=artifacts,
                    note='Post hoc descriptive reanalysis; original evidence archive unchanged. No new simulation runs.')
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(f'Created {len(records)} figures, PNG/PDF pairs, captions, tables and provenance in {out}')


if __name__=='__main__':
    main()
