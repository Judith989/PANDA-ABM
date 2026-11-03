"""Report the completed final-output profile analysis and update paper fragments."""
from pathlib import Path
import hashlib,json,re,shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
ANALYSIS=ROOT/'research/tcss/profile_reanalysis_20261030'
PAPER=ROOT/'paper/results_section'

def write(path,value):Path(path).write_text(value,encoding='utf-8')
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify(design):
    for name,h in (design['input_sha256']|design['analysis_source_sha256']).items():
        assert digest(ROOT/name)==h,name
    records=pd.read_csv(ANALYSIS/'prepared_records.csv.gz')
    # The literal family name "null" is data; only blanks denote missing fields.
    diagnostics=pd.read_csv(ANALYSIS/'profile_diagnostics.csv',keep_default_na=False,na_values=[''])
    assigned=pd.read_csv(ANALYSIS/'profile_assignments.csv.gz')
    selection=pd.read_csv(ANALYSIS/'mixture_selection.csv')
    keys=['context','population','occupancy','seed','model','information']
    assert len(records)==122400 and len(records.groupby(keys))==1530
    assert records.groupby(keys).size().eq(80).all()
    assert not records.duplicated(keys+['driver']).any()
    assert len(diagnostics)==161 and len(diagnostics[diagnostics.family!='null'])==81
    assert selection[selection.selected].converged.all()
    assert assigned.analysis_eligible.all() and assigned.success.all()
    assert not assigned.mobility_limited.any() and not assigned.eligible.any() and assigned.permit.isna().all()
    assert np.isfinite(assigned[['search_s','walk_relative','posterior']]).all().all()
    assert assigned.posterior.between(0,1).all()
    for row in diagnostics[diagnostics.family!='null'].itertuples():
        g=assigned[assigned.fit_id==row.fit_id]
        assert len(g[g.validation])==row.validation_n and len(g[~g.validation])==row.train_n
        assert set(g[g.validation].seed).isdisjoint(g[~g.validation].seed)
        expected=set(design['matched_control_validation_seeds'] if row.family in ['matched_base','constant_preferences'] else design['core_validation_seeds'])
        assert set(g[g.validation].seed)==expected
    result=dict(source_hashes_verified=len(design['input_sha256']),unique_trials=1530,outcomes=122400,
        real_data_fits=81,diagnostic_fits=80,all_selected_fits_converged=True,sample_and_seed_splits_verified=True)
    write(ANALYSIS/'verification.json',json.dumps(result,indent=2)+'\n')

def main():
    if '\\emph{Behavioral response profiles:}' in (PAPER/'results.tex').read_text(encoding='utf-8'):
        raise RuntimeError('Historical successful-driver analysis cannot overwrite the current all-driver manuscript. Use update_manuscript_all_driver_profiles.py for integration.')
    design=json.loads((ANALYSIS/'design.json').read_text())
    assert design['status']=='completed'
    for path,h in json.loads((ANALYSIS/'output_sha256.json').read_text()).items():
        assert digest(ANALYSIS/path)==h,path
    verify(design)
    diagnostics=pd.read_csv(ANALYSIS/'profile_diagnostics.csv',keep_default_na=False,na_values=[''])
    consistency=pd.read_csv(ANALYSIS/'cross_occupancy_consistency.csv')
    controls=pd.read_csv(ANALYSIS/'matched_preference_controls.csv')
    null=pd.read_csv(ANALYSIS/'null_challenges.csv')
    desc=pd.read_csv(ANALYSIS/'heldout_profile_descriptions.csv')
    core=diagnostics[diagnostics.family=='core'].copy()
    assert len(core)==27
    n_pass=int(core.candidate_supported.sum())
    by_model=core.groupby('model').agg(conditions=('fit_id','size'),screening_passes=('candidate_supported','sum'))
    assert (by_model.conditions==9).all()
    core_cons=consistency[(consistency.family=='core')&~((consistency.components_a==1)&(consistency.components_b==1))]
    low,high=core_cons.adjusted_rand.min(),core_cons.adjusted_rand.max()
    ctrl_pass=int(controls.candidate_supported_constant.sum())
    both_pass=int((controls.candidate_supported_constant&controls.candidate_supported_varying).sum())
    transfer=diagnostics[diagnostics.family=='transfer']
    t_pass=int(transfer.candidate_supported.sum())
    heldout=pd.read_csv(ANALYSIS/'profile_assignments.csv.gz');heldout=heldout[heldout.validation]
    layout=[]
    for occ in [.8,.95]:
        for model in ['deterministic','rum','cpt']:
            for info in ['unaided','aisle','space']:
                a=heldout[(heldout.family=='core')&np.isclose(heldout.occupancy,occ)&heldout.model.eq(model)&heldout.information.eq(info)]
                b=heldout[(heldout.family=='transfer')&np.isclose(heldout.occupancy,occ)&heldout.model.eq(model)&heldout.information.eq(info)]
                pair=a.merge(b,on=['seed','driver'],suffixes=('_a','_b'),validate='one_to_one')
                from sklearn.metrics import adjusted_rand_score
                layout.append(dict(occupancy=occ,model=model,information=info,n=len(pair),adjusted_rand=adjusted_rand_score(pair.behavior_regime_a,pair.behavior_regime_b)))
    layout_frame=pd.DataFrame(layout)
    layout_frame.to_csv(ANALYSIS/'cross_layout_consistency.csv',index=False)
    # Illustration rule is independent of group means: largest validation sample,
    # ties resolved by fixed model, occupancy, information ordering.
    supported=core[core.candidate_supported].copy()
    supported['model_order']=supported.model.map({'deterministic':0,'rum':1,'cpt':2})
    supported['information_order']=supported.information.map({'unaided':0,'aisle':1,'space':2})
    example=supported.sort_values(['validation_n','model_order','occupancy','information_order'],ascending=[False,True,True,True]).iloc[0] if len(supported) else None
    names={'deterministic':'deterministic utility','rum':'stochastic utility','cpt':'CPT'}
    plt.rcParams.update({'font.size':9,'font.weight':'bold','axes.labelsize':9,'axes.labelweight':'bold',
        'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,'pdf.fonttype':42,
        'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(2,1,figsize=(3.5,3.5),layout='constrained')
    fig.get_layout_engine().set(w_pad=.05,h_pad=.07)
    order=['deterministic','rum','cpt'];cols=['#617080','#009e73','#0072b2']
    bars=axs[0].bar(range(3),[by_model.loc[m,'screening_passes'] for m in order],color=cols,width=.55)
    axs[0].bar_label(bars,padding=3,weight='bold')
    axs[0].set(xticks=range(3),xticklabels=['Deterministic','Stochastic','CPT'],ylim=(0,9),yticks=[0,3,6,9],ylabel='Conditions passing\nprofile checks (of 9)',xlabel='(a) Decision model')
    for i,(model,color) in enumerate(zip(order,cols)):
        a=core_cons[core_cons.model==model].adjusted_rand.to_numpy()
        axs[1].scatter(i+np.linspace(-.1,.1,len(a)),a,color=color,s=16,zorder=3)
        if len(a):axs[1].hlines(np.median(a),i-.2,i+.2,color='black',lw=1.5)
    axs[1].set(xticks=range(3),xticklabels=['Deterministic','Stochastic','CPT'],ylim=(-.08,1.05),yticks=[0,.5,1],ylabel='Cross-occupancy\nassignment agreement',xlabel='(b) Decision model')
    axs[1].axhline(0,color='0.6',lw=.7)
    fig.canvas.draw();renderer=fig.canvas.get_renderer()
    for text in fig.findobj(matplotlib.text.Text):
        if text.get_visible() and text.get_text() and not text.get_clip_on():
            box=text.get_window_extent(renderer)
            assert box.x0>=-2 and box.y0>=-2 and box.x1<=fig.bbox.width+2 and box.y1<=fig.bbox.height+2,text.get_text()
    for ext in ['png','pdf']:fig.savefig(PAPER/'figures'/f'column_profile_evidence.{ext}',dpi=350)
    plt.close(fig);shutil.copy2(PAPER/'figures/column_profile_evidence.pdf',PAPER/'img/column_profile_evidence.pdf')
    caption=r'Behavioral-group checks and cross-occupancy assignment agreement. Black lines indicate medians.'
    record=dict(name='column_profile_evidence',caption=caption,label='profile_evidence_fig',width_inches=3.5,height_inches=3.5)
    write(PAPER/'profile_figure_record.json',json.dumps(record,indent=2)+'\n')
    overrides=json.loads((PAPER/'caption_overrides.json').read_text());overrides['profile_evidence_fig']=caption
    write(PAPER/'caption_overrides.json',json.dumps(overrides,indent=2)+'\n')
    figure=r'''\begin{figure}[!t]
\centering
\includegraphics[width=\columnwidth]{img/column_profile_evidence.pdf}
\caption{'''+caption+r'''}
\label{profile_evidence_fig}
\end{figure}'''
    null_false=int(null[null.context.isin(['single_skewed','curved_continuum'])].screening_passes.sum())
    paragraphs=rf'''\emph{{Behavioral profiles:}}
Search--walking groups passed the validation checks in
{n_pass} of 27 baseline conditions: {int(by_model.loc['rum','screening_passes'])}
under stochastic utility and {int(by_model.loc['cpt','screening_passes'])}
under CPT, as shown in Fig.~\ref{{profile_evidence_fig}}.
These counts describe profile checks, not model accuracy.

{figure}

Across separately fitted conditions, held-out assignment
consistency ranged from
{low:.2f} to {high:.2f} using the adjusted Rand index; one indicates
identical partitions, and zero is the chance-adjusted baseline.
The low agreement showed that group membership changed with occupancy.
The figure includes all fitted conditions, excluding pairs in
which both fits selected one group. Comparisons include the
same drivers meeting the analysis criteria in both conditions.

With preference weights held constant, {ctrl_pass} of 18 matched
control fits passed the checks; other driver attributes could
still vary. The synthetic layout produced {t_pass} supported
{'partition' if t_pass==1 else 'partitions'} in 18 conditions. Group structure therefore depended
on the decision rule and parking context. Across layouts,
assignment agreement ranged from {layout_frame.adjusted_rand.min():.2f}
to {layout_frame.adjusted_rand.max():.2f}.
'''
    table=''
    if example is not None:
        d=desc[desc.fit_id==example.fit_id].sort_values('behavior_regime')
        rows='\n'.join(f"{int(x.behavior_regime)+1} & {int(x.drivers)} & {x.search_s:.1f} & {x.walk_m:.1f}"+r' \\' for x in d.itertuples())
        condition=f"{names[example.model]} at {example.occupancy:.0%} occupancy with {example.information} information".replace('%',r'\%').replace('unaided information','unaided search')
        table=r'''\begin{table}[!t]
\caption{Held-out behavioral groups for '''+condition+r'''.}
\label{profile_groups}
\centering
\small
\setlength{\tabcolsep}{5pt}
\begin{tabular}{@{}rrrr@{}}
\toprule
Group & Drivers & Search (s) & Walking (m)\\
\midrule
'''+rows+r'''
\bottomrule
\end{tabular}
\end{table}'''
        paragraphs+='\n'+r'Table~\ref{profile_groups} illustrates the held-out group means for '+condition+r'''. Group numbers describe this condition only and are
ordered by training search duration; they are not persistent
driver labels. The illustrated fit was selected by validation
sample size, with ties resolved by a fixed condition order.

'''+table+'\n'
        if d.loc[d.search_s.idxmax(),'walk_m']==d.walk_m.min():
            paragraphs+='\nThe group with the longest mean search had the shortest mean\nwalk, illustrating different search--walking tradeoffs.\n'
    paragraphs+=rf'''
The diagnostic datasets produced {null_false} screening passes
among 40 skewed or curved continuous datasets without distinct
underlying classes. These checks support contextual descriptions
of search and walking; they do not establish psychological
personas such as cost-sensitive or risk-averse drivers.
'''
    results_path=PAPER/'results.tex';s=results_path.read_text(encoding='utf-8')
    start=s.index('\\emph{Behavioral variation and profile interpretation:}') if '\\emph{Behavioral variation and profile interpretation:}' in s else s.index('\\emph{Behavioral profiles:}')
    end=s.index('\\subsection{Decision models',start)
    conclusion=r'''These findings address RQ1 by showing that driver variation
affected parking outcomes. Replacing individual preference
weights changed mean search duration, while walking-constraint
comparisons showed differences between driver groups.
The results support representing heterogeneous drivers when
evaluating parking strategies.

'''
    s=s[:start]+paragraphs+'\n'+conclusion+s[end:]
    s=s.replace('The findings remained conditional on estimated geometry,','Profile screening identified contextual outcome groups, but did\nnot validate permanent driver types. The findings also remained\nconditional on estimated geometry,')
    write(results_path,s);write(PAPER/'results.txt',s)
    framework=r'''% Insert within Proposed Framework / Driver Population Generator.
Driver behavior develops from continuous preferences, individual
constraints, and shared decision rules. As drivers search and
compete, their actions change the opportunities available to
others, allowing different parking responses to arise within
the same facility. Behavioral profiles are examined after the
simulation using recorded outcomes. Profile assignments describe
these responses; they do not determine driver parameters or
select decision rules. Their consistency is evaluated across
replications and parking conditions before interpretation.
'''
    write(PAPER/'framework_population_profiles.tex',framework)
    write(PAPER/'framework_population_profiles.txt',framework)
    exp=PAPER/'experimental_design_site.tex';e=exp.read_text(encoding='utf-8')
    anchor='Information effects are informed minus unaided outcomes within'
    method=r'''\emph{Behavioral-profile analysis:}
We examined search--walking patterns in 1,530 saved trials for
the three main models, including preference controls and the
synthetic layout. To limit grouping driven by hard constraints,
the profile sample includes parked drivers without walking
limits, accessible-space eligibility, or permits; exclusions
remain recorded. Features are $\log(1+T)$ and
$\log(1+d^w/r^w)$: search duration and walking relative to
the driver's reference distance.

Gaussian mixtures with one to six components are selected by
the Bayesian information criterion. Scaling and selection use
20 training replications, with ten held out; matched preference
controls use six and four. Checks cover held-out prediction,
group size, assignment confidence, and stability across 20
training-replication bootstrap refits. Log-score 95\% intervals use
5,000 resamples of held-out replications. Membership consistency
across occupancy and layout is measured by the adjusted Rand
index. Diagnostic datasets with and without distinct groups
test the screening procedure. Exact thresholds are retained
in the archived protocol. This exploratory analysis describes
outcome patterns without assigning psychological personas.

'''
    if '\\emph{Behavioral-profile analysis:}' in e:
        a=e.index('\\emph{Behavioral-profile analysis:}');b=e.index(anchor,a);e=e[:a]+e[b:]
    assert anchor in e;e=e.replace(anchor,method+anchor,1)
    write(exp,e);write(PAPER/'experimental_design_site.txt',e)
    # Compact evidence package without duplicating the many intermediate fit files.
    destination=PAPER/'profile_analysis';destination.mkdir(exist_ok=True)
    for name in ['design.json','screening_summary.csv','profile_diagnostics.csv','sample_accounting.csv',
        'heldout_profile_descriptions.csv','cross_occupancy_consistency.csv','cross_layout_consistency.csv',
        'matched_preference_controls.csv','null_challenges.csv','mixture_selection.csv',
        'prepared_records.csv.gz','profile_assignments.csv.gz','verification.json']:
        shutil.copy2(ANALYSIS/name,destination/name)
    source=destination/'source';source.mkdir(exist_ok=True)
    for p in [ROOT/'scripts/analyze_final_behavioral_profiles.py',Path(__file__),ROOT/'panda_abm/analysis/profiles.py']:
        shutil.copy2(p,source/p.name)
    packages=design['environment']['packages']|{'matplotlib':matplotlib.__version__}
    write(destination/'requirements.txt','\n'.join(f'{name}=={version}' for name,version in packages.items())+'\n')
    report=f'''# Final-output behavioral-profile reanalysis

This is an exploratory post-simulation analysis of the final TCSS evidence, not the earlier persona pilot. No new ABM simulations were run. The input contains 122,400 outcome records from 1,530 existing trials within the 3,400-trial programme. All recorded source hashes and frozen model-version inputs are retained in design.json.

## Results

- Core conditions passing all screens: **{n_pass}/27**. Per-model counts: {by_model.to_dict(orient='index')}.
- Constant-preference-weight screens: **{ctrl_pass}/18**; matched conditions passing in both populations: **{both_pass}/18**. These are not fully homogeneous-agent controls: other parameters and attributes can vary.
- Synthetic transfer conditions passing: **{t_pass}/18**.
- Cross-occupancy adjusted Rand range: **{low:.4f} to {high:.4f}**, excluding trivial single-group pairs. These are comparisons of independently fitted partitions on the same jointly eligible held-out drivers, not external predictive validation.
- Diagnostic skewed/curved continua passing screens despite having no discrete classes: **{null_false}/40**.

{null.to_string(index=False)}

## Interpretation

Mixtures summarize contextual search/walking patterns. Screening passes do not prove latent human types. One component is allowed, all selected component counts are retained, and selection at the six-component upper bound is not proof of six personas. Abandonment and constraint exclusions remain counted. Only outcome features enter fitting; preference coefficients are used solely for descriptive interpretation. No cost-sensitive or risk-averse personas are inferred from this free-parking, legal-only experiment.

All thresholds and splits were frozen before fitting this reanalysis, using the earlier exploratory protocol. This is not a preregistered or outcome-blind confirmatory study: aggregate outcomes had already been inspected. Training and validation split at replication level. Matching the smaller preference controls requires a separate six/four replication split. The primary 20/10 and matched six/four fits should not be treated as interchangeable estimates.

## Reproduction

Run scripts/analyze_final_behavioral_profiles.py in the repository's analysis environment with --prepared pointing to prepared_records.csv.gz and a new --output directory. The source functions and package versions are supplied in the paper evidence package. The earlier analysis remains untouched and its numerical findings are not pooled with these results.
'''
    write(ANALYSIS/'REPORT.md',report);write(destination/'REPORT.md',report)
    write(PAPER/'profile_analysis_status.md',report)
    metadata=json.loads((PAPER/'single_column_provenance.json').read_text())
    metadata['figures']=[x for x in metadata['figures'] if x['label']!='profile_evidence_fig']+[record]
    write(PAPER/'single_column_provenance.json',json.dumps(metadata,indent=2)+'\n')
    write(PAPER/'single_column_figures.md','# Single-column Results figures\n\n'+'\n\n'.join('## '+x['name']+'\n\n![Figure](figures/'+x['name']+'.png)\n\n'+x['caption'].replace(r'\%','%') for x in metadata['figures'])+'\n')
    assert len(re.findall(r'\\begin\{figure\}',s))==15
    assert len(re.findall(r'\\begin\{table\*?\}',s))==(4 if example is not None else 3)
    print(f'Core {n_pass}/27; constant weights {ctrl_pass}/18; transfer {t_pass}/18; cross-occupancy {low:.3f}--{high:.3f}; diagnostic false-class screens {null_false}/40.')
    print('Framework insertion, methods, Results, figure and supporting evidence updated.')

if __name__=='__main__':main()
