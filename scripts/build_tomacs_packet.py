"""Organize verified existing evidence for writing; no simulation is launched."""
from pathlib import Path
import hashlib
import json
import math
import platform
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/tomacs'
SOURCE=ROOT/'results/parking_information_20261028'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def table(name,frame,caption):
    folder=OUT/'tables';folder.mkdir(exist_ok=True)
    frame.to_csv(folder/(name+'.csv'),index=False)
    lines=['# '+name.replace('_',' ').capitalize(),'',caption,'',
           '| '+' | '.join(frame.columns)+' |','|'+'|'.join('---' for _ in frame.columns)+'|']
    for row in frame.itertuples(index=False,name=None):
        cells=['—' if pd.isna(v) else f'{v:.3f}' if isinstance(v,(float,np.floating)) else str(v) for v in row]
        lines.append('| '+' | '.join(cells)+' |')
    (folder/(name+'.md')).write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    names=['design.json','runs.csv','drivers.csv','contrasts.csv','individual_choices.csv','target_competition.csv','checks.json']
    manifest=json.loads((SOURCE/'bundle_manifest.json').read_text())
    for name in names:
        if sha(SOURCE/name)!=manifest[name]:raise ValueError(f'Archive input mismatch: {name}')
    r=pd.read_csv(SOURCE/'runs.csv');d=pd.read_csv(SOURCE/'drivers.csv')
    c=pd.read_csv(SOURCE/'contrasts.csv');choices=pd.read_csv(SOURCE/'individual_choices.csv')
    competition=pd.read_csv(SOURCE/'target_competition.csv')
    plan=json.loads((SOURCE/'design.json').read_text())
    checks=pd.DataFrame(json.loads((SOURCE/'checks.json').read_text()))
    assert len(r)==270 and len(d)==21600 and len(checks)==270
    assert not r.duplicated(['seed','occupancy','model','information']).any()
    flags=['exclusive_claims','balanced_release','terminal','finite','elapsed_identity','bounded_search','legal','walking_limits','local_stall_targets']
    assert checks[flags].all().all()
    assert d.loc[~d.success,'walk_m'].isna().all()
    summary=r.groupby(['occupancy','model','information']).agg(seeds=('seed','nunique'),arrivals=('drivers','sum'),parked=('parked','sum'),
        success_pct=('success',lambda x:100*x.mean()),search_all_s=('mean_search_s','mean'),search_parked_s=('mean_search_parked_s','mean'),
        walk_parked_m=('mean_walk_parked_m','mean'),exit_parked_m=('mean_exit_parked_m','mean'),search_distance_m=('mean_search_distance_m','mean'),
        failed_claims=('lost_claims','sum')).reset_index()
    table('current_outcomes',summary,'Exploratory pilot: ten independent seeds and 800 arrivals per cell. Means were equal-weight seed means. Walking and intended-exit proximity included parked drivers only. Exit proximity was straight-line distance; source tables retained unrounded values.')
    selected=c[c.comparison.isin(['aisle_vs_unaided','space_vs_unaided'])].copy()
    selected=selected[selected.metric.isin(['mean_search_s','success','mean_walk_parked_m','mean_exit_parked_m'])]
    success=selected.metric=='success'
    selected.loc[success,['delta','ci_low','ci_high']]*=100
    selected['unit']=np.where(success,'percentage points',np.where(selected.metric=='mean_search_s','seconds','metres'))
    table('paired_information_effects',selected[['occupancy','model','comparison','metric','unit','seeds','delta','ci_low','ci_high']],
          'Intervention minus unaided, with original 95% paired-seed bootstrap intervals. These were exploratory pointwise intervals, not multiplicity-adjusted confirmatory tests. Walking/exit effects conditioned on each arm parking.')
    table('individual_choice_changes',choices,'Matched-driver descriptive comparisons. Same-space/aisle fractions and walking changes were restricted to jointly parked drivers; success switches used the complete matched cohort. No independent-driver confidence intervals were computed.')
    comp=competition.groupby(['occupancy','model','information']).agg(target_selections=('target_selections','sum'),already_pursued=('selections_already_pursued','sum'),peak_targeters=('peak_concurrent_targeters','max')).reset_index()
    comp['pooled_already_pursued_fraction']=comp.already_pursued/comp.target_selections
    comp=comp.merge(summary[['occupancy','model','information','arrivals','failed_claims']],on=['occupancy','model','information'])
    comp['failed_claims_per_arrival']=comp.failed_claims/comp.arrivals
    table('claim_competition',comp,'Event counts included repeated events by a driver. The overlap fraction here pooled selections across runs; it differed in estimand from the equal-weight within-seed fraction plotted in the expanded gallery. These were target conflicts, not road queues.')
    for group,metric,name in [('intended_exit','exit_distance_m','intended_exit_distance'),('door','walk_m','destination_walking')]:
        seed=d[d.success].groupby(['seed','occupancy','model','information',group])[metric].agg(['mean','size']).reset_index()
        frame=seed.groupby(['occupancy','model','information',group]).agg(mean_m=('mean','mean'),contributing_seeds=('mean','count'),parked=('size','sum')).reset_index()
        table(name,frame,'Mean of within-seed distances among parked drivers, with contributing seed and driver counts. Straight-line distances; subgroup cohorts differed across conditions. No direct exit-choice or departure-time effect was estimated.')
    mobility=d.groupby(['seed','occupancy','model','information','mobility_limited']).agg(arrivals=('success','size'),success=('success','mean'),search_s=('search_s','mean')).reset_index()
    mobility=mobility.groupby(['occupancy','model','information','mobility_limited']).agg(arrivals=('arrivals','sum'),success_pct=('success',lambda x:100*x.mean()),search_s=('search_s','mean'),seeds=('seed','nunique')).reset_index()
    table('mobility_outcomes',mobility,'Exploratory walking-constraint subgroup seed means. Physical mobility constraints were distinct from accessible-space eligibility. Small subgroups did not provide independent confirmatory evidence.')
    precision=[]
    for (occ,model),frame in r.groupby(['occupancy','model']):
        for mode in ['aisle','space']:
            paired=frame[frame.information==mode].merge(frame[frame.information=='unaided'],on='seed',suffixes=('_i','_u'),validate='one_to_one')
            for metric,h in [('mean_search_s',3.),('success',.01)]:
                delta=paired[metric+'_i']-paired[metric+'_u'];sd=float(delta.std(ddof=1))
                precision.append(dict(occupancy=occ,model=model,comparison=mode+'_vs_unaided',metric=metric,
                                      pilot_seeds=len(delta),paired_sd=sd,target_half_width=h,
                                      normal_planning_n=math.ceil((1.96*sd/h)**2),
                                      n_for_2s_search=math.ceil((1.96*sd/2)**2) if metric=='mean_search_s' else None,
                                      note='Observed zero variance; no universal-success inference' if sd==0 else 'Pilot planning diagnostic'))
    table('pilot_precision',pd.DataFrame(precision),'Approximate pointwise planning n=(1.96*s/h)^2, rounded upward, from ten paired seed differences. Targets were 3 seconds for search and 0.01 success fraction (one percentage point). This was not a power calculation, a simultaneous-interval calculation or a precision guarantee. Zero-variance pilot cells did not imply n=0 was adequate.')
    assert max(p['normal_planning_n'] for p in precision)==29
    settings=[('Facility','1,315 slot records; 209 blocked; 1,106 unblocked','Estimated geometry, not surveyed capacity'),
              ('Accessible records','34','Eligibility and mobility constraints were distinct'),
              ('Modules','17 (A–Q); side groups O–Q contained 70 records','Main groups A–N contained 1,245 records'),
              ('Occupancy','0.40 / 0.80 / 0.95 of unblocked records','Initial occupancy was uniformly sampled; background cars did not depart'),
              ('Initial occupied counts','442 / 885 / 1,051','Per-case draws were shared across all nine policy/information arms'),
              ('Population','80 arrivals per run','Continuous structural priors; no local behavioral calibration'),
              ('Arrival schedule','Every 20 seconds','Intended exit matched arrival access in the primary generator'),
              ('Dwell','Discrete uniform 900–3,599 seconds','Simulated drivers released their stalls'),
              ('Physical step / decisions / output','1 s / 10 s / 10 s','Output batching was independent of physical stepping'),
              ('Speed / walking speed','5 m/s / 1.4 m/s','No car-following, traffic queues or pedestrian interactions'),
              ('Search deadline / maneuver','600 s / 2 s','Deadline check preceded a claim at that instant'),
              ('Local visibility','60 m perfect radial visibility','No occlusion or local sensor errors'),
              ('Remote information','Perfect current reports at decision times','Not forecasts, reservations or continuously rerouted targets'),
              ('Claim belief hazard','0.002 per second','Assumed survival belief, not an independent random physical claim failure'),
              ('Acceptance threshold','1.75','A structural assumption on the utility scale'),
              ('Replication','Seeds 1000–1009; 270 runs; 21,600 outcomes','Interacting drivers were not independent replications')]
    table('implemented_settings',pd.DataFrame(settings,columns=['item','value','interpretation']),'Methods table for the existing information pilot. Distinguish these fixed settings from proposed future factors.')
    # Proposed run counts remain machine-readable and are never labelled completed.
    stages=[dict(id='E0',unit='decision evaluations',factors=[243,200,8],count=388800,status='proposed; oracle/panel implementation required'),
            dict(id='E1',unit='full model executions',factors=[3,3,3,20],count=540,status='proposed; existing runner supported'),
            dict(id='E2a',unit='full model executions',factors=[2,3,30],count=180,status='proposed; linear-prospect control required'),
            dict(id='E2b',unit='full model executions',factors=[3,3,30],count=270,status='proposed; simple policy required'),
            dict(id='E3a',unit='full model executions',factors=[2,4,3,10],count=240,status='proposed; background turnover required'),
            dict(id='E3b',unit='full model executions',factors=[2,4,2,10],count=160,status='proposed; delayed reports required'),
            dict(id='E4',unit='full model executions',factors=[2,4,3,30],count=720,status='proposed; second layout required'),
            dict(id='E5',unit='full model executions',factors=[2,5,3,10],count=300,status='proposed; combined runner required'),
            dict(id='E6',unit='full model executions',factors=[3,3,5,2,2],count=180,status='proposed; 90 execution-equivalence pairs')]
    specifications={
        'E0':dict(opportunity_settings=243,driver_vectors=200,transform_switches=8),
        'E1':dict(occupancies=[.4,.8,.95],policies=['deterministic','rum','cpt'],information=['unaided','aisle','space'],seeds=list(range(1010,1030))),
        'E2a':dict(occupancies=[.8,.95],policies=['linear_prospect_same_adapter'],information=['unaided','aisle','space'],seeds=list(range(1000,1030))),
        'E2b':dict(occupancies=[.4,.8,.95],policies=['first_local_then_nearest_reported'],information=['unaided','aisle','space'],seeds=list(range(1000,1030))),
        'E3a':dict(occupancies=[.8,.95],policies=['deterministic','rum','cpt','simple'],information=['unaided','aisle','space'],seeds=list(range(1000,1010)),background_residual_median_s=1800),
        'E3b':dict(occupancies=[.8,.95],policies=['deterministic','rum','cpt','simple'],information=['aisle','space'],seeds=list(range(1000,1010)),remote_report_delay_s=30),
        'E4':dict(layout='second_synthetic_layout_not_yet_implemented',usable_spaces=1106,occupancies=[.8,.95],policies=['deterministic','rum','cpt','simple'],information=['unaided','aisle','space'],seeds=list(range(1000,1030))),
        'E5':dict(integration_seconds=[.5,.25],occupancies=[.95],policies=['deterministic','rum','cpt','simple','linear_prospect_same_adapter'],information=['unaided','aisle','space'],seeds=list(range(1000,1010)),decision_interval_s=10),
        'E6':dict(occupancy=.8,policies=['deterministic','rum','cpt'],information=['unaided','aisle','space'],seeds=list(range(4000,4005)),population_sizes=[8,80],execution_modes=['recorded','live'])}
    for stage in stages:stage['specification']=specifications[stage['id']]
    assert all(math.prod(s['factors'])==s['count'] for s in stages)
    total=sum(s['count'] for s in stages if s['unit']=='full model executions');assert total==2590
    (OUT/'experiment_manifest.json').write_text(json.dumps(dict(status='proposed_not_executed',prepared='2026-10-28',reuse_existing_runs=270,
        new_executions_reuse_first=total,independent_core_alternative_new_executions=total+270,
        core_extension_seeds=list(range(1010,1030)),independent_core_alternative_seeds=list(range(3000,3030)),
        shared_control_reuse='Only with exact source/settings/population/RNG/initial-occupancy compatibility',stages=stages),indent=2)+'\n')
    refs=json.loads((OUT/'literature_sources.json').read_text())
    bib=[]
    for ref in refs:
        kind='misc' if 'preprint' in ref['venue'].lower() else 'inproceedings' if 'Conference' in ref['venue'] else 'article'
        venue_key='journal' if kind=='article' else 'booktitle' if kind=='inproceedings' else 'note'
        fields=dict(author=ref['authors'],title='{'+ref['title']+'}',year=str(ref['year']))
        fields[venue_key]=ref['venue'];fields['url']=ref['url']
        if ref.get('doi'):fields['doi']=ref['doi']
        bib.append('@'+kind+'{'+ref['id']+',\n'+''.join('  '+k+' = {'+v+'},\n' for k,v in fields.items())+'}\n')
    (OUT/'references.bib').write_text('\n'.join(bib),encoding='utf-8')
    ledger=[('Information pilot','270 matched runs / 21,600 outcomes','results/parking_information_20261028','Primary exploratory results; no field calibration'),
            ('Publication audit','468 verification/sensitivity runs plus 15 claim-belief diagnostic runs','results/publication_audit_20261027','Separate designs/source versions; do not pool as extra information-study replications'),
            ('Continuous-population/profile study','Existing archived study','results/continuous_population_20261027','Methods background and supplementary diagnostics; no proof of discrete human classes'),
            ('Early persona studies','Historical controlled perturbations','results/persona_cpt_20261027','Exclude from primary continuous-population evidence'),
            ('Cesium/live adapter','169 tests passed in the preceding implementation turn; one archived 80-driver signature matched','dashboard/README.md','Software evidence, not field validity or a completed visual/performance evaluation')]
    table('evidence_ledger',pd.DataFrame(ledger,columns=['evidence','extent','location','permitted_use']),'Study counts had different purposes and overlapping scenarios. They were not independent pooled samples or a publication-readiness score.')
    provenance=dict(prepared='2026-10-28',script_sha256=sha(Path(__file__)),python=platform.python_version(),
                    source_inputs={n:sha(SOURCE/n) for n in names},source_manifest_sha256=sha(SOURCE/'bundle_manifest.json'),
                    source_archive_sha256=sha(SOURCE/'reproducibility_bundle.zip'),
                    source_directory=SOURCE.relative_to(ROOT).as_posix(),
                    generated_tables={p.relative_to(OUT).as_posix():sha(p) for p in sorted((OUT/'tables').iterdir()) if p.is_file()},
                    note='Existing evidence reorganized; no new simulations, source-archive edits or field validation. Proposed counts are not results.')
    (OUT/'table_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(f'Organized {len(list((OUT/"tables").glob("*.md")))} tables and {len(refs)} references; proposed new executions: {total}; executed: 0')


if __name__=='__main__':main()
