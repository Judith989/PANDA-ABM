"""Integrate the all-arrival analysis into the user's authoritative pasted draft.

Preserves the supplied manuscript outside explicit result/method consistency edits.
Refuses to overwrite subsequent manual edits of the generated main source.
"""
from pathlib import Path
import hashlib,json,re,shutil,zipfile
import pandas as pd
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
ATTACHMENT=Path('C:/Users/jnjoku/.codex/attachments/0c430ae3-1c03-41e2-8ca6-9854136caadc/Pasted text.txt')
PROJECT=ROOT/'paper/current_manuscript'
FRAGMENTS=ROOT/'paper/results_section'
ANALYSIS=ROOT/'paper/all_driver_profiles_20261102'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,s):Path(p).write_text(s,encoding='utf-8')
def copy_evidence_tree(source,destination):
    """Do not rewrite immutable evidence that may be mapped by the desktop viewer."""
    destination.mkdir(parents=True,exist_ok=True)
    for item in source.rglob('*'):
        if not item.is_file():continue
        target=destination/item.relative_to(source)
        if target.exists() and sha(item)==sha(target):continue
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(item,target)
def replace_between(s,start,end,replacement):
    a=s.index(start);b=s.index(end,a);return s[:a]+replacement+'\n\n'+s[b:]
def section(s,start,end):return s[s.index(start):s.index(end,s.index(start))].strip()+'\n'

def main():
    PROJECT.mkdir(exist_ok=True,parents=True)
    provenance=PROJECT/'revision_provenance.json'
    if provenance.exists():
        old=json.loads(provenance.read_text())
        assert sha(PROJECT/'main.tex')==old['main_sha256'],'Manual manuscript edits detected; refusing to overwrite them.'
    original=ATTACHMENT.read_text(encoding='utf-8');s=original
    write(PROJECT/'original_supplied_draft.txt',original)
    # Brief, consistent description in the population-generator subsection.
    behavior=r'''\emph{Behavioral variation:}
Different parking responses arise as driver attributes interact
with the decision rules, available spaces, and competition.
For analysis, profiles are derived from responses to
standardized parking choices, without using actual parking
success or final search outcomes. These descriptive labels do
not set driver preferences or decision rules. Parking success
and information benefits are then compared across the learned
groups, including drivers who did not park.'''
    s=replace_between(s,r'\emph{Behavioral variation:}',r'\subsection{Behavioral Decision Layer}',behavior)
    method=r'''\emph{Behavioral response profiles:}
The analysis includes all 2,400 drivers and 64,800 outcome
records from the 810 core trials. No driver is excluded for
unsuccessful parking, walking limits, eligibility, or permits.
Each implemented decision model evaluates four standardized
three-space menus at hypothetical search durations of 0, 180,
and 420~s. Menus vary walking, exit distance, approach time,
availability, and restricted-space opportunities. Driver
constraints remain active. Expected probabilities of choosing
each space or continuing form 48 response features; actual
parking outcomes are not features.

Training-only dimension reduction precedes Gaussian-mixture
selection with one to six components. Twenty populations
(1,600 drivers; seeds 1000--1019) are used for fitting and ten
(800 drivers; seeds 1020--1029) for held-out assessment.
Models are fitted separately, and
membership is fixed across occupancy and information conditions.
Checks assess group size, held-out response prediction,
assignment confidence, and stability across 20 population
bootstrap refits. The supplementary analysis gives thresholds,
probe specifications, and sensitivity checks.

Primary profile comparisons use the 21,600 held-out outcome
records; all-30-population descriptions are supplied separately.
These are subsets of the existing experiments, so the total
remains 3,400 trials. Profile intervals condition on the learned
groups. Information effects compare facility-wide conditions,
including competition and spillovers, rather than isolated
changes in one driver's information access.'''
    s=replace_between(s,r'\emph{Behavioral-profile analysis:}','Information effects are',method)
    metric=r'''\emph{Search-and-walking time} combines search duration with
one-way walking time, $T_i+d_i^w/v_w$, using $v_w=1.4$~m/s.
Matched comparisons use drivers parked in both conditions;
the supplementary analysis also reports the return walk.
Search duration among parked and abandoned drivers is
reported separately to distinguish success from elapsed time.

'''
    anchor=r'\emph{Choice agreement}';assert anchor in s;s=s.replace(anchor,metric+anchor,1)
    source=pd.read_csv(ANALYSIS/'parking_success_95_by_profile.csv')
    names={1:'Mixed choice',2:'Eligibility-linked',3:'Permit-linked',4:'Late-search rejection',5:'Limited nearby choices',6:'Mixed nearby choices'}
    rows=[]
    for r in source[source.model=='rum'].sort_values('profile').itertuples():
        rows.append(f'P{r.profile}: {names[r.profile]} & {r.heldout_drivers} & {r.unaided_success_pct:.1f} & {r.aisle_success_pct:.1f} & {r.space_success_pct:.1f}'+r' \\')
    table=r'''\begin{table}[!t]
\caption{Candidate stochastic response profiles at 95\% occupancy.}
\label{profile_groups}
\centering\small
\setlength{\tabcolsep}{3pt}
\begin{tabular}{@{}lrrrr@{}}
\toprule
Profile & Drivers & \multicolumn{3}{c}{Success (\%)}\\
\cmidrule(l){3-5}
 & & Unaided & Aisle & Space\\
\midrule
'''+ '\n'.join(rows)+r'''
\bottomrule
\end{tabular}
\end{table}'''
    profile=r'''\emph{Behavioral response profiles:}
The all-driver analysis related outcome-independent response
groups to parking success, as shown in Fig.~\ref{profile_evidence_fig}.
Unlike grouping successful drivers by their final search and
walking outcomes, this comparison retains unsuccessful arrivals.
Success is illustrated at 95\% occupancy because all drivers
parked at 40\% and 80\%; complete profile outcomes are supplied
in the supplementary analysis.
The selected mixtures reached six components for each model,
but no complete partition passed every size and repeatability
check. Several individual components were repeatable; small
groups, unstable components, and sensitivity to the component
limit prevented identification of a fixed persona taxonomy.
Group numbers are specific to each decision model.

\begin{figure*}[!t]
\centering
\includegraphics[width=\textwidth]{img/column_profile_success_all_models.pdf}
\caption{Parking success by candidate response profile at 95\% occupancy.}
\label{profile_evidence_fig}
\end{figure*}

The stochastic groups illustrate the observed patterns in
Table~\ref{profile_groups}. They include mixed choices,
eligibility-linked responses, permit-linked responses,
greater late-search rejection, and two walking-limit-dominated
patterns with different feasible choices. These descriptions
were assigned after fitting; they did not determine driver
generation or decisions.

The eligibility-linked stochastic group contained 75 held-out
drivers, all eligible for accessible spaces. Its mean
replication-level success increased from 84.1\% unaided to
94.3\% with space information: a paired change of
$+10.15$ percentage points $[0.79,19.73]$.
This information effect exceeded the overall effect for the
same held-out populations by 9.90 percentage points
$[0.79,19.73]$, using a direct paired comparison.
The group's bootstrap membership agreement was 0.999.

'''+table+r'''

Other response groups had uncertain or opposite point estimates.
For example, the CPT group with greater walking emphasis
had success of 82.1\% unaided and 77.6\% with space information;
its change of $-4.45$ percentage points $[-8.42,0.30]$
did not establish a reduction. Small walking-limited and
permit-linked groups had wider intervals. Table percentages
average population-level rates; they are not pooled fractions
of the displayed driver counts. These held-out estimates use
ten populations, while the main experiment summaries use 30.

These findings address RQ1 by showing that driver variation
and access constraints affected parking outcomes and the
distribution of information benefits. The response profiles
provide conditional comparisons, without establishing discrete
psychological personas. Complete group estimates and diagnostics
are supplied in the supplementary analysis.'''
    s=replace_between(s,r'\emph{Behavioral profiles:}',r'\subsection{Decision models',profile)
    # Additional metrics are calculated from the same saved matched records.
    access=r'''Longer search did not necessarily increase combined
search-and-walking time. At 80\% occupancy, space information
reduced this measure by 21.82~s under deterministic utility,
1.61~s under stochastic utility, and 8.53~s under CPT.
The CPT interval was $[-9.59,-7.44]$~s. All drivers parked in
both conditions at this occupancy. The separate outcomes also
retain differences in walking effort, exit proximity, and competition.

'''
    anchor='The heatmaps show mean changes;';assert anchor in s;s=s.replace(anchor,access+anchor,1)
    duration=r'''Abandonment contributes to the all-arrival search mean:
drivers who did not park reached the 600-s deadline.
For CPT at 95\% occupancy, space information also reduced
search among the same drivers parked in both conditions by
8.39~s $[-12.05,-4.50]$. The search reduction therefore
remained present within this jointly successful cohort;
it was not solely a consequence of more drivers parking.

'''
    anchor='Fig.~\\ref{10}' # Use the existing semantic label, not a figure number.
    anchor=r'Fig.~\ref{search_distribution_fig} shows'
    assert anchor in s;s=s.replace(anchor,duration+anchor,1)
    old='Profile screening identified contextual outcome groups, but did\nnot validate permanent driver types.'
    new='Response profiling retained every driver, but did not validate a\ncomplete set of permanent driver types. Candidate groups depended\non decision rules, access constraints, and the standardized probes.'
    assert old in s;s=s.replace(old,new,1)
    conclusion=r'''The all-driver response analysis further showed that information
benefits could differ between candidate groups. Several patterns
were repeatable, but the complete groupings did not establish
a stable persona taxonomy. Profiles therefore describe simulated
responses under the tested rules and conditions.

'''
    anchor='These findings support utilizing parking digital';assert anchor in s;s=s.replace(anchor,conclusion+anchor,1)
    abstract=r'''Parking information changes what drivers know and how they
search and compete for shared spaces. We developed an agent-based
framework for examining these interactions within parking digital
twins. It integrates geospatial parking geometry, heterogeneous
driver preferences and constraints, alternative decision mechanisms,
information services, and shared occupancy. Deterministic utility,
stochastic utility, and cumulative prospect theory (CPT) were
evaluated alongside linear-CPT and simple-search controls.
Matched experiments examined unaided search, aisle-level
information, and space-level information across occupancy,
adoption, and operating conditions. The programme comprised
3,400 trials using an estimated Walmart layout and a synthetic
transfer layout. For CPT at 80\% occupancy, space information
increased mean search by 8.43~s and reduced walking by 23.75~m,
giving an 8.53-s reduction in combined search-and-walking time.
At 95\%, it reduced search by 8.34~s and increased parking
success by 0.92 percentage points alongside greater competition.
Outcome-independent profiling retained unsuccessful drivers and
identified candidate response groups with unequal information
benefits, without establishing a stable persona taxonomy.
Mixed adoption affected uninformed drivers, while departures
and layout changes altered estimated information benefits.
The findings support evaluating parking information through
multiple outcomes and explicit behavioral assumptions.
The framework provides a simulation component for parking
digital twins; empirical calibration and continuous physical-state
updates remain future work.'''
    s=replace_between(s,r'\begin{abstract}',r'\end{abstract}',r'\begin{abstract}'+'\n'+abstract+'\n')
    assert 100<=len(abstract.split())<=250,len(abstract.split())
    s=s.replace('under matched simulation conditions.','under matched simulation conditions. Outcome-independent\n    response profiling retains unsuccessful drivers in these comparisons.',1)
    for i in range(1,5):s=s.replace(f'RQ{i}:-',f'RQ{i}:')
    s=s.replace('The rest of the manuscript is organized as follows:',r'''Section~\ref{framewk} presents the framework.
Section~\ref{exp} describes the experimental design, and
Section~\ref{results} discusses the findings.
Section~\ref{conclusion} concludes the study.''',1)
    s=re.sub(r'\\section\{Conclusion\}(?!\s*\\label\{conclusion\})',lambda m:m.group()+r'\label{conclusion}',s,count=1)
    # Remove false template production metadata, keeping supplied author names and biography.
    s=re.sub(r'\\thanks\{This paper was produced by the IEEE Publication Technology Group\.[^}]*\}', '',s)
    s=re.sub(r'\\thanks\{Manuscript received April 19, 2021; revised August 16, 2021\.\}', '',s)
    a=s.index('% The paper headers');b=s.index('% \\IEEEpubid',a)
    s=s[:a]+r'\markboth{Draft manuscript}{Agent-Based Parking Framework}'+'\n\n'+s[b:]
    s=s.replace(r'\bibliography{references.bib}',r'\bibliography{references}')
    s=s.replace('\\newpage\n\n\\section{Biography Section}','')
    # These packages have no active uses in the supplied source.
    for name in ['orcidlink','svg','algorithm','algpseudocode']:
        s=re.sub(r'(?m)^\\usepackage\{'+name+r'\}[^\n]*\n','',s)
    seen=False;lines=[]
    for line in s.splitlines():
        if line==r'\usepackage{graphicx}':
            if seen:continue
            seen=True
        lines.append(line)
    s='\n'.join(lines)+'\n'
    write(PROJECT/'main.tex',s);write(PROJECT/'updated_paper.txt',s)
    # Synchronize the existing editable section sources in place.
    pieces={
        'framework_population_profiles':section(s,r'\subsection{Driver Population Generator}',r'\subsection{Behavioral Decision Layer}'),
        'experimental_design_site':section(s,r'\section{Experimental Design}',r'\section{Results and Discussion}'),
        'results':section(s,r'\section{Results and Discussion}',r'\section{Conclusion}')}
    for name,text in pieces.items():
        write(FRAGMENTS/f'{name}.tex',text);write(FRAGMENTS/f'{name}.txt',text)
    # Reuse supplied figures and recover only the missing original author assets.
    images=PROJECT/'img';images.mkdir(exist_ok=True)
    for p in (FRAGMENTS/'img').iterdir():
        if p.is_file():shutil.copy2(p,images/p.name)
    recovered=PdfReader('C:/Users/jnjoku/Downloads/ABM_Smart_Parking (2).pdf')
    (PROJECT/'ORCIDiD_icon128x128.png').write_bytes(recovered.pages[0].images[0].data)
    (images/'sys.png').write_bytes(recovered.pages[2].images[0].data)
    (images/'judith_pic.png').write_bytes(recovered.pages[14].images[0].data)
    shutil.copy2(ANALYSIS/'figures/success_by_response_profile.pdf',images/'column_profile_success_all_models.pdf')
    for ext in ['pdf','png']:
        shutil.copy2(ANALYSIS/f'figures/success_by_response_profile.{ext}',FRAGMENTS/f'figures/column_profile_success_all_models.{ext}')
    shutil.copy2(images/'column_profile_success_all_models.pdf',FRAGMENTS/'img/column_profile_success_all_models.pdf')
    shutil.copy2(ROOT/'paper/references.bib',PROJECT/'references.bib')
    dest=PROJECT/'supplementary_profile_analysis';copy_evidence_tree(ANALYSIS,dest)
    copy_evidence_tree(ANALYSIS,FRAGMENTS/'all_driver_profile_analysis')
    record=dict(name='column_profile_success_all_models',caption=r'Parking success by candidate response profile at 95\% occupancy.',
        label='profile_evidence_fig',width_inches=7.,height_inches=2.8,columns=2)
    write(FRAGMENTS/'profile_figure_record.json',json.dumps(record,indent=2)+'\n')
    caps=json.loads((FRAGMENTS/'caption_overrides.json').read_text());caps['profile_evidence_fig']=record['caption'];write(FRAGMENTS/'caption_overrides.json',json.dumps(caps,indent=2)+'\n')
    checks=dict(original_attachment_sha256=sha(ATTACHMENT),main_sha256=sha(PROJECT/'main.tex'),
        profile_analysis_design_sha256=sha(ROOT/'research/tcss/all_driver_profiles_20261102/design.json'),
        full_simulation_trials=3400,profile_trials=810,profile_records=64800,unique_profile_drivers=2400,
        training_drivers=1600,heldout_drivers=800,heldout_records=21600,new_abm_simulations=0,
        abstract_words=len(abstract.split()),recovered_assets='ORCID, architecture and biography photo recovered unchanged from the supplied ABM_Smart_Parking (2).pdf.',
        scope='New all-driver profiling supersedes the old successful-driver-only profile analysis. Other experiment estimates retained. Introduction/literature placeholder text and dummy coauthors retained for author completion.')
    write(provenance,json.dumps(checks,indent=2)+'\n')
    write(PROJECT/'README.md','''# Updated manuscript: all-driver response profiles

`main.tex` is the complete inline manuscript based on the latest pasted source. `updated_paper.txt` is identical for copying. Copy this folder into the manuscript editor and compile main.tex. Existing figure/equation labels and numbering are retained where possible.

The population-generator explanation, profile methods, RQ1 results, profile figure/table, abstract, discussion and conclusion now use the all-driver analysis. The former successful-driver-only group counts and table are removed. The new profile plot replaces that figure rather than adding another figure. Combined search/walking and matched-successful-driver search results are also reported from existing outputs.

The profile analysis uses 810 existing core trials (64,800 scenario records; 2,400 generated drivers), with 1,600 discovery and 800 held-out drivers. The full study remains 3,400 trials. Candidate groups are model-specific; no complete partition passed all validation checks. Full descriptions, CIs, source and reproducibility files are in supplementary_profile_analysis/.

The Introduction and Literature Review still contain the supplied placeholders. Author 2/3 remain placeholders. The architecture image was recovered from the supplied PDF and retains its unfinished lower block. These items and the final page allocation still require author completion. The source does not claim a completed operational digital twin or validated human personas.
''')
    print(f'Updated full manuscript and three existing section sources; abstract {len(abstract.split())} words.')

if __name__=='__main__':main()
