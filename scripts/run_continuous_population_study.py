"""Matched generic-driver M0/M1/M2 study with a homogeneous-preference null.

Workers run independent replications; no agent delegation or external messaging.
The manifest and source archive are saved before simulation outcomes exist.
"""
from pathlib import Path
from dataclasses import replace,asdict
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse
import gc
import hashlib
import importlib.metadata
import json
import platform
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior.factory import make_population
from panda_abm.behavior.continuous import PopulationPriors,PREFERENCE_MEANS
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.environment import load_facility_from_lot_config,generate_synthetic_facility

SCENARIOS=[('walmart_crowded',.8,80),('walmart_saturated',.95,80),('synthetic_rule_tradeoff',.35,40)]


def run_replication(job):
    scenario,occupancy,size,seed,output=job
    out=Path(output)
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json') if scenario.startswith('walmart') else generate_synthetic_facility(seed)
    illegal=scenario=='synthetic_rule_tradeoff'
    if illegal:facility=replace(facility,spaces=tuple(replace(s,price_per_hour=0. if s.accessible or s.reserved_type else 9.) for s in facility.spaces))
    populations={mode:make_population(facility,size=size,seed=seed,heterogeneous=mode=='heterogeneous') for mode in ('heterogeneous','homogeneous')}
    assert [d.attributes for d in populations['heterogeneous'].drivers]==[d.attributes for d in populations['homogeneous'].drivers]
    all_drivers=[];checks=[];runs=[];population_hashes={}
    for mode,population in populations.items():
        assert all(d.attributes.persona is None for d in population.drivers)
        serialized=json.dumps(population.as_dict(),sort_keys=True)
        population_hashes[mode]=hashlib.sha256(serialized.encode()).hexdigest()
        (out/'populations'/f'{scenario}_{seed}_{mode}.json').write_text(serialized,encoding='utf-8')
        expected_occupied=None
        for name in ('deterministic','rum','cpt'):
            # Common namespace/run ID: model name does not change random draws
            # at an otherwise identical driver/time decision context.
            model=ParkingModel(facility,population,decision_model=name,seed=seed,initial_occupancy_rate=occupancy,
                scenario_id=scenario,run_id=f'continuous_{scenario}_{seed}',replication_id=f'seed_{seed}',
                allow_illegal_alternatives=illegal,decision_seed_namespace='matched')
            occupied={sid for sid,state in model.space_states.items() if state.occupied}
            if expected_occupied is None:expected_occupied=occupied
            assert occupied==expected_occupied
            model.run_until_complete()
            active={};safe=True;nonempty={};rejected_decisions={};availability=[]
            for event in model.event_logger.records:
                if event.event_type=='SpaceClaimSucceeded':
                    if event.space_id in active:safe=False
                    active[event.space_id]=event.agent_id
                elif event.event_type=='SpaceReleased':active.pop(event.space_id,None)
                elif event.event_type=='CandidateObserved' and event.details.get('feasible_count',0)>0:
                    nonempty[event.agent_id]=nonempty.get(event.agent_id,0)+1
                elif event.event_type=='CandidateRejected' and event.details.get('reason') not in ('no_feasible_candidates',None):
                    rejected_decisions[event.agent_id]=rejected_decisions.get(event.agent_id,0)+1
            finite=all(np.isfinite(e.utility) for e in model.event_logger.records if e.utility is not None)
            terminal=all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in model.agents)
            elapsed=all(a.search_time_s==a.search_ended_s-a.search_started_s for a in model.agents)
            legal=illegal or not any(a.violation for a in model.agents)
            assert safe and finite and terminal and elapsed and legal
            checks.append(dict(scenario=scenario,seed=seed,population=mode,model=name,no_double_claims=safe,
                finite=finite,terminal=terminal,elapsed_identity=elapsed,legal_if_required=legal,
                population_sha256=population_hashes[mode]))
            rows=[]
            for a in model.agents:
                attrs=a.attributes;success=a.parking_time_s is not None
                space=facility.space_by_id.get(a.chosen_space_id) if success else None
                rows.append(dict(scenario=scenario,seed=seed,population=mode,model=name,driver=a.driver_id,
                    persona=attrs.persona,success=success,search_s=a.search_time_s,search_distance_m=a.search_distance_m,
                    walk_m=a.walking_distance_m,walk_relative=a.walking_distance_m/max(a.reference_points.r_walk_m,1e-9) if success else None,
                    chosen_space=space.space_id if space else None,module=space.module_id if space else None,
                    module_switches=a.module_switches,rejected_candidates=a.rejected_spaces,
                    nonempty_scans=nonempty.get(a.driver_id,0),rejected_decisions=rejected_decisions.get(a.driver_id,0),
                    violation=a.violation,lost_claims=a.lost_space_events,
                    eligible=attrs.accessibility_eligibility,mobility_limited=attrs.mobility_limitation,
                    permit=attrs.permit_type,walking_limit_m=attrs.max_walking_distance_m,
                    door=attrs.walmart_door_id,arrival_exit=attrs.arrival_exit_id,preferred_exit=attrs.preferred_exit_id,
                    familiarity=attrs.local_familiarity,urgency=attrs.trip_urgency,
                    r_walk_m=a.reference_points.r_walk_m,r_search_s=a.reference_points.r_search_s,
                    **a.parameters.as_dict(),**{f'cpt_{k}':v for k,v in a.spec.cpt_parameters.as_dict().items()}))
            all_drivers.extend(rows)
            runs.append(dict(scenario=scenario,seed=seed,population=mode,model=name,drivers=size,
                parked=sum(r['success'] for r in rows),mean_search_s=float(np.mean([r['search_s'] for r in rows])),
                population_sha256=population_hashes[mode]))
            del model;gc.collect()
    tag=f'{scenario}_{seed}'
    pd.DataFrame(all_drivers).to_csv(out/'replications'/f'{tag}_drivers.csv',index=False)
    pd.DataFrame(runs).to_csv(out/'replications'/f'{tag}_runs.csv',index=False)
    (out/'replications'/f'{tag}_checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    return tag,runs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/continuous_population_20261027')
    parser.add_argument('--seeds',type=int,nargs='+',default=list(range(42,52)))
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args();out=args.output
    if (out/'design.json').exists():raise FileExistsError('Use a fresh output directory to preserve the frozen design')
    for directory in (out,out/'replications',out/'populations'):directory.mkdir(parents=True,exist_ok=True)
    files=sorted([*ROOT.glob('panda_abm/**/*.py'),*ROOT.glob('scripts/*.py'),*ROOT.glob('tests/*.py'),
                  *ROOT.glob('research/*'),ROOT/'README.md',ROOT/'requirements.txt',ROOT/'data/lot_config.json'])
    files=[p for p in files if p.is_file()]
    plan=dict(seeds=args.seeds,scenarios=SCENARIOS,models=['deterministic','rum','cpt'],population_modes=['heterogeneous','homogeneous'],
        priors=asdict(PopulationPriors()),preference_means=PREFERENCE_MEANS,source_status='Structural assumptions, not estimated populations',
        causal_labels=None,matching='Same attributes/constraints between population modes; same frozen population across models; same initial occupancy and decision RNG namespace',
        clustering=dict(features=['log1p(search_s)','log1p(walk_relative)'],
            eligible_sample='Parked, no mobility limitation, not accessible-eligible, no permit; outcomes of all excluded drivers reported separately',
            train_seeds=args.seeds[:6],validation_seeds=args.seeds[6:],components=[1,2,3,4,5,6],
            method='Full-covariance Gaussian mixtures, BIC on training seeds; robust scaling fitted only on training seeds',
            settings=dict(n_init=10,max_iter=500,reg_covar=.001,tol=.00001),minimum_train=80,minimum_validation=40,
            exploratory_gates='BIC improvement over one component >10; held-out per-seed log-score improvement lower bootstrap bound >0; every component >=5% train/test; seed-bootstrap Jaccard >=.75; >=50% validation points have posterior >=.8',
            stability='20 training-seed bootstrap refits; fixed validation drivers; maximum Jaccard per component',
            null='Identical analysis on homogeneous preference population. Components also supported in null cannot establish preference personas.',
            interpretation='Unsupervised descriptive behavioral regimes; no five-persona naming or automatic claim of driver types',
            cross_scenario='Held-out matched-driver adjusted Rand across normal occupancy scenarios, descriptive only'),
        uncertainty='Paired per-seed differences, 5000 seed bootstrap resamples; exploratory ten-seed pilot, no independence assumption for drivers',
        python=platform.python_version(),packages={name:importlib.metadata.version(name) for name in ('numpy','pandas','mesa','scikit-learn','scipy')},
        source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (out/'design.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(out/'source_snapshot.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for p in files:archive.write(p,p.relative_to(ROOT).as_posix())
    jobs=[(scenario,occupancy,size,seed,str(out)) for scenario,occupancy,size in SCENARIOS for seed in args.seeds]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(run_replication,job) for job in jobs]
        for future in as_completed(futures):
            tag,runs=future.result()
            print(tag+': '+', '.join(f'{r["population"][:3]}/{r["model"]} {r["parked"]}/{r["drivers"]}' for r in runs),flush=True)
    drivers=pd.concat([pd.read_csv(p) for p in sorted((out/'replications').glob('*_drivers.csv'))],ignore_index=True)
    runs=pd.concat([pd.read_csv(p) for p in sorted((out/'replications').glob('*_runs.csv'))],ignore_index=True)
    checks=[r for p in sorted((out/'replications').glob('*_checks.json')) for r in json.loads(p.read_text())]
    drivers.to_csv(out/'drivers.csv',index=False);runs.to_csv(out/'runs.csv',index=False)
    (out/'checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(f'Completed {len(runs)} runs and {len(drivers)} driver outcomes',flush=True)


if __name__=='__main__':main()
