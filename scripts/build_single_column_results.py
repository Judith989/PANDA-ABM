"""Replot saved results at IEEE column width; no simulations or new inference."""
from pathlib import Path
import hashlib
import json
import shutil
import re
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'paper/results_section'
FIG=OUT/'figures'
DATA=ROOT/'paper/tables/complete'
sources={}

def read(path):
    path=ROOT/path
    sources[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return pd.read_csv(path)

ctx=read(Path('paper/tables/complete/robustness_context_information_effects.csv'))
linear=read(Path('paper/tables/complete/first_batch_information_effects.csv'))
means=read(Path('paper/tables/complete/robustness_benchmark_cells.csv'))
agree=read(Path('paper/tables/complete/first_batch_linear_cpt_choice_agreement.csv'))
transform=read(Path('paper/tables/complete/first_batch_prospect_transform_effects.csv'))
adopt=read(Path('paper/tables/complete/robustness_mixed_adoption_system_effects.csv'))
cohorts=read(Path('paper/tables/complete/robustness_mixed_adoption_group_effects.csv'))
resolution=read(Path('paper/tables/complete/robustness_cpt_transform_resolution_80.csv'))
switches=read(Path('paper/tables/current_individual_changes.csv'))
doors=read(Path('paper/tables/door_walking_by_seed.csv'))
exits=read(Path('paper/tables/exit_groups_by_seed.csv'))
archive=ROOT/'results/tcss_first_batch_20261028'
design=json.loads((archive/'design.json').read_text())
assert hashlib.sha256((archive/'drivers.csv').read_bytes()).hexdigest()==design['output_sha256']['drivers.csv']
drivers=read(Path('results/tcss_first_batch_20261028/drivers.csv'))
drivers=drivers[(drivers.variant=='base')&(drivers.model=='cpt')&np.isclose(drivers.occupancy,.95)]
assert len(drivers)==7200
drivers[['seed','driver','information','search_s']].to_csv(OUT/'source_tables/search_distribution_cpt95.csv',index=False)
for name in ['current_individual_changes','door_walking_by_seed','exit_groups_by_seed']:
    shutil.copy2(ROOT/'paper/tables'/f'{name}.csv',OUT/'source_tables'/f'{name}.csv')

plt.rcParams.update({'font.size':9,'font.weight':'bold','axes.labelsize':9,
    'axes.labelweight':'bold','xtick.labelsize':8,'ytick.labelsize':8,
    'legend.fontsize':8,'lines.linewidth':1.4,'pdf.fonttype':42,
    'axes.spines.top':False,'axes.spines.right':False})
BLUE='#0072b2';ORANGE='#c46b00';GREY='#617080';PURPLE='#7651a8'
INFO=[('unaided','Unaided',GREY),('aisle','Aisle',ORANGE),('space','Space',BLUE)]
records=[]

def select(df,**kw):
    for k,v in kw.items():df=df[np.isclose(df[k],v) if isinstance(v,float) else df[k].eq(v)]
    return df

def one(df,**kw):
    a=select(df,**kw);assert len(a)==1,(kw,len(a));return a.iloc[0]

def canvas(height=2.35,rows=1):
    return plt.subplots(rows,1,figsize=(3.5,height),layout='constrained',squeeze=False)

def save(fig,name,caption,label):
    assert fig._suptitle is None and all(not ax.get_title() for ax in fig.axes)
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    for text in fig.findobj(matplotlib.text.Text):
        if text.get_visible() and text.get_text() and not text.get_clip_on():
            bounds=text.get_window_extent(renderer)
            assert bounds.x0>=-2 and bounds.y0>=-2 and bounds.x1<=fig.bbox.width+2 and bounds.y1<=fig.bbox.height+2,(name,text.get_text(),bounds)
    for ext in ['pdf','png']:fig.savefig(FIG/f'{name}.{ext}',dpi=350)
    (OUT/'img').mkdir(exist_ok=True)
    shutil.copy2(FIG/f'{name}.pdf',OUT/'img'/f'{name}.pdf')
    records.append(dict(name=name,caption=caption,label=label,width_inches=3.5,height_inches=fig.get_size_inches()[1]))
    plt.close(fig)

def err(ax,x,r,color,label=None):
    y=r.delta
    ax.errorbar(x,y,yerr=[[y-r.ci_low],[r.ci_high-y]],fmt='o-',color=color,capsize=3,ms=4,label=label)

models=['deterministic','rum','cpt','linear_cpt','simple']
names=['M0','M1','CPT','Linear CPT','Simple']
fig,axes=canvas(2.45);ax=axes[0,0]
offsets=[(-20,-15),(-15,7),(-18,8),(5,-10),(3,6)]
for m,name,c,offset in zip(models,names,[GREY,'#009e73',BLUE,PURPLE,ORANGE],offsets):
    row=one(means,occupancy=.8,model=m,information='space')
    ax.scatter(row.mean_search_s,row.mean_walk_parked_m,c=c,s=35,zorder=3)
    ax.annotate(name,(row.mean_search_s,row.mean_walk_parked_m),xytext=offset,textcoords='offset points',fontsize=8,weight='bold')
ax.set(xlabel='Mean search duration (s)',ylabel='Mean walking distance (m)',xlim=(28,51),ylim=(45,132));ax.grid(alpha=.18)
save(fig,'column_policies',r'All five policies with space information at 80\% occupancy. Points show descriptive means over 30 matched seeds; walking includes parked drivers. M0 is deterministic utility, M1 stochastic utility, linear CPT a mechanism control, and simple search a benchmark. Intervals for selected paired contrasts are reported in the tables.','five_policies')

fig,axes=canvas(3.6,2);a,b=axes[:,0]
for j,(field,name,c) in enumerate([('same_stall','Same space',BLUE),('same_aisle','Same aisle',ORANGE)]):
    vals=[100*select(agree,occupancy=o,information='space')[field].mean() for o in [.8,.95]]
    a.bar(np.arange(2)+(j-.5)*.32,vals,width=.3,color=c,label=name)
a.set(xticks=[0,1],xticklabels=['80%','95%'],ylim=(0,100),xlabel='(a) Initial occupancy',ylabel='Agreement (%)');a.legend(frameon=False,ncol=2,fontsize=8)
for occ,c,mark in [(.8,BLUE,'o'),(.95,ORANGE,'s')]:
    x=one(transform,occupancy=occ,information='space',metric='mean_search_s')
    y=one(transform,occupancy=occ,information='space',metric='mean_walk_parked_m')
    b.errorbar(x.cpt_minus_linear,y.cpt_minus_linear,xerr=[[x.cpt_minus_linear-x.ci_low],[x.ci_high-x.cpt_minus_linear]],yerr=[[y.cpt_minus_linear-y.ci_low],[y.ci_high-y.cpt_minus_linear]],fmt=mark,color=c,capsize=3,label=f'{occ:.0%}',ms=4)
b.axvline(0,c='0.6',lw=.7);b.axhline(0,c='0.6',lw=.7);b.set(xlabel='(b) Search change (s)',ylabel='Walking change (m)');b.legend(frameon=False,fontsize=8)
save(fig,'column_mechanisms',r'CPT versus linear CPT with space information and 30 matched seeds. (a) Mean within-seed agreement among drivers parked in both conditions. (b) CPT-minus-linear search and walking changes; error bars are marginal pointwise 95\% paired-seed intervals, not a joint confidence region.','mechanisms')

for metric,title,name,label in [('mean_search_s','Search change (s)','column_search_effect','information_results_fig'),('mean_walk_parked_m','Walking change (m)','column_walking_effect','walking_effects_fig'),('mean_exit_parked_m','Exit-distance change (m)','column_exit_effect','exit_effects_fig')]:
    a=np.array([[np.nan if m=='linear_cpt' and occ==.4 else (one(linear,variant='base',occupancy=occ,model=m,information=i,metric=metric).delta if m=='linear_cpt' else one(ctx,condition='base',occupancy=occ,model=m,information=i,metric=metric).delta) for i in ['aisle','space']] for occ in [.4,.8,.95] for m in models])
    fig,axes=canvas(3.35);ax=axes[0,0];bound=max(1.,np.nanmax(abs(a)));cmap=plt.colormaps['RdBu_r'].copy();cmap.set_bad('#e2e8f0')
    im=ax.imshow(a,cmap=cmap,vmin=-bound,vmax=bound,aspect='auto')
    for y in range(15):
        for x in range(2):
            val=a[y,x];text='N/A' if np.isnan(val) else ('0.0' if abs(val)<.05 else f'{val:+.1f}')
            ax.text(x,y,text,ha='center',va='center',fontsize=8,weight='bold',color='white' if abs(val)>.62*bound else 'black')
    ax.set_xticks([0,1],['Aisle','Space']);ax.set_yticks(range(15),[f'{occ:.0%} {n}' for occ in [.4,.8,.95] for n in names]);ax.set_xlabel('Information condition')
    for y in [4.5,9.5]:ax.axhline(y,color='white',lw=2)
    cb=fig.colorbar(im,ax=ax,orientation='horizontal',pad=.03,shrink=.9);cb.set_label(title)
    cap=title.replace(' (s)','').replace(' (m)','')+r' relative to unaided search over 30 matched seeds. Printed values are descriptive paired means; colours do not classify significance. N/A marks untested 40\% linear-CPT cells.'
    if metric!='mean_search_s':cap+=r' Distances include parked drivers separately in each condition; successful cohorts can differ.'
    save(fig,name,cap,label)

fig,axes=canvas(3.45,2)
for ax,metric,ylabel,panel in zip(axes[:,0],['mean_search_s','claims_per_arrival'],['Search change (s)','Failed-claim change\nper arrival'],['(a)','(b)']):
    for info,c in [('aisle',ORANGE),('space',BLUE)]:
        g=select(adopt,occupancy=.95,model='cpt',information=info,metric=metric).sort_values('adoption')
        ax.errorbar(g.adoption*100,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o-',color=c,capsize=3,ms=4,label=info.title())
    ax.axhline(0,c='0.6',lw=.7);ax.set(xlabel=panel+' Adoption (%)',ylabel=ylabel,xticks=[25,50,75]);ax.legend(frameon=False,ncol=2,fontsize=8)
save(fig,'column_adoption',r'CPT at 95\% initial occupancy: (a) search and (b) failed-claim changes relative to all-unaided search across ten matched seeds. Error bars are pointwise 95\% paired-seed intervals.','adoption_fig')

fig,axes=canvas(2.25);ax=axes[0,0]
for group,c,name in [('fixed_informed',BLUE,'Fixed informed'),('fixed_unaided',PURPLE,'Fixed unaided')]:
    g=select(cohorts,occupancy=.95,model='cpt',information='space',metric='search_s',cohort=group).sort_values('adoption')
    ax.errorbar(g.adoption*100,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o-',c=c,capsize=3,ms=4,label=name)
ax.axhline(0,c='0.6',lw=.7);ax.set(xlabel='Space-information adoption (%)',ylabel='Search change (s)',xticks=[25,50,75])
handles,labels=ax.get_legend_handles_labels()
fig.legend(handles,labels,loc='outside upper center',ncol=2,frameon=False,fontsize=8)
save(fig,'column_cohorts',r'Fixed-cohort search effects under CPT space information at 95\% occupancy. Each cohort retains its own access and is compared with the same drivers under all-unaided search. Error bars are pointwise 95\% paired-seed intervals across ten seeds.','fixed_cohorts_fig')

fig,axes=canvas(3.45,2)
for ax,metric,xlab in zip(axes[:,0],['mean_search_s','mean_walk_parked_m'],['(a) Search change (s)','(b) Walking change (m)']):
    for j,condition in enumerate(['base','E3a','E3b','E4']):
        row=one(ctx,condition=condition,occupancy=.95,model='cpt',information='space',metric=metric)
        ax.errorbar(row.delta,j,xerr=[[row.delta-row.ci_low],[row.ci_high-row.delta]],fmt='o',color=BLUE,capsize=3,ms=4)
    ax.axvline(0,c='0.6',lw=.7);ax.set(yticks=range(4),yticklabels=['Static (30)','Departures (10)','Delay (10)','Synthetic (30)'],xlabel=xlab);ax.invert_yaxis()
save(fig,'column_robustness',r'CPT space-information changes relative to unaided search at 95\% occupancy. Parentheses give seed counts; intervals are pointwise 95\% paired-seed intervals. Context means with different seed counts are not the matched context-change estimates reported in the text.','robustness_fig')

fig,axes=canvas(2.15);ax=axes[0,0];g=select(resolution,information='space',metric='mean_search_s').sort_values('integration')
ax.errorbar(g.integration,g.delta,yerr=[g.delta-g.ci_low,g.ci_high-g.delta],fmt='o-',c=PURPLE,capsize=3,ms=4);ax.axhline(0,c='0.6',lw=.7);ax.set(xlabel='Physical time step (s)',ylabel='CPT minus linear\nsearch duration (s)',xticks=[.25,.5,1.])
save(fig,'column_resolution',r'CPT-minus-linear search differences with space information at 80\% occupancy, using the same ten seeds at every physical time step. Error bars are pointwise 95\% paired-seed intervals.','resolution_fig')

fig,axes=canvas(2.35);ax=axes[0,0]
for j,info,c in [(0,'aisle',ORANGE),(1,'space',BLUE)]:
    g=select(switches,occupancy=.95,information=info).set_index('model').loc[['deterministic','rum','cpt']]
    x=np.arange(3)+(j-.5)*.32
    ax.bar(x,g.gained,width=.3,color=c,label=info.title());ax.bar(x,-g.lost,width=.3,color=c,alpha=.5,hatch='///')
ax.axhline(0,c='0.25',lw=.8);ax.set(xticks=range(3),xticklabels=['M0','M1','CPT'],ylabel='Matched arrivals (%)',ylim=(-8,10));ax.legend(frameon=False,ncol=2)
save(fig,'column_success_switches',r'Information versus unaided search at 95\% occupancy for the three main behavioral models. Positive bars show drivers who parked only with information; negative hatched bars show drivers who parked only unaided. Pooled proportions across 30 seeds are descriptive, not independent-driver tests.','success_switches_fig')

fig,axes=canvas(3.65,2)
for ax,df,field,ylabel,xlab,levels in [(axes[0,0],doors,'door','Walking\ndistance (m)','(a) Destination door',['door_1','door_2']),(axes[1,0],exits,'intended_exit','Intended-exit\ndistance (m)','(b) Intended exit',['exit_a','exit_b'])]:
    for j,(info,name,c) in enumerate(INFO):
        vals=[select(df,information=info,**{field:level})['mean'].dropna().values for level in levels]
        bp=ax.boxplot(vals,positions=np.arange(2)+(j-1)*.24,widths=.2,patch_artist=True,manage_ticks=False,showfliers=True,medianprops={'color':'black','linewidth':1.2},flierprops={'markersize':2})
        for patch in bp['boxes']:patch.set(facecolor=c,alpha=.65)
    ax.set(xticks=[0,1],xticklabels=['Door 1','Door 2'] if field=='door' else ['A','B'],ylabel=ylabel,xlabel=xlab);ax.grid(axis='y',alpha=.15)
fig.legend(handles=[plt.Line2D([],[],color=c,lw=4,label=name) for _,name,c in INFO],loc='outside lower center',ncol=3,frameon=False,fontsize=8)
save(fig,'column_door_exit',r'CPT at 95\% occupancy: distributions of replication-level walking and intended-exit distance means among parked drivers, grouped by door and intended exit. Boxes show medians and interquartile ranges, whiskers extend to 1.5 times the interquartile range, and points beyond whiskers are shown individually. Thirty seed means contribute per group. These are descriptive distributions, not treatment-effect intervals; successful cohorts can differ.','door_exit_fig')

fig,axes=canvas(2.4);ax=axes[0,0]
for j,(info,name,c) in enumerate(INFO):
    vals=drivers[drivers.information==info].search_s.dropna().values
    v=ax.violinplot(vals,positions=[j],showmedians=True,showextrema=False)
    for body in v['bodies']:body.set(facecolor=c,alpha=.65)
    v['cmedians'].set_color('black');ax.vlines(j,*np.quantile(vals,[.25,.75]),color='black',lw=3)
ax.set(xticks=range(3),xticklabels=[x[1] for x in INFO],ylabel='Search duration (s)',ylim=(0,610));ax.axhline(600,c='0.5',ls=':',lw=.8)
save(fig,'column_search_distribution',r'CPT search-duration distributions at 95\% occupancy, pooled over 30 seeds per condition. Black marks show medians and interquartile ranges; the dotted line marks the 600-s search deadline. Smoothed densities are descriptive and clipped at the displayed boundary. Interacting driver records are not independent replications.','search_distribution_fig')

# Spatial choice frequencies complement the fixed site-layout map.
from panda_abm.environment.facility import load_facility_from_lot_config
config_path=ROOT/'data/lot_config.json'
assert hashlib.sha256(config_path.read_bytes()).hexdigest()==design['source_sha256']['data/lot_config.json']
sources['data/lot_config.json']=hashlib.sha256(config_path.read_bytes()).hexdigest()
facility=load_facility_from_lot_config(config_path)
spaces=[space for space in facility.spaces if not space.unavailable]
counts=drivers[drivers.success].groupby(['information','chosen_space']).size()/30
counts.rename('mean_parkings_per_trial').to_csv(OUT/'source_tables/spatial_choices_cpt95.csv')
fig,axes=canvas(4.2,2)
for ax,info,panel in zip(axes[:,0],['unaided','space'],['(a) Unaided','(b) Space information']):
    ax.scatter([s.x_m for s in spaces],[s.y_m for s in spaces],s=.4,c='#d4d4d4',zorder=1)
    chosen=[s for s in spaces if counts.get((info,s.space_id),0)>0]
    im=ax.scatter([s.x_m for s in chosen],[s.y_m for s in chosen],s=2,marker='_',linewidths=.35,c=[counts.get((info,s.space_id),0) for s in chosen],cmap='viridis',vmin=0,vmax=counts.max(),zorder=2)
    for points,marker,c in [(facility.walmart_doors,'s','black'),(facility.entry_points,'D','#a63b18')]:
        ax.scatter(*np.array(points).T,s=18,marker=marker,color=c,zorder=3)
    ax.set_aspect('equal');ax.set(xlabel=panel+' / East (m)',ylabel='North (m)')
fig.colorbar(im,ax=axes[:,0].tolist(),orientation='horizontal',pad=.025,shrink=.85,label='Mean parkings / space / trial')
save(fig,'column_spatial_choices',r'Spatial parking selections under CPT at 95\% initial occupancy with (a) unaided search and (b) space information, using a common colour scale over 30 replications. Grey points are unselected usable spaces, black squares store doors, and brown diamonds vehicle access points. Counts describe simulated parking choices, not observed occupancy; space reuse can occur. Geometry is estimated.','spatial_choices_fig')

mobility=read(Path('paper/tables/walking_constraint_success_by_seed.csv'))
shutil.copy2(ROOT/'paper/tables/walking_constraint_success_by_seed.csv',OUT/'source_tables/walking_constraint_success_by_seed.csv')
assert (mobility.groupby(['information','mobility_limited']).size()==30).all()
fig,axes=canvas(2.55);ax=axes[0,0]
for j,(info,name,c) in enumerate(INFO):
    vals=[100*select(mobility,information=info,mobility_limited=v)['mean'].values for v in [False,True]]
    bp=ax.boxplot(vals,positions=np.arange(2)+(j-1)*.24,widths=.2,patch_artist=True,manage_ticks=False,medianprops={'color':'black'},flierprops={'markersize':2})
    for patch in bp['boxes']:patch.set(facecolor=c,alpha=.65)
ax.set(xticks=[0,1],xticklabels=['No walking\nlimit','Walking\nlimited'],ylabel='Parking success (%)',ylim=(0,105))
fig.legend(handles=[plt.Line2D([],[],c=c,lw=4,label=n) for _,n,c in INFO],loc='outside upper center',ncol=3,frameon=False,fontsize=8)
save(fig,'column_constraint_success',r'CPT parking success at 95\% occupancy by walking-constraint group. Boxes describe 30 replication-level subgroup success rates per condition; medians, interquartile ranges, and 1.5-interquartile-range whiskers are shown. All subgroup arrivals contribute. These descriptive distributions do not isolate the causal effect of a walking limit. Walking limitation and accessible-space eligibility are distinct attributes.','constraint_success_fig')

def block(record):
    env='figure*' if record.get('columns',1)==2 else 'figure'
    width='\\textwidth' if env=='figure*' else '\\columnwidth'
    return ('\\begin{'+env+'}[!t]\n\\centering\n\\includegraphics[width='+width+']{img/'+record['name']+'.pdf}\n\\caption{'+record['caption']+'}\n\\label{'+record['label']+'}\n\\end{'+env+'}')

profile_record=OUT/'profile_figure_record.json'
if profile_record.exists():
    records.append(json.loads(profile_record.read_text(encoding='utf-8')))
    sources[profile_record.relative_to(ROOT).as_posix()]=hashlib.sha256(profile_record.read_bytes()).hexdigest()
    profile_folder='all_driver_profile_analysis' if records[-1].get('columns')==2 else 'profile_analysis'
    files=['data/design.json','data/all_driver_audit.json','profile_descriptions.csv'] if profile_folder=='all_driver_profile_analysis' else ['design.json','profile_diagnostics.csv','cross_occupancy_consistency.csv']
    for name in files:
        source=OUT/profile_folder/name
        sources[source.relative_to(ROOT).as_posix()]=hashlib.sha256(source.read_bytes()).hexdigest()
caption_path=OUT/'caption_overrides.json'
if caption_path.exists():
    overrides=json.loads(caption_path.read_text())
    for record in records:record['caption']=overrides.get(record['label'],record['caption'])
by_label={r['label']:r for r in records}
path=OUT/'results.tex';s=path.read_text()
# Preserve the edited manuscript prose once all selected figures are present.
if not all('\\label{'+record['label']+'}' in s for record in records):
    for label in ['walking_effects_fig','exit_effects_fig','fixed_cohorts_fig','resolution_fig']:
        for match in reversed(list(re.finditer(r'\\begin\{figure\*?\}.*?\\end\{figure\*?\}',s,re.S))):
            if '\\label{'+label+'}' in match.group():s=s[:match.start()]+s[match.end():]
    for label in ['five_policies','mechanisms','information_results_fig','adoption_fig','robustness_fig']:
        pattern=r'\\begin\{figure\*?\}.*?\\end\{figure\*?\}'
        matches=[m for m in re.finditer(pattern,s,re.S) if '\\label{'+label+'}' in m.group()]
        assert len(matches)==1,(label,len(matches))
        replacement=block(by_label[label])
        if label=='information_results_fig':replacement+='\n\n'+block(by_label['walking_effects_fig'])+'\n\n'+block(by_label['exit_effects_fig'])
        if label=='adoption_fig':replacement+='\n\n'+block(by_label['fixed_cohorts_fig'])
        if label=='robustness_fig':replacement+='\n\n'+block(by_label['resolution_fig'])
        m=matches[0];s=s[:m.start()]+replacement+s[m.end():]

    s=s.replace('Fig.~\\ref{five_policies} compares all five policies across the three\ninformation conditions.', 'Fig.~\\ref{five_policies} shows the search--walking tradeoff for all\nfive policies with space information at 80\\% occupancy.')
    s=s.replace('(Fig.~\\ref{information_results_fig}). Under M0, M1, and CPT,', '(Figs.~\\ref{information_results_fig}--\\ref{exit_effects_fig}). Under M0, M1, and CPT,')
    cohort_sentence='Fixed-cohort effects are shown in Fig.~\\ref{fixed_cohorts_fig}.\n'
    while cohort_sentence+cohort_sentence in s:s=s.replace(cohort_sentence+cohort_sentence,cohort_sentence)
    if cohort_sentence not in s:s=s.replace('Drivers without information could also benefit from changes',cohort_sentence+'Drivers without information could also benefit from changes')
    s=s.replace('At 80\\% occupancy, CPT-minus-linear search differences remained', 'In Fig.~\\ref{resolution_fig}, CPT-minus-linear search differences at\n80\\% occupancy remained')
    insertions=[
        ('\\subsection{Information effects',r'''A separate information-versus-unaided comparison
    (Fig.~\ref{success_switches_fig}) identified drivers who gained or lost
    parking success. Gross gains and losses could offset in the net effect;
    these descriptive proportions complemented the aggregate success means.

    '''+block(by_label['success_switches_fig'])+'\n\n'),
        ('The decision model affected the estimated information benefit.',r'''The pooled distributions in Fig.~\ref{search_distribution_fig}
    complemented mean search effects by showing variation in individual
    outcomes, including long searches. Door- and exit-specific distributions
    (Fig.~\ref{door_exit_fig}) separated proximity outcomes by trip destination.
    These distributions described variation between replication-level means;
    they did not isolate causal effects of door or exit assignment.

    '''+block(by_label['search_distribution_fig'])+'\n\n'+block(by_label['door_exit_fig'])+'\n\n'),
        ('The decision model affected the estimated information benefit.',r'''Spatial choice frequencies (Fig.~\ref{spatial_choices_fig}) locate the
    spaces selected under unaided and space-informed search. This outcome map
    complements the fixed inventory and navigation map in the experimental design;
    the colour scale represents parking selections across replications.

    '''+block(by_label['spatial_choices_fig'])+'\n\n'),
        ('\\subsection{Robustness and transfer across layouts}',r'''Fig.~\ref{constraint_success_fig} reports parking success separately
    for drivers with and without walking limits, complementing the search-effect
    comparison. The subgroup distributions include all arrivals within each group;
    they do not establish a causal effect of assigning a walking constraint.

    '''+block(by_label['constraint_success_fig'])+'\n\n')]
    for anchor,text in insertions:
        if text.splitlines()[0] not in s:
            assert anchor in s;s=s.replace(anchor,text+anchor,1)
for record in records:
    matches=[m for m in re.finditer(r'\\begin\{figure\*?\}.*?\\end\{figure\*?\}',s,re.S) if '\\label{'+record['label']+'}' in m.group()]
    assert len(matches)==1
    match=matches[0];s=s[:match.start()]+block(record)+s[match.end():]
path.write_text(s,encoding='utf-8');(OUT/'results.txt').write_text(s,encoding='utf-8')
assert len(re.findall(r'\\begin\{figure\*?\}',s))==len(records)
assert s.count('\\begin{figure*}')==sum(r.get('columns',1)==2 for r in records)
metadata={'method':'Saved ABM outcomes. Most figures use 3.5-inch columns; the all-driver profile comparison spans two columns. No new ABM simulations.',
          'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'fonts':'Bold labels 9 pt; ticks and legends 8 pt at native column width. No embedded titles.',
          'source_sha256':sources,'figures':records,
          'output_sha256':{p.relative_to(OUT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in FIG.glob('column_*')}}
(OUT/'single_column_provenance.json').write_text(json.dumps(metadata,indent=2)+'\n')
manifest_path=OUT/'asset_provenance.json'
manifest=json.loads(manifest_path.read_text())
profile_panels=(3 if records[-1].get('columns')==2 else 2) if profile_record.exists() else 0
manifest.update(main_figures=len(records),main_figure_panels=19+profile_panels,map_figures=1,result_figure_layout='14 single-column figures; one two-column all-driver profile comparison' if profile_panels==3 else 'Single-column figures, native width 3.5 inches')
manifest['source_sha256'].update(sources)
manifest['output_sha256'].update(metadata['output_sha256'])
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
(OUT/'single_column_figures.md').write_text('# Results figure gallery\n\n'+ '\n\n'.join('## '+r['name']+'\n\n![Figure](figures/'+r['name']+'.png)\n\n'+r['caption'].replace(r'\%','%') for r in records)+'\n',encoding='utf-8')
print(f'Updated {len(records)} Results figures; Results TEX/TXT synchronized; no new simulations.')
