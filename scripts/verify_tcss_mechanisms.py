"""Independent specification oracle and frozen CPT mechanism panel (E0)."""
from pathlib import Path
from itertools import product
import argparse
import hashlib
import json
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from panda_abm.behavior.continuous import make_population
from panda_abm.behavior.cpt_parameters import CPTParameters
from panda_abm.behavior.decision.base import DecisionContext
from panda_abm.behavior.decision.cpt import LinearProspectDecisionModel,cumulative_prospect_value
from panda_abm.environment import ParkingSpace,load_facility_from_lot_config


def utility(f,p):
    costs={'walking_distance_m':('beta_walk',250),'exit_distance_m':('beta_exit',300),
        'search_time_s':('beta_search',600),'approach_time_s':('beta_approach',120),
        'price_per_hour':('beta_price',10),'rule_risk':('beta_risk',1)}
    benefits={'availability_probability':'beta_availability','accessibility_match':'beta_accessibility',
        'familiarity':'beta_familiarity'}
    return sum(getattr(p,w)*(1-min(1,max(0,f[k]/s))) for k,(w,s) in costs.items())+sum(
        getattr(p,w)*min(1,max(0,f[k])) for k,w in benefits.items())


def oracle(lottery,cp):
    # Direct tail masses per unique outcome, rather than iterative branch accumulation.
    merged={}
    for x,p in lottery:merged[x]=merged.get(x,0)+p
    def weight(p,g):
        return p**g/(p**g+(1-p)**g)**(1/g) if 0<p<1 else float(p)
    total=0.
    for x,p in merged.items():
        if not p:continue
        g=cp.gamma_loss if x<0 else cp.gamma
        tail=sum(q for y,q in merged.items() if (y<=x if x<0 else y>=x))
        strict=sum(q for y,q in merged.items() if (y<x if x<0 else y>x))
        v=x**cp.alpha if x>=0 else -cp.lambda_loss*(-x)**cp.beta
        total+=(weight(min(1,tail),g)-weight(min(1,strict),g))*v
    return total


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    started=time.perf_counter()
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    pop=make_population(facility,size=200,seed=20261028)
    (args.output/'population.json').write_text(json.dumps(pop.as_dict(),sort_keys=True),encoding='utf-8')
    contexts=lotteries=0;max_error=0.;switch_means={str(s):[] for s in product((0,1),repeat=3)}
    for d in pop.drivers:
        p=d.behavioral_parameters;refs=d.reference_points;cp=d.cpt_parameters
        for walk,exit_m,elapsed,prob,approach in product((10.,100.,260.),(20.,150.,350.),(0.,550.,590.),(0.,.5,1.),(0.,20.,100.)):
            ctx=DecisionContext(d.driver_id,p,refs,elapsed,(0,0),(0,0),rng_seed=31,
                preferred_exit_id='exit_a',approach_times_s={'s':approach},
                availability_probabilities={'s':prob},remaining_search_time_s=600-elapsed,
                accessibility_eligibility=True)
            s=ParkingSpace('s','A',walk,0,distance_to_exit_a_m=exit_m)
            result=LinearProspectDecisionModel().evaluate_candidates(ctx,[s])
            e=result.candidate_evaluations[0]; f=e.features
            reference=dict(f,walking_distance_m=refs.r_walk_m,exit_distance_m=refs.r_exit_m,
                search_time_s=refs.r_search_s,approach_time_s=0.,price_per_hour=0.,rule_risk=0.,
                availability_probability=1.,accessibility_match=0.)
            success=dict(f,search_time_s=elapsed+approach,availability_probability=1.)
            failure=dict(success,walking_distance_m=250.,exit_distance_m=300.,
                availability_probability=0.,accessibility_match=0.,price_per_hour=0.,rule_risk=0.,
                search_time_s=elapsed+approach+30.)
            ref=utility(reference,p)
            good=utility(success,p)-ref;bad=utility(failure,p)-ref
            expected=prob*good+(1-prob)*bad
            max_error=max(max_error,abs(e.utility-expected))
            assert abs(e.utility-expected)<1e-10
            reachable=approach<600-elapsed
            assert e.feasible==reachable
            if reachable:
                later_p=prob if approach+10<600-elapsed else 0.
                later_good=utility(dict(success,search_time_s=elapsed+approach+10),p)-ref
                later_bad=utility(dict(failure,search_time_s=elapsed+approach+40),p)-ref
                continuation=later_p*later_good+(1-later_p)*later_bad
                assert abs(e.diagnostics['continuation_value']-continuation)<1e-10
                accept=utility(success,p)>=p.acceptance_utility_threshold and expected+1e-12>=continuation
                assert (result.chosen_action=='park')==accept
            else:assert result.chosen_action=='continue'
            for switches in product((0,1),repeat=3):
                curvature,loss,weighting=switches
                q=CPTParameters(alpha=cp.alpha if curvature else 1,beta=cp.beta if curvature else 1,
                    lambda_loss=cp.lambda_loss if loss else 1,gamma=cp.gamma if weighting else 1,
                    gamma_loss=cp.gamma_loss if weighting else 1)
                lottery=((good,prob),(bad,1-prob))
                actual=cumulative_prospect_value(lottery,q);expected_q=oracle(lottery,q)
                max_error=max(max_error,abs(actual-expected_q))
                assert abs(actual-expected_q)<1e-10
                switch_means[str(switches)].append(actual);lotteries+=1
            contexts+=1
        print(f'Verified {contexts} contexts / {lotteries} switch lotteries',flush=True)
    sources=[*ROOT.glob('panda_abm/**/*.py'),Path(__file__)]
    report=dict(status='passed',population_seed=20261028,drivers=200,contexts=contexts,
        switch_lotteries=lotteries,max_absolute_oracle_error=max_error,
        switch_value_means={k:float(np.mean(v)) for k,v in switch_means.items()},
        seconds=time.perf_counter()-started,
        limitations='Synthetic verification, not behavioral calibration; multi-offer sampling and mixture cases covered by pytest.',
        source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (args.output/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
