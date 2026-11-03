"""Compose manuscript figures/tables from saved TCSS analyses; no simulations."""
from pathlib import Path
import hashlib,json,shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'paper/results_section'
FIG=OUT/'figures';FIG.mkdir(exist_ok=True)
DATA=ROOT/'paper/tables/complete'
sources={}
def read(name):
    p=DATA/(name+'.csv');sources[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return pd.read_csv(p)
ctx=read('robustness_context_information_effects')
linear_effects=read('first_batch_information_effects')
tr=read('first_batch_prospect_transform_effects')
agree=read('first_batch_linear_cpt_choice_agreement')
adopt=read('robustness_mixed_adoption_system_effects')
cohort=read('robustness_mixed_adoption_group_effects')
num=read('robustness_cpt_transform_resolution_80')
hetero=read('first_batch_heterogeneity_controls')
simple=read('robustness_simple_minus_behavioral')
inter=read('first_batch_model_information_interactions')
change=read('robustness_change_in_information_effects')

plt.rcParams.update({'font.size':13,'font.weight':'bold','axes.labelsize':14,
 'axes.labelweight':'bold','xtick.labelsize':12,'ytick.labelsize':12,
 'legend.fontsize':11,'pdf.fonttype':42,'lines.linewidth':2,'axes.spines.top':False,
 'axes.spines.right':False,'savefig.dpi':300})
BLUE='#0072b2';ORANGE='#c46b00';PURPLE='#7651a8'
def select(df,**kw):
    g=df
    for k,v in kw.items():g=g[np.isclose(g[k],v) if isinstance(v,float) else g[k].eq(v)]
    return g
def one(df,**kw):
    g=select(df,**kw);assert len(g)==1,(kw,len(g));return g.iloc[0]
def save(fig,name):
    assert fig._suptitle is None
    for ax in fig.axes:assert not ax.get_title()
    for ext in ['pdf','png']:fig.savefig(FIG/(name+'.'+ext),bbox_inches='tight')
    plt.close(fig)
def error(ax,x,row,color,offset=0):
    y=float(row.delta)
    ax.errorbar(x+offset,y,yerr=[[y-row.ci_low],[row.ci_high-y]],fmt='o',
        color=color,capsize=4,markersize=6)

# Choice agreement is the equal-weight mean of the original per-seed fractions.
fig,axs=plt.subplots(1,2,figsize=(9.4,3.35),layout='constrained')
for j,(field,label,c) in enumerate([('same_stall','Same space',BLUE),('same_aisle','Same aisle',ORANGE)]):
    vals=[100*select(agree,occupancy=o,information='space')[field].mean() for o in [.8,.95]]
    axs[0].bar(np.arange(2)+(j-.5)*.32,vals,width=.3,label=label,color=c)
axs[0].set(xticks=[0,1],xticklabels=['80%','95%'],ylim=(0,100),
    xlabel='(a) Initial occupancy',ylabel='CPT / linear agreement (%)')
axs[0].legend(frameon=False,loc='upper right')
for occ,c,mark in [(.8,BLUE,'o'),(.95,ORANGE,'s')]:
    a=one(tr,occupancy=occ,information='space',metric='mean_search_s')
    b=one(tr,occupancy=occ,information='space',metric='mean_walk_parked_m')
    x=a.cpt_minus_linear;y=b.cpt_minus_linear
    axs[1].errorbar(x,y,xerr=[[x-a.ci_low],[a.ci_high-x]],
        yerr=[[y-b.ci_low],[b.ci_high-y]],fmt=mark,color=c,capsize=4,label=f'{occ:.0%}')
axs[1].axhline(0,color='0.65',lw=.8);axs[1].axvline(0,color='0.65',lw=.8)
axs[1].set(xlabel='(b) Search change (s)',ylabel='Walking change (m)')
axs[1].legend(frameon=False,title='Initial occupancy')
save(fig,'mechanisms')

# A categorical heatmap avoids implying interpolation between decision models.
fig,axs=plt.subplots(1,3,figsize=(10.7,5.9),layout='constrained')
models=['deterministic','rum','cpt','linear_cpt','simple'];names=['M0','M1','CPT','Linear CPT','Simple']
for ax,metric,unit,panel in zip(axs,['mean_search_s','mean_walk_parked_m','mean_exit_parked_m'],['Search change (s)','Walking change (m)','Exit-distance change (m)'],['(a)','(b)','(c)']):
    a=np.array([[np.nan if m=='linear_cpt' and occ==.4 else (one(linear_effects,variant='base',occupancy=occ,model=m,information=i,metric=metric).delta if m=='linear_cpt' else one(ctx,condition='base',occupancy=occ,model=m,information=i,metric=metric).delta) for i in ['aisle','space']] for occ in [.4,.8,.95] for m in models])
    bound=max(1.,np.nanmax(abs(a)));cmap=plt.colormaps['RdBu_r'].copy();cmap.set_bad('#e2e8f0');im=ax.imshow(a,cmap=cmap,vmin=-bound,vmax=bound,aspect='auto')
    for row in range(15):
        for col in range(2):ax.text(col,row,'N/A' if np.isnan(a[row,col]) else f'{a[row,col]:+.1f}',ha='center',va='center',fontsize=11,fontweight='bold',color='white' if abs(a[row,col])>.62*bound else 'black')
    ax.set_xticks([0,1],['Aisle','Space']);ax.set_yticks(range(15),[f'{occ:.0%} {n}' for occ in [.4,.8,.95] for n in names])
    ax.set_xlabel(panel+' Information')
    for y in [4.5,9.5]:ax.axhline(y,color='white',lw=2.5)
    fig.colorbar(im,ax=ax,orientation='horizontal',pad=.04,shrink=.95,label=unit)
save(fig,'information')

fig,axs=plt.subplots(1,3,figsize=(10.7,3.5),layout='constrained')
for ax,metric,ylabel,panel in zip(axs[:2],['mean_search_s','claims_per_arrival'],['Search change (s)','Failed-claim change / arrival'],['(a)','(b)']):
    for info,c in [('aisle',ORANGE),('space',BLUE)]:
        g=select(adopt,occupancy=.95,model='cpt',information=info,metric=metric).sort_values('adoption')
        assert len(g)==3
        ax.errorbar(g.adoption*100,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o-',color=c,capsize=4,label=info.title())
    ax.axhline(0,color='0.6',lw=.8);ax.set(xlabel=panel+' Adoption (%)',ylabel=ylabel,xticks=[25,50,75]);ax.legend(frameon=False)
for group,c,label in [('fixed_informed',BLUE,'Informed'),('fixed_unaided',PURPLE,'Unaided')]:
    g=select(cohort,occupancy=.95,model='cpt',information='space',metric='search_s',cohort=group).sort_values('adoption')
    axs[2].errorbar(g.adoption*100,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o-',color=c,capsize=4,label=label)
axs[2].axhline(0,color='0.6',lw=.8);axs[2].set(xlabel='(c) Adoption (%)',ylabel='Fixed-cohort search change (s)',xticks=[25,50,75]);axs[2].legend(frameon=False)
save(fig,'adoption')

fig,axs=plt.subplots(1,3,figsize=(10.7,3.6),layout='constrained')
conditions=['base','E3a','E3b','E4'];labels=['Static (30)','Departures (10)','Delay (10)','Synthetic (30)']
for ax,metric,xlab in zip(axs[:2],['mean_search_s','mean_walk_parked_m'],['(a) Search change (s)','(b) Walking change (m)']):
    for j,condition in enumerate(conditions):
        r=one(ctx,condition=condition,occupancy=.95,model='cpt',information='space',metric=metric)
        ax.errorbar(r.delta,j,xerr=[[r.delta-r.ci_low],[r.ci_high-r.delta]],fmt='o',color=BLUE,capsize=4)
    ax.axvline(0,color='0.6',lw=.8);ax.set(yticks=range(4),yticklabels=labels,xlabel=xlab);ax.invert_yaxis()
g=select(num,information='space',metric='mean_search_s').sort_values('integration')
axs[2].errorbar(g.integration,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o-',color=PURPLE,capsize=4)
axs[2].axhline(0,color='0.6',lw=.8);axs[2].set(xlabel='(c) Physical step (s)',ylabel='CPT minus linear search (s)',xticks=[.25,.5,1.])
save(fig,'robustness')

# Exact compact tables are produced from the same saved analysis rows as plots.
def fmt(v):return f'{v:+.2f}' if abs(v)>=.005 else '0.00'
def interval(r,field='delta',scale=1):return f'{fmt(r[field]*scale)} [{fmt(r.ci_low*scale)}, {fmt(r.ci_high*scale)}]'
tables=OUT/'tables';tables.mkdir(exist_ok=True)
lines=[]
for occ in [.4,.8,.95]:
    for info in ['aisle','space']:
        cells=[f'{occ:.0%}'.replace('%',r'\%'),info.title()]
        for metric in ['mean_search_s','mean_walk_parked_m','mean_exit_parked_m','success']:
            cells.append(interval(one(ctx,condition='base',occupancy=occ,model='cpt',information=info,metric=metric),scale=100 if metric=='success' else 1))
        lines.append(' & '.join(cells)+r' \\')
(tables/'information_rows.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
lines=[]
for occ in [.4,.8]:
    a=one(simple,occupancy=occ,information='space',comparator='cpt',metric='mean_search_s')
    b=one(simple,occupancy=occ,information='space',comparator='cpt',metric='mean_walk_parked_m')
    lines.append(f'Simple--CPT & {occ:.0%}'.replace('%',r'\%')+' & '+interval(a)+' & '+interval(b)+r' \\')
for occ in [.8,.95]:
    a=one(tr,occupancy=occ,information='space',metric='mean_search_s')
    b=one(tr,occupancy=occ,information='space',metric='mean_walk_parked_m')
    lines.append(f'CPT--linear & {occ:.0%}'.replace('%',r'\%')+' & '+interval(a,'cpt_minus_linear')+' & '+interval(b,'cpt_minus_linear')+r' \\')
(tables/'mechanism_rows.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')

# Keep additional existing scientific figures available without crowding the main section.
extras=OUT/'additional_figures';extras.mkdir(exist_ok=True)
keys=['search_distributions','walking_distributions','search_walk_scatter','individual_success_switches','choice_agreement_bars','door_walking','exit_groups','walking_constraint_success','spatial_parking_maps','search_by_information','success_by_information','walking_by_information','competition','cpt_resolution']
for key in keys:
    p=ROOT/'paper/figures'/f'{key}.pdf';shutil.copy2(p,extras/p.name)
    sources[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'method':'New presentation of saved analyses; no new simulations or new bootstrap estimates.',
 'source_sha256':sources,'main_figures':4,'additional_figures':len(keys),
 'agreement':'Equal-weight mean of per-seed CPT/linear fractions; not agreement with unaided.',
 'uncertainty':'Saved pointwise paired-seed intervals; two-axis error bars are marginal, not joint confidence regions.',
 'output_sha256':{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*FIG.glob('*'),*tables.glob('*')]}}
(OUT/'asset_provenance.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Built mechanism, information, adoption and robustness composites; completing five-policy overview next.')

# Complete-policy overview and compact descriptive table use the same saved analyses.
import runpy
runpy.run_path(str(ROOT/'scripts/build_five_policy_overview.py'),run_name='__main__')
runpy.run_path(str(ROOT/'scripts/build_single_column_results.py'),run_name='__main__')
