"""Matched crowded-lot experiments for M0/M1/M2, without changing their behavior.

Writes per-driver outcomes, per-run metrics, aggregate comparisons and safety
checks. Initial occupancy and generated drivers are matched across models in
each seed; different seeds regenerate both. Distances remain straight-line.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np
import pandas as pd

from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.parameters import PERSONA_PARAMETER_PROFILES
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.environment import generate_synthetic_facility, load_facility_from_lot_config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results'/'persona_stress_20261027'/'mixed')
    parser.add_argument('--seeds',type=int,nargs='+',default=[42,43,44])
    parser.add_argument('--personas',nargs='+',choices=list(PERSONA_PARAMETER_PROFILES),default=list(PERSONA_PARAMETER_PROFILES))
    parser.add_argument('--cpt-profile-mode',choices=['shared','persona'],default='persona')
    parser.add_argument('--scenarios',nargs='+',default=None,help='Optional subset of scenario names.')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    scenarios=[
        ('synthetic_crowded','synthetic',.80,80,0),
        ('synthetic_saturated','synthetic',.95,80,0),
        ('synthetic_full','synthetic',1.,40,0),
        ('walmart_crowded','walmart',.80,80,0),
        ('walmart_saturated','walmart',.95,80,0),
        ('walmart_full','walmart',1.,40,0),
        ('walmart_saturated_exit_preference','walmart',.95,80,1.),
        ('synthetic_rule_tradeoff','synthetic',.35,40,0),
    ]
    if args.scenarios:
        known={s[0] for s in scenarios}
        if not set(args.scenarios)<=known:parser.error(f'Unknown scenarios: {set(args.scenarios)-known}')
        scenarios=[s for s in scenarios if s[0] in args.scenarios]
    walmart=load_facility_from_lot_config(ROOT/'data'/'lot_config.json')
    runs=[]
    drivers=[]
    checks=[]
    started=time.perf_counter()
    for scenario,facility_name,occupancy,size,beta_exit in scenarios:
        for seed in args.seeds:
            facility=generate_synthetic_facility(seed) if facility_name=='synthetic' else walmart
            # Hypothetical price/rule tradeoff; never modifies Walmart or its JSON.
            rule_tradeoff=scenario=='synthetic_rule_tradeoff'
            if rule_tradeoff:
                facility=replace(facility,spaces=tuple(replace(s,price_per_hour=0. if s.reserved_type or s.accessible else 9.) for s in facility.spaces))
            population=make_population(facility,size=size,seed=seed,personas=tuple(args.personas),cpt_profile_mode=args.cpt_profile_mode)
            if beta_exit:
                population=replace(population,drivers=tuple(replace(d,behavioral_parameters=replace(d.behavioral_parameters,beta_exit=beta_exit)) for d in population.drivers))
            initial_ids=None
            for model_name in ('deterministic','rum','cpt'):
                run_id=f'{scenario}_{model_name}_{seed}'
                model=ParkingModel(facility,population,decision_model=model_name,run_id=run_id,
                    scenario_id=scenario,replication_id=f'seed_{seed}',seed=seed,initial_occupancy_rate=occupancy,
                    allow_illegal_alternatives=rule_tradeoff)
                occupied={sid for sid,s in model.space_states.items() if s.occupied}
                if initial_ids is None:initial_ids=occupied
                assert occupied==initial_ids,'Models must start with identical occupancy'
                run_start=time.perf_counter()
                model.run_until_complete()
                agents=list(model.agents)
                rows=[]
                for a in agents:
                    chosen=facility.space_by_id.get(a.chosen_space_id)
                    rule_violation=bool(chosen and (
                        (chosen.accessible and not a.attributes.accessibility_eligibility) or
                        (chosen.reserved_type and a.attributes.permit_type!=(chosen.permit_requirement or chosen.reserved_type))))
                    rows.append(dict(scenario=scenario,seed=seed,model=model_name,driver=a.driver_id,
                        persona=a.attributes.persona,
                        success=a.parking_time_s is not None,abandoned=a.state==DriverState.ABANDONED,
                        search_time_s=a.search_time_s,walking_distance_m=a.walking_distance_m,
                        rejected=a.rejected_spaces,lost_spaces=a.lost_space_events,final_state=a.state.value,
                        chosen_space=a.chosen_space_id,arrival_exit=a.attributes.arrival_exit_id,
                        preferred_exit=a.attributes.preferred_exit_id,beta_exit=a.parameters.beta_exit,
                        r_walk_m=a.reference_points.r_walk_m,r_exit_m=a.reference_points.r_exit_m,
                        reference_space_count=a.reference_points.reference_space_count,
                        distance_reference_policy=a.reference_points.distance_reference_policy,
                        cpt_parameters=a.spec.cpt_parameters.as_dict(),cpt_parameter_source=a.spec.cpt_parameter_source,
                        price_per_hour=chosen.price_per_hour if chosen else None,
                        chosen_accessible=chosen.accessible if chosen else False,
                        accessible_eligible=a.attributes.accessibility_eligibility,
                        rule_violation=rule_violation,
                        preferred_exit_distance_m=getattr(chosen,f'distance_to_{a.attributes.preferred_exit_id}_m',None) if chosen else None))
                frame=pd.DataFrame(rows)
                drivers.extend(rows)
                events=model.event_logger.records
                failures=sum(r.event_type=='SpaceClaimFailed' for r in events)
                below=sum(r.event_type=='CandidateRejected' and r.details.get('reason')=='below_acceptance_threshold' for r in events)
                no_candidates=sum(r.event_type=='CandidateRejected' and r.details.get('reason')=='no_feasible_candidates' for r in events)
                active={}
                legal=True
                for r in events:
                    if r.event_type=='SpaceClaimSucceeded':
                        if r.space_id in active:legal=False
                        active[r.space_id]=r.agent_id
                    elif r.event_type=='SpaceReleased':active.pop(r.space_id,None)
                finite=all(np.isfinite(r.utility) for r in events if r.utility is not None)
                completed=all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in agents)
                # Initial vehicles never depart in the current model.
                full_safe=occupancy<1 or not frame.success.any()
                checks.append(dict(run_id=run_id,no_double_claims=legal,finite_utilities=finite,
                    all_agents_terminal=completed,full_lot_never_parks=full_safe))
                assert legal and finite and completed and full_safe,checks[-1]
                if not rule_tradeoff:assert not frame.rule_violation.any(),'Illegal parking in a legal-only scenario'
                success=frame[frame.success]
                runs.append(dict(scenario=scenario,seed=seed,model=model_name,occupancy=occupancy,
                    drivers=size,parked=int(frame.success.sum()),abandoned=int(frame.abandoned.sum()),
                    success_rate=frame.success.mean(),mean_search_all_s=frame.search_time_s.mean(),
                    mean_search_parked_s=success.search_time_s.mean(),p90_search_all_s=frame.search_time_s.quantile(.9),
                    mean_walk_parked_m=success.walking_distance_m.mean(),mean_rejected=frame.rejected.mean(),
                    unique_chosen_spaces=success.chosen_space.nunique(),claim_failures=failures,
                    below_threshold_rejections=below,no_candidate_rejections=no_candidates,
                    seconds=round(time.perf_counter()-run_start,3)))
                pd.DataFrame(runs).to_csv(args.output/'per_run.csv',index=False)
                print(f'{run_id}: {int(frame.success.sum())}/{size} parked; search {frame.search_time_s.mean():.1f}s; {runs[-1]["seconds"]}s elapsed',flush=True)
    pd.DataFrame(drivers).to_csv(args.output/'drivers.csv',index=False)
    driver_frame=pd.DataFrame(drivers)
    driver_frame['walking_if_parked']=driver_frame.walking_distance_m.where(driver_frame.success)
    driver_frame['price_if_parked']=driver_frame.price_per_hour.where(driver_frame.success)
    driver_frame['accessible_if_parked']=driver_frame.chosen_accessible.astype(float).where(driver_frame.success)
    driver_frame['rule_violation_if_parked']=driver_frame.rule_violation.astype(float).where(driver_frame.success)
    persona_summary=driver_frame.groupby(['scenario','model','persona']).agg(
        drivers=('driver','count'),parked=('success','sum'),success_rate=('success','mean'),
        mean_search_all_s=('search_time_s','mean'),mean_walk_parked_m=('walking_if_parked','mean'),
        mean_price_parked_per_hour=('price_if_parked','mean'),accessible_share_parked=('accessible_if_parked','mean'),
        illegal_share_parked=('rule_violation_if_parked','mean')).reset_index()
    persona_summary.to_csv(args.output/'persona_summary.csv',index=False)
    run_frame=pd.DataFrame(runs)
    summary=run_frame.groupby(['scenario','model']).agg(runs=('seed','count'),
        drivers=('drivers','sum'),parked=('parked','sum'),success_rate=('success_rate','mean'),
        success_rate_std=('success_rate','std'),mean_search_all_s=('mean_search_all_s','mean'),
        mean_search_parked_s=('mean_search_parked_s','mean'),mean_walk_parked_m=('mean_walk_parked_m','mean'),
        mean_rejected=('mean_rejected','mean'),claim_failures=('claim_failures','sum'),
        below_threshold_rejections=('below_threshold_rejections','sum'),no_candidate_rejections=('no_candidate_rejections','sum')).reset_index()
    summary.to_csv(args.output/'summary.csv',index=False)
    (args.output/'checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    (args.output/'conditions.json').write_text(json.dumps(dict(seeds=args.seeds,scenarios=scenarios,
        seconds=time.perf_counter()-started,population=list(args.personas),cpt_profile_mode=args.cpt_profile_mode,
        persona_profiles={name:PERSONA_PARAMETER_PROFILES[name].as_dict() for name in args.personas},
        persona_assignment='balanced and shuffled with a separate seeded RNG',
        experimental_assumptions='uncalibrated weights; accessibility_seeking implies eligibility and a 120 m cap; synthetic_rule_tradeoff exposes illegal alternatives and hypothetical fees; Walmart remains free and legal-only',
        arrival_interval_s=20,initial_vehicles_depart=False,step_seconds=10,max_search_time_s=600,
        integration_seconds=1.,decision_interval_s=10.,parking_maneuver_s=2.,claim_hazard_per_s=.002,failure_delay_s=30.,
        navigation='estimated connected aisle graph inferred from row geometry; all space spurs and side corridors',
        distance_references='fixed median of static legal usable inventory for chosen door and preferred exit; respects walking cap; no occupancy conditioning; explicit custom references supported',
        cpt='finite-outcome cumulative gain/loss weighting; terminal-horizon observed-offer continuation mixture after one scan; fixed claim probabilities during extra delay; explicit future lottery override; acceptance before softmax; external utility aspiration unchanged'),indent=2)+'\n')
    print(summary.to_string(index=False),flush=True)


if __name__=='__main__':main()
