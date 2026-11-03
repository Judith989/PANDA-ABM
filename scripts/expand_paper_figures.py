"""Restore distributional, spatial and individual views using corrected core runs."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'paper';F=OUT/'figures';T=OUT/'tables';S=ROOT/'results/tcss_first_batch_20261028'
design=json.loads((S/'design.json').read_text())
for name in ('runs.csv','drivers.csv'):
    assert hashlib.sha256((S/name).read_bytes()).hexdigest()==design['output_sha256'][name]
d=pd.read_csv(S/'drivers.csv');d=d[(d.variant=='base')&d.model.isin(['deterministic','rum','cpt'])].copy()
r=pd.read_csv(S/'runs.csv');r=r[(r.variant=='base')&r.model.isin(['deterministic','rum','cpt'])].copy()
assert len(r)==810 and len(d)==64800
plt.rcParams.update({'font.size':14,'font.weight':'bold','axes.labelsize':15,'axes.labelweight':'bold',
 'xtick.labelsize':13,'ytick.labelsize':13,'legend.fontsize':12,'pdf.fonttype':42,'lines.linewidth':2.2})
modes=['unaided','aisle','space'];colors=['#595959','#d55e00','#0072b2'];records=[]
def save(fig,name,caption):
    for ax in fig.axes:assert not ax.get_title()
    assert fig._suptitle is None
    for ext in ('png','pdf'):fig.savefig(F/f'{name}.{ext}',dpi=350,bbox_inches='tight')
    plt.close(fig);records.append((name,caption))
def key(fig):
    fig.legend(handles=[plt.Line2D([],[],color=c,marker='o',label=m.title()) for m,c in zip(modes,colors)],loc='outside lower center',ncol=3,frameon=False)
def panels():return plt.subplots(1,3,figsize=(11,4.6),layout='constrained')
def boot(x):
    x=np.asarray(x,float);x=x[np.isfinite(x)]
    if not len(x):return (np.nan,np.nan,np.nan)
    a=np.random.default_rng(20261029).choice(x,(10000,len(x)),replace=True).mean(axis=1)
    return x.mean(),*np.quantile(a,[.025,.975])
for metric,label,name,parked in [('search_s','Elapsed search (s)','search_distributions',False),('walk_m','Walking distance (m)','walking_distributions',True)]:
    fig,axes=panels()
    for ax,occ in zip(axes,[.4,.8,.95]):
        for j,(mode,c) in enumerate(zip(modes,colors)):
            a=d[(d.model=='cpt')&(d.occupancy==occ)&(d.information==mode)]
            if parked:a=a[a.success]
            vals=a[metric].dropna()
            parts=ax.violinplot(vals,positions=[j],showmedians=True,showextrema=False)
            for body in parts['bodies']:body.set_facecolor(c);body.set_alpha(.65)
            parts['cmedians'].set_color('black')
            q=np.quantile(vals,[.25,.75]);ax.vlines(j,*q,color='black',lw=5)
        ax.set_xticks(range(3),['Unaided','Aisle','Space'],rotation=25);ax.set_xlabel(f'{occ:.0%} occupancy');ax.grid(axis='y',alpha=.18)
    axes[0].set_ylabel(label)
    save(fig,name,'CPT pooled outcome distributions across 30 matched seeds per cell. Violin widths showed smoothed density; black marks showed median and interquartile range. '+('Walking excluded unparked drivers.' if parked else 'Search included all arrivals and abandonment at the deadline; boundary smoothing was descriptive, not a survival model.')+' Interacting driver records were not independent replications; no driver-level inferential intervals were assigned.')
fig,axes=panels()
for ax,occ in zip(axes,[.4,.8,.95]):
    for mode,c in zip(modes,colors):
        g=r[(r.model=='cpt')&(r.occupancy==occ)&(r.information==mode)]
        ax.scatter(g.mean_search_s,g.mean_walk_parked_m,color=c,s=45,alpha=.7)
    ax.set_xlabel(f'{occ:.0%} / mean search (s)');ax.grid(alpha=.18)
axes[0].set_ylabel('Mean walking among parked (m)');key(fig)
save(fig,'search_walk_scatter','Each point represented one CPT run (30 seeds per information/occupancy cell). Search included all arrivals; walking conditioned on parking. This described run-level tradeoffs, not individual causal correlations or a Pareto frontier.')
# A heatmap provides an overview without connecting categorical models by lines.
effects=pd.read_csv(ROOT/'research/tcss/robustness_tables/context_information_effects.csv')
fig,axes=plt.subplots(1,2,figsize=(9,6),layout='constrained',sharey=True)
for ax,info in zip(axes,['aisle','space']):
    arr=np.array([[effects[(effects.condition=='base')&(effects.occupancy==occ)&(effects.model==model)&(effects.information==info)&(effects.metric=='mean_search_s')].iloc[0].delta for model in ['deterministic','rum','cpt']] for occ in [.4,.8,.95]])
    im=ax.imshow(arr,cmap='RdBu_r',vmin=-20,vmax=20,aspect='auto')
    for i in range(3):
        for j in range(3):ax.text(j,i,f'{arr[i,j]:+.1f}',ha='center',va='center',fontweight='bold',color='white' if abs(arr[i,j])>12 else 'black')
    ax.set_xticks(range(3),['M0','M1','CPT']);ax.set_yticks(range(3),['40%','80%','95%']);ax.set_xlabel(info.title()+' information')
axes[0].set_ylabel('Initial occupancy');fig.colorbar(im,ax=axes,label='Search change vs unaided (s)',shrink=.8)
save(fig,'information_effect_heatmap','Paired mean search effects from the corrected 30-seed core. Blue indicated lower search and red higher search relative to unaided. Printed values were seconds. Complete paired intervals remained in the context-information table; cell color was not a significance classification.')
keys=['seed','occupancy','model','driver'];base=d[d.information=='unaided']
changes=[]
for mode in ['aisle','space']:
    p=d[d.information==mode].merge(base,on=keys,suffixes=('_info','_base'),validate='one_to_one')
    for (occ,model),g in p.groupby(['occupancy','model']):
        both=g.success_info & g.success_base
        changes.append(dict(occupancy=occ,model=model,information=mode,
         gained=100*(g.success_info & ~g.success_base).mean(),lost=100*(~g.success_info & g.success_base).mean(),
         same_stall=100*(g.loc[both,'chosen_space_info']==g.loc[both,'chosen_space_base']).mean(),
         same_aisle=100*(g.loc[both,'chosen_aisle_info']==g.loc[both,'chosen_aisle_base']).mean(),jointly_parked=int(both.sum())))
ch=pd.DataFrame(changes);ch.to_csv(T/'current_individual_changes.csv',index=False)
fig,axes=plt.subplots(1,2,figsize=(9,4.8),layout='constrained',sharey=True)
for ax,mode,c in zip(axes,['aisle','space'],colors[1:]):
    g=ch[(ch.occupancy==.95)&(ch.information==mode)].set_index('model').loc[['deterministic','rum','cpt']]
    ax.bar(range(3),g.gained,color=c,label='Parked only with information')
    ax.bar(range(3),-g.lost,color=c,alpha=.45,hatch='///',label='Parked only unaided')
    ax.axhline(0,color='black',lw=1);ax.set_xticks(range(3),['M0','M1','CPT']);ax.set_xlabel(mode.title()+' information')
axes[0].set_ylabel('Matched arrivals (%)');h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='outside lower center',ncol=1,frameon=False)
save(fig,'individual_success_switches','Gross success gains and losses at 95% occupancy among all matched arrivals over 30 seeds. Positive bars parked only with information; negative hatched bars parked only unaided. Gross switches could offset in aggregate success. These descriptive proportions were not independent-driver tests.')
fig,axes=plt.subplots(1,2,figsize=(9,4.8),layout='constrained',sharey=True)
for ax,field,label in zip(axes,['same_stall','same_aisle'],['Same parking space (%)','Same parking aisle (%)']):
    for j,mode,c in zip(range(2),['aisle','space'],colors[1:]):
        g=ch[(ch.occupancy==.95)&(ch.information==mode)].set_index('model').loc[['deterministic','rum','cpt']]
        ax.bar(np.arange(3)+(j-.5)*.34,g[field],width=.32,color=c,label=mode.title())
    ax.set_xticks(range(3),['M0','M1','CPT']);ax.set_xlabel(label);ax.set_ylim(0,100)
axes[0].set_ylabel('Agreement with unaided (%)');h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='outside lower center',ncol=2,frameon=False)
save(fig,'choice_agreement_bars','At 95% occupancy, bars showed the percentage of matched drivers parked in both worlds who chose the same space (left) or aisle (right) as unaided. Aisle/space in the legend named the information service, not the agreement measure. Success-switching drivers were excluded and reported separately. Pooled proportions were descriptive.')
for field,metric,label,name in [('door','walk_m','Walking among parked (m)','door_walking'),('intended_exit','exit_distance_m','Distance to intended exit (m)','exit_groups'),('mobility_limited','success','Parking success (%)','walking_constraint_success')]:
    frame=d[(d.model=='cpt')&(d.occupancy==.95)]
    if metric!='success':frame=frame[frame.success]
    grp=frame.groupby(['seed','information',field])[metric].agg(['mean','size']).reset_index();grp.to_csv(T/f'{name}_by_seed.csv',index=False)
    levels=sorted(grp[field].unique());fig,ax=plt.subplots(figsize=(8,4.8),layout='constrained')
    for j,(mode,c) in enumerate(zip(modes,colors)):
        for k,level in enumerate(levels):
            vals=grp[(grp.information==mode)&(grp[field]==level)]['mean'];mean,lo,hi=boot(vals);scale=100 if metric=='success' else 1
            x=k+(j-1)*.23;ax.bar(x,mean*scale,width=.21,color=c,label=mode.title() if k==0 else None)
            ax.errorbar(x,mean*scale,yerr=[[max(0,mean-lo)*scale],[max(0,hi-mean)*scale]],color='black',capsize=4)
    labels=[str(v).replace('door_','Door ').replace('exit_a','Exit A').replace('exit_b','Exit B') for v in levels]
    if field=='mobility_limited':labels=['No walking limit','Walking limited']
    ax.set_xticks(range(len(levels)),labels);ax.set_ylabel(label);ax.grid(axis='y',alpha=.18);ax.legend(loc='upper left',bbox_to_anchor=(1,1),frameon=False)
    save(fig,name,'CPT at 95% initial occupancy. Bars were equal-weight means of seed/subgroup means, with exploratory pointwise 95% seed-bootstrap intervals. '+('All arrivals contributed; walking limits differed from accessible-space eligibility.' if metric=='success' else 'Only parked drivers contributed; empty seed/subgroup cells were excluded. Successful cohorts could differ across arms. Distances were straight-line proximity, not route travel time.'))
# Spatial panel from the frozen configuration, not an outdated pilot map.
from panda_abm.environment import load_facility_from_lot_config
config=ROOT/'data/lot_config.json'
assert hashlib.sha256(config.read_bytes()).hexdigest()==design['source_sha256']['data/lot_config.json']
facility=load_facility_from_lot_config(config);spaces=[s for s in facility.spaces if not s.unavailable]
counts=d[(d.model=='cpt')&d.success].groupby(['occupancy','information','chosen_space']).size()/30
fig,axes=plt.subplots(2,3,figsize=(11,9),layout='constrained',sharex=True,sharey=True)
for i,occ in enumerate([.4,.95]):
    for ax,mode in zip(axes[i],modes):
        ax.scatter([s.x_m for s in spaces],[s.y_m for s in spaces],s=7,color='#dddddd')
        selected=[s for s in spaces if counts.get((occ,mode,s.space_id),0)>0]
        im=ax.scatter([s.x_m for s in selected],[s.y_m for s in selected],s=20,c=[counts.get((occ,mode,s.space_id),0) for s in selected],vmin=0,vmax=counts.max(),cmap='viridis')
        for points,marker,color in [(facility.walmart_doors,'s','black'),(facility.entry_points,'D','#a63b18')]:
            ax.scatter(*np.array(points).T,marker=marker,c=color,s=50)
        ax.set_aspect('equal');ax.set_xlabel(f'{mode.title()} / east (m)')
    axes[i,0].set_ylabel(f'{occ:.0%} occupancy / north (m)')
fig.colorbar(im,ax=axes,label='Parkings per space per run',shrink=.7)
save(fig,'spatial_parking_maps','CPT parking selections at 40% and 95% initial occupancy over 30 replications, with a shared scale. Grey points were unselected usable spaces; black squares were store doors; brown diamonds were vehicle accesses. Estimated geometry; stall reuse could occur. Counts described simulated choices, not observed occupancy.')
catalog=OUT/'expanded_figure_catalogue.md'
catalog.write_text('# Restored spatial and distributional results\n\nThese ten additional figures used the corrected 810-run, 30-seed core (64,800 outcome records), not the earlier 270-run pilot. No simulations were rerun. They supplemented the [12 original paper figures](figure_catalogue.md), giving 22 figure pairs to select from. More figures did not imply more independent evidence.\n\n'+'\n\n'.join(f'## {name}\n\n![{name}](figures/{name}.png)\n\n{cap}\n\n[Vector PDF](figures/{name}.pdf)' for name,cap in records)+'\n',encoding='utf-8')
outputs=[p for name,_ in records for p in [F/f'{name}.png',F/f'{name}.pdf']]
(OUT/'expanded_provenance.json').write_text(json.dumps({'source_sha256':{str((S/n).relative_to(ROOT)):hashlib.sha256((S/n).read_bytes()).hexdigest() for n in ['drivers.csv','runs.csv','design.json']},'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'behavioral_runs':810,'seeds':30,'new_simulations':0,'figures':len(records),'output_sha256':{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs}},indent=2),encoding='utf-8')
print(f'Added {len(records)} figures from corrected core results.')
