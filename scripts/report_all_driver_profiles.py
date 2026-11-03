"""Tables, scientific figures and interpretation for all-driver response profiles."""
from pathlib import Path
import hashlib,json,re,shutil,zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'research/tcss/all_driver_profiles_20261102'
OUT=ROOT/'paper/all_driver_profiles_20261102'
MODELS=['deterministic','rum','cpt'];NAMES={'deterministic':'Deterministic','rum':'Stochastic','cpt':'CPT'}
COLORS={'unaided':'#657383','aisle':'#c07800','space':'#0072b2'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,s):Path(p).write_text(s,encoding='utf-8')
def read(name):return pd.read_csv(DATA/name)
def pick(df,**values):
    for k,v in values.items():df=df[np.isclose(df[k],v)] if isinstance(v,float) else df[df[k]==v]
    assert len(df)==1,(values,len(df));return df.iloc[0]
def interval(r,digits=1):return f'{r["mean"]:+.{digits}f} [{r.ci_low:+.{digits}f}, {r.ci_high:+.{digits}f}]'
def markdown_table(df):
    return '| '+' | '.join(map(str,df.columns))+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(map(str,row))+' |' for row in df.itertuples(index=False,name=None))

def main():
    design=json.loads((DATA/'design.json').read_text());assert design['status']=='completed'
    for name,h in json.loads((DATA/'output_sha256.json').read_text()).items():assert sha(DATA/name)==h,name
    for name,h in design['input_sha256'].items():assert sha(ROOT/name)==h,name
    OUT.mkdir(parents=True,exist_ok=True);figures=OUT/'figures';figures.mkdir(exist_ok=True)
    labels=read('all_driver_profile_assignments.csv');outcomes=read('profile_outcomes.csv');effects=read('information_effects.csv')
    heldout=labels[labels.heldout];rows=[];diagnostics=[]
    for model in MODELS:
        diag=json.loads((DATA/f'{model}_diagnostics.json').read_text());diagnostics.append({'model':model}|diag)
        a=labels[labels.model==model];probes=np.load(DATA/f'{model}_response_features.npz')['primary'].reshape(2400,4,3,4)
        assert len(a)==2400
        for profile in sorted(a.profile.unique()):
            g=a[a.profile==profile];v=g[g.heldout];t=g[~g.heldout]
            mask=(a.profile==profile)&a.heldout
            data=probes[mask]
            row=dict(model=model,profile=int(profile),training_drivers=len(t),heldout_drivers=len(v),
                training_fraction=len(t)/1600,heldout_fraction=len(v)/800,
                walking_limited_pct=100*v.mobility_limited.mean(),accessible_eligible_pct=100*v.eligible.mean(),
                reserved_permit_pct=100*v.permit.eq('reserved').mean(),
                mean_walk_weight=v.beta_walk.mean(),mean_search_weight=v.beta_search.mean(),
                mean_exit_weight=v.beta_exit.mean(),mean_availability_weight=v.beta_availability.mean(),
                mean_loss_aversion=v.loss_aversion.mean(),mean_temperature=v.temperature.mean(),
                bootstrap_jaccard=diag['per_group_bootstrap_jaccard'][str(profile)],
                continue_early=data[:,:,0,3].mean(),continue_late=data[:,:,2,3].mean(),
                near_door_choice=data[:,0,:,0].mean(),reliable_choice=data[:,1,:,1].mean(),
                fast_approach_choice=data[:,2,:,1].mean(),restricted_menu_continue=data[:,3,:,3].mean())
            row['size_and_repeatability_checks']=bool(row['training_fraction']>=.05 and row['heldout_fraction']>=.05 and row['bootstrap_jaccard']>=.75)
            rows.append(row)
    traits=pd.DataFrame(rows);traits.to_csv(OUT/'profile_descriptions.csv',index=False)
    component_summary=traits.groupby('model').agg(candidate_components=('profile','size'),
        components_meeting_size_and_repeatability_checks=('size_and_repeatability_checks','sum'))
    component_summary.to_csv(OUT/'component_repeatability_summary.csv')
    aliases={
        ('deterministic',3):'Availability-oriented responses',
        ('deterministic',5):'Door-oriented responses',
        ('rum',1):'Mixed-choice responses without recorded access constraints',
        ('rum',2):'Accessible-eligibility-linked responses',
        ('rum',3):'Reserved-permit-linked responses',
        ('rum',4):'More late-search rejection',
        ('rum',5):'Walking-limit-dominated responses',
        ('rum',6):'Walking-limit-dominated responses with a different feasible set',
        ('cpt',1):'Availability and short-approach responses',
        ('cpt',2):'Greater walking emphasis',
        ('cpt',3):'Eligibility and permit-linked responses',
    }
    named=traits.copy();named['posthoc_description']=[aliases.get((r.model,r.profile),'Mixed candidate response pattern') for r in traits.itertuples()]
    named.to_csv(OUT/'posthoc_profile_descriptions.csv',index=False)
    pd.DataFrame(diagnostics).drop(columns=['per_group_bootstrap_jaccard']).to_csv(OUT/'profile_validation.csv',index=False)
    plt.rcParams.update({'font.size':9,'font.weight':'bold','axes.labelsize':9,'axes.labelweight':'bold',
        'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,'pdf.fonttype':42,'lines.linewidth':1.5,
        'axes.spines.top':False,'axes.spines.right':False})
    def save(fig,name):
        assert fig._suptitle is None and all(not ax.get_title() for ax in fig.axes)
        fig.canvas.draw();renderer=fig.canvas.get_renderer()
        for obj in fig.findobj(matplotlib.text.Text):
            if obj.get_visible() and obj.get_text() and not obj.get_clip_on():
                b=obj.get_window_extent(renderer)
                assert b.x0>=-2 and b.y0>=-2 and b.x1<=fig.bbox.width+2 and b.y1<=fig.bbox.height+2,(name,obj.get_text())
        for ext in ['pdf','png']:fig.savefig(figures/f'{name}.{ext}',dpi=350)
        plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(7,2.8),layout='constrained',sharey=True)
    for ax,model,letter in zip(axes,MODELS,'abc'):
        for j,info in enumerate(['unaided','aisle','space']):
            g=pick_frame(outcomes,split='heldout',model=model,occupancy=.95,information=info,metric='success_pct')
            g=g[g.profile>0].sort_values('profile');xx=g.profile+(j-1)*.16
            ax.errorbar(xx,g['mean'],yerr=[g['mean']-g.ci_low,g.ci_high-g['mean']],fmt='o',ms=3.5,capsize=2,color=COLORS[info],label=info.title())
        ax.set(xticks=range(1,7),xticklabels=[f'P{i}' for i in range(1,7)],xlabel=f'({letter}) {NAMES[model]}',ylim=(0,103))
    axes[0].set_ylabel('Parking success (%)');axes[1].legend(loc='lower center',frameon=False,ncol=1)
    save(fig,'success_by_response_profile')
    fig,ax=plt.subplots(figsize=(3.5,2.7),layout='constrained')
    for j,info in enumerate(['unaided','aisle','space']):
        g=pick_frame(outcomes,split='heldout',model='rum',occupancy=.95,information=info,metric='success_pct')
        g=g[g.profile>0].sort_values('profile')
        ax.errorbar(g.profile+(j-1)*.16,g['mean'],yerr=[g['mean']-g.ci_low,g.ci_high-g['mean']],fmt='o',ms=3.5,capsize=2,color=COLORS[info],label=info.title())
    ax.set(xticks=range(1,7),xticklabels=[f'P{i}' for i in range(1,7)],xlabel='Candidate stochastic response profile',ylabel='Parking success (%)',ylim=(0,103))
    ax.legend(frameon=False,ncol=3,loc='lower center');save(fig,'stochastic_profile_success_column')
    fig,axes=plt.subplots(2,3,figsize=(7,4.7),layout='constrained',sharey='row')
    for row,(metric,ylabel) in enumerate([('success_pp','Success change\n(percentage points)'),('search_s','Search-duration\nchange (s)')]):
        for col,model in enumerate(MODELS):
            ax=axes[row,col]
            for j,info in enumerate(['aisle','space']):
                g=pick_frame(effects,split='heldout',model=model,occupancy=.95,information=info,metric=metric)
                g=g[g.profile>0].sort_values('profile')
                ax.errorbar(g.profile+(j-.5)*.18,g['mean'],yerr=[g['mean']-g.ci_low,g.ci_high-g['mean']],fmt='o',ms=3.5,capsize=2,color=COLORS[info],label=info.title())
            ax.axhline(0,c='0.5',lw=.8);ax.set(xticks=range(1,7),xticklabels=[f'P{i}' for i in range(1,7)],xlabel=f'({chr(97+row*3+col)}) {NAMES[model]}')
            if col==0:ax.set_ylabel(ylabel)
    axes[0,1].legend(frameon=False,ncol=2,loc='upper left');save(fig,'information_benefits_by_response_profile')
    fields=['continue_early','continue_late','near_door_choice','reliable_choice','fast_approach_choice','restricted_menu_continue']
    fig,ax=plt.subplots(figsize=(7,5.3),layout='constrained')
    image=ax.imshow(traits[fields].values,vmin=0,vmax=1,cmap='Blues',aspect='auto')
    ax.set(yticks=range(len(traits)),yticklabels=[f'{NAMES[r.model]} P{r.profile}' for r in traits.itertuples()],
        xticks=range(6),xticklabels=['Continue\nat 0 s','Continue\nat 420 s','Near door\n(menu 1)','Reliable\n(menu 2)','Fast approach\n(menu 3)','Continue\n(menu 4)'])
    for i,row in enumerate(traits[fields].values):
        for j,v in enumerate(row):ax.text(j,i,f'{v:.2f}',ha='center',va='center',fontsize=8,c='white' if v>.6 else 'black',weight='bold')
    fig.colorbar(image,ax=ax,label='Mean probe action probability',fraction=.035,pad=.025);save(fig,'response_profile_signatures')
    # Complete success table: descriptive mean replication percentages and paired effects.
    success_rows=[]
    for r in traits.itertuples():
        row=dict(model=r.model,profile=r.profile,heldout_drivers=r.heldout_drivers,bootstrap_jaccard=r.bootstrap_jaccard)
        for info in ['unaided','aisle','space']:
            q=pick(outcomes,split='heldout',model=r.model,occupancy=.95,information=info,profile=r.profile,metric='success_pct')
            row[f'{info}_success_pct']=q['mean'];row[f'{info}_ci_low']=q.ci_low;row[f'{info}_ci_high']=q.ci_high
        for metric in ['success_pp','search_s']:
            q=pick(effects,split='heldout',model=r.model,occupancy=.95,information='space',profile=r.profile,metric=metric)
            row[f'space_{metric}']=q['mean'];row[f'space_{metric}_ci_low']=q.ci_low;row[f'space_{metric}_ci_high']=q.ci_high
        success_rows.append(row)
    success=pd.DataFrame(success_rows);success.to_csv(OUT/'parking_success_95_by_profile.csv',index=False)
    compact=[]
    for r in success.itertuples():compact.append(f"{NAMES[r.model]} P{r.profile} & {r.heldout_drivers} & {r.unaided_success_pct:.1f} & {r.aisle_success_pct:.1f} & {r.space_success_pct:.1f} & {r.space_success_pp:+.1f}"+r' \\')
    table=r'''\begin{table*}[!t]
\centering\small
\caption{Mean replication-level parking success by candidate response profile at 95\% occupancy.}
\label{tab:all_driver_profiles}
\begin{tabular}{@{}lrrrrr@{}}
\toprule
Profile & Held-out drivers & Unaided (\%) & Aisle (\%) & Space (\%) & Space change (pp)\\
\midrule
'''+ '\n'.join(compact)+r'''
\bottomrule
\end{tabular}
\end{table*}
'''
    write(OUT/'profile_success_table.tex',table)
    methods=r'''\emph{Outcome-independent behavioral profiles:}
All drivers, including those who abandoned parking, receive
the same standardized decision probes. The implemented decision
rules evaluate tradeoffs involving walking, approach time,
exit distance, availability, and eligibility at three search
durations. Expected probabilities of choosing each candidate
or continuing form a response signature, without using actual
parking success, realized search duration, or final space choice.
Driver constraints are retained. We fit candidate groups using
20 training populations and assess their repeatability on ten
held-out populations. Profile membership is fixed before
comparing information conditions. Success and elapsed search
include all arrivals; walking and combined search--walking
effects use drivers parked in both matched conditions.
Intervals resample whole populations and are conditional on
the learned partition. These exploratory response groups do
not establish empirical psychological personas.
'''
    write(OUT/'methods_insertion.tex',methods)
    figure=r'''\begin{figure}[!t]
\centering
\includegraphics[width=\columnwidth]{figures/stochastic_profile_success_column.pdf}
\caption{Parking success by candidate stochastic response profile at 95\% occupancy.}
\label{fig:all_driver_profile_success}
\end{figure}
'''
    write(OUT/'profile_figure.tex',figure)
    descriptions=traits[['model','profile','heldout_drivers','walking_limited_pct','accessible_eligible_pct','mean_walk_weight','bootstrap_jaccard']].copy()
    report='''# All-driver behavioral response profiles

This analysis answers who parks and who benefits from information without defining profiles by those outcomes. It replaces the successful-driver-only analysis for this question; its numbers are not pooled with that earlier analysis.

## What was analysed

- **2,400 distinct generated drivers** from 30 populations of 80. No driver was excluded for failure, mobility limitation, accessible-space eligibility or permits.
- **64,800 outcome records from 810 existing trials**: three main decision models, three occupancies, three information conditions, 30 matched replications. Repeated records are scenarios for the same drivers, not independent people.
- Discovery uses 20 populations (1,600 drivers); primary outcome assessment uses ten held-out populations (800 drivers; 21,600 scenario records). All-30-population descriptive estimates are supplied separately. They do not replace the original full-sample estimates in the manuscript.
- No full ABM simulations were rerun. New decision-probe evaluations use the unchanged, archive-verified decision mechanisms.

## How profiles were discovered

Each driver encounters four fixed three-space menus at 0, 180 and 420 seconds of hypothetical elapsed search. Menus vary walking/exit tradeoffs, approach time, availability, and restricted-space opportunities. Actual walking caps, eligibility, permits, references and decision parameters are retained. Candidate availability uses the same baseline hazard. For M1, probabilities rejected after sampling are allocated to continued search; random sampled choices do not create artificial profile variation.

The 48 probabilities are square-root embedded and reduced by training-only PCA (95% variance, at most six dimensions). Gaussian mixtures with one to six components are selected by training BIC. Twenty whole-population bootstrap refits use one-to-one Jaccard matching. Held-out density improvement, minimum 5% group size in training and validation, minimum mean Jaccard 0.75, and posterior confidence are checked. These are exploratory density/response partitions, not a test proving discrete human personality types.

Group numbers are ordered by TRAINING continuation propensity. P1 in one model is not the same population as P1 in another model. Labels are fixed across occupancy/information by construction, which enables matching but does not establish longitudinal psychological stability.

## Validation results

'''
    for d in diagnostics:
        report+=f"- **{NAMES[d['model']]}:** {d['components']} candidate groups; complete partition passes all checks: **{d['supported']}**. Minimum group bootstrap Jaccard {d['min_bootstrap_jaccard']:.3f}; minimum held-out mass {100*d['min_validation_mass']:.2f}%. Membership agreement after 10% walking/approach probe perturbation: {d['perturbed_heldout_ari']:.3f}; after neutralizing walking caps and restricted-space candidates: {d['neutral_heldout_ari']:.3f}. Reference expectations remain unchanged in the neutral diagnostic.\n"
    report+='''
**No complete partition met every prespecified check.** Some individual components are reproducible, especially under stochastic utility, but small groups and unstable components prevent a claim of one validated six-persona taxonomy. `component_repeatability_summary.csv` separates individual size/repeatability checks from validation of an entire partition. All three BIC fits reached the six-component limit; six is not an established number of driver types. The secondary training-only complexity diagnostic is reported separately and never replaces the primary assignments or chooses groups using success.

Plain-language descriptions in `posthoc_profile_descriptions.csv` were written AFTER fitting from observed response probabilities and attributes. Examples include door-oriented responses, availability-oriented responses, and eligibility-linked responses. They are interpretations of fitted components, not labels used to generate drivers. More late-search rejection under a fixed aspiration threshold is a model response, not evidence of psychological impatience in observed people.

Constraint neutralization is a mechanistic sensitivity test, not an independent causal experiment about real drivers. The considerable membership changes show that the candidate groups depend on constraint-related responses; they cannot all be interpreted as preference-only personalities.

## Candidate profiles and held-out outcomes

The table below describes groups after discovery, without assigning labels such as cost-sensitive or risk-averse. An eligibility-linked group is not evidence that its members psychologically seek accessibility. Price and enforcement do not vary in these free, legal-parking experiments.

'''+markdown_table(descriptions.round(3))+'''

![Response signatures](figures/response_profile_signatures.png)

![Parking success](figures/success_by_response_profile.png)

![Matched information benefits](figures/information_benefits_by_response_profile.png)

## Illustrative held-out comparison

'''
    r=pick(success,model='rum',profile=2)
    benefit=pick(effects,split='heldout',model='rum',occupancy=.95,information='space',profile=2,metric='success_pp')
    search=pick(effects,split='heldout',model='rum',occupancy=.95,information='space',profile=2,metric='search_s')
    t=pick(traits,model='rum',profile=2)
    report+=f"The stochastic-utility P2 response group contains {int(t.heldout_drivers)} held-out drivers; {t.accessible_eligible_pct:.1f}% are eligible for accessible spaces. Its bootstrap Jaccard is {t.bootstrap_jaccard:.3f}. At 95% occupancy, mean replication success is {r.unaided_success_pct:.2f}% unaided, {r.aisle_success_pct:.2f}% with aisle information, and {r.space_success_pct:.2f}% with space information. The paired space-information change is **{interval(benefit,2)} percentage points**; the search change is **{interval(search,2)} seconds**. This is an illustrative exploratory comparison, not a prespecified confirmatory subgroup finding.\n"
    report+='''
Other groups can show smaller, uncertain or opposite point estimates. All groups and intervals are supplied, including small groups and zero/inconclusive effects. A clear interval for one group and an unclear interval for another is not itself a test that the effects differ: `profile_information_interactions.csv` supplies direct paired differences from the overall effect.

## Statistical interpretation

- Success percentages first average within each population and profile, then across populations. They need not equal pooled successes divided by the displayed total driver count. Seeds with no members of a small group are absent; every interval states its contributing seed count.
- Success and mean elapsed search include unsuccessful drivers. Parking failure is a measured outcome, never a clustering feature or an exclusion.
- Walking, exit distance and search-plus-walking comparisons use the SAME drivers parked in both conditions. These describe that selected successful cohort; they are not total-access estimates for abandoned arrivals. One-way and round-trip walking are separate metrics, using 1.4 m/s.
- Pointwise 95% percentile intervals use 10,000 resamples of matched populations, without multiplicity correction. Drivers interacting within a trial are not independent observations. Intervals condition on the fitted labels; partition uncertainty is assessed separately through refits.
- Information effects compare facility-wide information conditions. They combine a driver's own information access with competition and spillovers from other informed drivers; they do not isolate individual adoption while holding everyone else's access fixed.
- The whole-partition validation failure and upper-bound selection must remain attached to any use of these candidate-profile outcomes. Individual repeatable components do not establish a complete discrete persona taxonomy.
- These are responses of assumed simulated drivers. The analysis does not validate real-world psychological categories, prediction accuracy or an operational digital twin.

## Reproduction and files

Run `scripts/analyze_all_driver_profiles.py` in a repository checkout using the analysis dependencies. Its design and source/input hashes were written before probe fitting; the secondary complexity diagnostic has a separate declared plan. `scripts/report_all_driver_profiles.py` builds these figures and tables. Five targeted tests in `tests/test_response_profiles.py` check rejected-choice probability, inclusion of constrained drivers, deterministic response extraction, a one-group result, and protection of training selection from validation inputs.

`data/` contains all profile assignments, all-arrival records, all occupancy/information outcome summaries, direct effect contrasts, validation diagnostics and probe features. `source/` contains the analysis code; source decision-module hashes are checked against the final simulation archive. Original simulation logic, populations, and raw outcomes are unchanged.
'''
    write(OUT/'REPORT.md',report);write(DATA/'REPORT.md',report)
    insertion=r'''\emph{Behavioral response profiles:}
Outcome-independent decision probes included every driver,
including unsuccessful arrivals and drivers with constraints.
The learned groups showed different parking-success and
information-effect estimates. However, no complete partition
passed all size and repeatability checks, and the selected
component counts reached the search limit. The groups are
therefore exploratory descriptions of simulated responses,
not an established set of driver personas. For stochastic
utility, one repeatable eligibility-linked group had mean
success of '''+f'{r.unaided_success_pct:.1f}'+r'''\% unaided and
'''+f'{r.space_success_pct:.1f}'+r'''\% with space information at 95\% occupancy.
Full group estimates and validation diagnostics are reported
in the supplementary analysis.
'''
    write(OUT/'results_insertion.tex',insertion)
    for name in ['methods_insertion','results_insertion','profile_success_table','profile_figure']:
        shutil.copy2(OUT/f'{name}.tex',OUT/f'{name}.txt')
    dest=OUT/'data';dest.mkdir(exist_ok=True)
    names=['design.json','verification.json','all_driver_profile_assignments.csv','all_arrivals_with_profiles.csv.gz',
        'profile_outcomes.csv','information_effects.csv','information_effects_by_seed.csv','profile_cells_by_seed.csv',
        'profile_information_interactions.csv','complexity_sensitivity.csv','complexity_sensitivity_design.json','all_driver_audit.json']
    names += [f'{m}_{suffix}' for m in MODELS for suffix in ['diagnostics.json','selection.csv','response_features.npz','driver_inputs.csv']]
    for name in names:
        if (DATA/name).exists():shutil.copy2(DATA/name,dest/name)
    source=OUT/'source';source.mkdir(exist_ok=True)
    for p in [ROOT/'scripts/analyze_all_driver_profiles.py',Path(__file__),ROOT/'scripts/check_response_profile_complexity.py',ROOT/'scripts/verify_all_driver_profiles.py',ROOT/'panda_abm/analysis/response_profiles.py',ROOT/'tests/test_response_profiles.py']:
        shutil.copy2(p,source/p.name)
    write(OUT/'requirements.txt','\n'.join(f'{k}=={v}' for k,v in design['packages'].items())+f'\nmatplotlib=={matplotlib.__version__}\n')
    manifest={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='manifest.json'}
    write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    archive=OUT.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(OUT.parent).as_posix())
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    print('All-driver profile report, four vector figures, tables and ZIP created.')
    print('Complete validated partitions:',sum(d['supported'] for d in diagnostics),'of 3.')

def pick_frame(df,**values):
    for k,v in values.items():df=df[np.isclose(df[k],v)] if isinstance(v,float) else df[df[k]==v]
    return df

if __name__=='__main__':main()
