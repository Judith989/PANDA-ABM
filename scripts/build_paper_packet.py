"""Build paper derivatives from completed TCSS tables; never rerun simulations."""
from pathlib import Path
import hashlib,json,shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'paper'; FIG=OUT/'figures'; TAB=OUT/'tables'
for p in (FIG,TAB,TAB/'complete'):p.mkdir(parents=True,exist_ok=True)
sources={}
for stage in ('first_batch','robustness'):
    for p in (ROOT/f'research/tcss/{stage}_tables').glob('*.csv'):
        sources[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
        shutil.copyfile(p,TAB/'complete'/f'{stage}_{p.name}')
def read(name,stage='robustness'):
    return pd.read_csv(ROOT/f'research/tcss/{stage}_tables/{name}.csv')
plt.rcParams.update({'font.size':14,'font.weight':'bold','axes.labelsize':15,
 'axes.labelweight':'bold','xtick.labelsize':13,'ytick.labelsize':13,
 'legend.fontsize':12,'axes.linewidth':1.2,'lines.linewidth':2.3,
 'lines.markersize':6,'pdf.fonttype':42,'ps.fonttype':42})
names={'deterministic':'M0','rum':'M1','cpt':'CPT','simple':'Simple search','linear_cpt':'Linear CPT'}
colours={'deterministic':'#595959','rum':'#009e73','cpt':'#0072b2','simple':'#d55e00','linear_cpt':'#cc79a7'}
catalog=[]
def export(fig,name,caption,role):
    for ax in fig.axes:
        assert not ax.get_title()
        ax.grid(alpha=.18);ax.spines[['top','right']].set_visible(False)
    assert fig._suptitle is None
    for ext in ('pdf','png'):fig.savefig(FIG/f'{name}.{ext}',dpi=350,bbox_inches='tight')
    plt.close(fig);catalog.append((name,role,caption))
def legend(fig,ax):
    h,l=ax.get_legend_handles_labels()
    fig.legend(h,l,loc='outside lower center',ncol=min(len(l),4),frameon=False)
def table(frame,name):
    frame.to_csv(TAB/f'{name}.csv',index=False)
    fmt=frame.map(lambda v:f'{v:.2f}' if isinstance(v,float) else str(v))
    text='| '+' | '.join(fmt.columns)+' |\n| '+' | '.join(['---']*len(fmt.columns))+' |\n'
    text+='\n'.join('| '+' | '.join(r)+' |' for r in fmt.itertuples(index=False,name=None))+'\n'
    (TAB/f'{name}.md').write_text(text,encoding='utf-8')
cells=read('benchmark_cells')
for metric,label,name in [('mean_search_s','Search time, all arrivals (s)','search_by_information'),
 ('success','Parking success (%)','success_by_information'),
 ('mean_walk_parked_m','Walking among parked (m)','walking_by_information'),
 ('mean_exit_parked_m','Exit distance among parked (m)','exit_proximity'),
 ('claims_per_arrival','Failed claims per arrival','competition')]:
    fig,axes=plt.subplots(1,3,figsize=(10,4.3),layout='constrained',sharey=True)
    for ax,occ in zip(axes,(.4,.8,.95)):
        for model in ('deterministic','rum','cpt','simple'):
            g=cells[(cells.occupancy==occ)&(cells.model==model)].set_index('information').loc[['unaided','aisle','space']]
            ax.plot(range(3),g[metric]*(100 if metric=='success' else 1),'o-',color=colours[model],label=names[model])
        ax.set_xticks(range(3),['Unaided','Aisle','Space'],rotation=25)
        ax.set_xlabel(f'{occ:.0%} initial occupancy')
    axes[0].set_ylabel(label);legend(fig,axes[-1])
    export(fig,name,'Cell means across 30 matched seeds per condition. M0, M1, CPT and the simple-search benchmark used the same populations and initial occupied spaces. Walking and exit distance conditioned on parking in each arm; successful cohorts could differ. Exit distance measured proximity, not departure time. Lines connected means and did not show uncertainty; paired intervals were retained in the complete tables.','Main' if metric!='mean_exit_parked_m' else 'Supplement')
effects=read('context_information_effects')
for metric,label,name in [('mean_search_s','Search change vs unaided (s)','information_search_effect'),('mean_walk_parked_m','Walking change among parked (m)','information_walking_effect')]:
    fig,axes=plt.subplots(1,3,figsize=(10,4.4),layout='constrained',sharey=True)
    for ax,occ in zip(axes,(.4,.8,.95)):
        for j,model in enumerate(('deterministic','rum','cpt')):
            g=effects[(effects.condition=='base')&(effects.occupancy==occ)&(effects.model==model)&(effects.metric==metric)].set_index('information').loc[['aisle','space']]
            ax.errorbar(np.arange(2)+(j-1)*.12,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o',capsize=3,color=colours[model],label=names[model])
        ax.axhline(0,color='black',lw=1);ax.set_xticks([0,1],['Aisle','Space']);ax.set_xlabel(f'{occ:.0%} initial occupancy')
    axes[0].set_ylabel(label);legend(fig,axes[-1]);export(fig,name,'Information minus unaided effects, with exploratory pointwise 95% paired-seed percentile bootstrap intervals (10,000 resamples; 30 seeds). Walking conditioned on parking separately in each arm.','Main')
adopt=read('mixed_adoption_system_effects')
for metric,label,name in [('mean_search_s','Search change vs all unaided (s)','adoption_search'),('claims_per_arrival','Additional failed claims per arrival','adoption_competition')]:
    fig,axes=plt.subplots(1,2,figsize=(9,4.5),layout='constrained',sharey=True)
    for ax,info in zip(axes,('aisle','space')):
        for model in ('deterministic','rum','cpt'):
            g=adopt[(adopt.occupancy==.95)&(adopt.information==info)&(adopt.model==model)&(adopt.metric==metric)].sort_values('adoption')
            ax.errorbar(g.adoption*100,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o-',capsize=3,label=names[model],color=colours[model])
        ax.axhline(0,color='black',lw=1);ax.set_xticks([25,50,75]);ax.set_xlabel(f'{info.title()} access probability (%)')
    axes[0].set_ylabel(label);legend(fig,axes[-1]);export(fig,name,'Mixed adoption at 95% initial occupancy. Each rate was compared with the all-unaided world using ten matched seeds. Rates were independent access probabilities, not fixed quotas. Error bars were exploratory pointwise 95% paired-seed intervals.','Main')
gdata=read('mixed_adoption_group_effects')
fig,axes=plt.subplots(1,2,figsize=(9,4.5),layout='constrained',sharey=True)
for ax,info in zip(axes,('aisle','space')):
    for cohort,label in [('fixed_informed','Always informed'),('fixed_unaided','Always unaided')]:
        g=gdata[(gdata.occupancy==.95)&(gdata.model=='cpt')&(gdata.information==info)&(gdata.cohort==cohort)&(gdata.metric=='search_s')].sort_values('adoption')
        ax.errorbar(g.adoption*100,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o-',capsize=3,label=label)
    ax.axhline(0,color='black',lw=1);ax.set_xticks([25,50,75]);ax.set_xlabel(f'{info.title()} access probability (%)')
axes[0].set_ylabel('CPT search change vs own baseline (s)');legend(fig,axes[-1])
export(fig,'fixed_cohort_spillovers','CPT at 95% initial occupancy. Membership was fixed across adoption rates: 196 always-informed and 202 always-unaided trips over ten seeds. Each group was compared with the same drivers under all-unaided access. Intervals resampled seeds and included interactions with other drivers; they did not directly test differences between groups.','Main')
fig,ax=plt.subplots(figsize=(8,4.5),layout='constrained')
for j,info in enumerate(('aisle','space')):
    g=effects[(effects.occupancy==.95)&(effects.model=='cpt')&(effects.information==info)&(effects.metric=='mean_search_s')].set_index('condition').loc[['base','E3a','E3b','E4']]
    ax.errorbar(np.arange(4)+(j-.5)*.15,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o',capsize=4,label=info.title())
ax.axhline(0,color='black',lw=1);ax.set_xticks(range(4),['Static','Background\ndepartures','30 s report\ndelay','Synthetic\nlayout']);ax.set_ylabel('CPT search change vs unaided (s)');legend(fig,ax)
export(fig,'operational_robustness','CPT information effects at 95% initial occupancy. Static and layout conditions used 30 seeds; departure and delay screens used ten. Departures reduced background occupancy without replacement. Transfer changed geometry, compatible supply and distance expectations together. Intervals were pointwise paired-seed intervals within each context.','Main')
tr=read('cpt_transform_resolution_80')
fig,axes=plt.subplots(1,2,figsize=(9,4.5),layout='constrained')
for ax,metric,label in zip(axes,('mean_search_s','mean_walk_parked_m'),('Search difference (s)','Walking difference (m)')):
    for info in ('unaided','aisle','space'):
        g=tr[(tr.information==info)&(tr.metric==metric)].sort_values('integration')
        ax.errorbar(g.integration,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o-',capsize=3,label=info.title())
    ax.axhline(0,color='black',lw=1);ax.set_xticks([.25,.5,1]);ax.set_xlabel('Integration interval (s)');ax.set_ylabel('CPT minus linear\n'+label)
legend(fig,axes[-1]);export(fig,'cpt_resolution','CPT minus its same-adapter linear control at 80% initial occupancy, using the same ten seeds at every integration interval. Intervals were exploratory pointwise 95% paired-seed intervals. This tested numerical sensitivity, not empirical equivalence.','Main')
core=cells[cells.model=='cpt'].copy();core['occupancy']=core.occupancy*100;core['success']=core.success*100
table(core.rename(columns={'occupancy':'Initial occupancy (%)','information':'Information','mean_search_s':'Search (s)','success':'Success (%)','mean_walk_parked_m':'Walking (m)','mean_exit_parked_m':'Exit proximity (m)','claims_per_arrival':'Failed claims / arrival'}).drop(columns='model'),'core_cpt_outcomes')
for name,frame in [('context_effects',effects[(effects.occupancy==.95)&(effects.model=='cpt')&(effects.metric=='mean_search_s')]),('adoption_effects',adopt[(adopt.occupancy==.95)&(adopt.model=='cpt')]),('cpt_timing_control',tr)]:table(frame,name)
(OUT/'figure_catalogue.md').write_text('# Figure placement and captions\n\nFigures contained no titles or figure numbers. Labels below were file identifiers; assign manuscript numbering during typesetting. PDF files retained vector text. Use two-column width for multi-panel figures.\n\n'+'\n\n'.join(f'## {name} — {role}\n\n![{name}](figures/{name}.png)\n\n{cap}\n\n[Vector PDF](figures/{name}.pdf)' for name,role,cap in catalog)+'\n',encoding='utf-8')
(OUT/'provenance.json').write_text(json.dumps({'source_tables_sha256':sources,'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'new_simulations':0,'figure_count':len(catalog),'font':'bold; 13-point ticks, 14-point body, 15-point axis labels at native 8–10 inch width; embed vector PDFs','outputs_sha256':{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in (FIG,TAB) for p in folder.rglob('*') if p.is_file()}},indent=2),encoding='utf-8')
print(f'Built {len(catalog)} title-free PNG/PDF figure pairs and paper tables in {OUT}')
