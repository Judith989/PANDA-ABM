"""Semantic checks independent of the CPT weighting implementation."""
from dataclasses import replace
import math
import pytest
from panda_abm.behavior import BehavioralParameters, ReferencePoints
from panda_abm.behavior.decision.base import DecisionContext
from panda_abm.behavior.decision.cpt import LinearProspectDecisionModel, CPTDecisionModel
from panda_abm.environment import ParkingSpace


def utility(f, p):
    # Independent specification of the nine oriented dimensions.
    costs={'walking_distance_m':('beta_walk',250), 'exit_distance_m':('beta_exit',300),
           'search_time_s':('beta_search',600), 'approach_time_s':('beta_approach',120),
           'price_per_hour':('beta_price',10), 'rule_risk':('beta_risk',1)}
    benefits={'availability_probability':'beta_availability',
              'accessibility_match':'beta_accessibility','familiarity':'beta_familiarity'}
    return sum(getattr(p,w)*(1-min(1,max(0,f[k]/s))) for k,(w,s) in costs.items())+sum(
        getattr(p,w)*min(1,max(0,f[k])) for k,w in benefits.items())


@pytest.mark.parametrize('elapsed',[0,550,590,700])
@pytest.mark.parametrize('probability',[0,.3,1])
def test_common_reference_and_clipped_delayed_failure(elapsed, probability):
    p=BehavioralParameters(acceptance_utility_threshold=0)
    refs=ReferencePoints(r_walk_m=70,r_exit_m=90,r_search_s=300)
    ctx=DecisionContext('d',p,refs,elapsed,(0,0),(0,0),rng_seed=7,
        approach_times_s={'s':20},availability_probabilities={'s':probability})
    result=LinearProspectDecisionModel().evaluate_candidates(ctx,[ParkingSpace('s','a',100,0)])
    e=result.candidate_evaluations[0]; f=e.features
    ref=dict(f,walking_distance_m=70,exit_distance_m=90,search_time_s=300,
             approach_time_s=0,price_per_hour=0,rule_risk=0,availability_probability=1,accessibility_match=0)
    success=dict(f,search_time_s=elapsed+20,availability_probability=1)
    fail=dict(success,walking_distance_m=250,exit_distance_m=300,availability_probability=0,
              accessibility_match=0,price_per_hour=0,rule_risk=0,search_time_s=elapsed+50)
    good=utility(success,p)-utility(ref,p); bad=utility(fail,p)-utility(ref,p)
    assert e.diagnostics['failure_outcome']==pytest.approx(bad)
    assert e.utility==pytest.approx(probability*good+(1-probability)*bad)
    later_good=utility(dict(success,search_time_s=elapsed+30),p)-utility(ref,p)
    later_bad=utility(dict(fail,search_time_s=elapsed+60),p)-utility(ref,p)
    cont=probability*later_good+(1-probability)*later_bad
    assert e.diagnostics['continuation_value']==pytest.approx(cont)
    assert (result.chosen_action=='park')==(e.utility+1e-12>=cont)


def test_linear_control_probabilities_match_independent_softmax_and_acceptance():
    ctx=DecisionContext('d',BehavioralParameters(acceptance_utility_threshold=0),
        ReferencePoints(),0,(0,0),(0,0),rng_seed=17,
        continuation_outcomes=((-10.,1.),))
    result=LinearProspectDecisionModel().evaluate_candidates(ctx,[ParkingSpace(str(i),'a',i*30,0) for i in range(4)])
    scores=[e.utility for e in result.candidate_evaluations]
    weights=[math.exp((s-max(scores))/ctx.behavioral_parameters.decision_temperature) for s in scores]
    for e,w in zip(result.candidate_evaluations,weights):
        assert result.probabilities[e.space_id]==pytest.approx(w/sum(weights))


def test_reference_shift_affects_both_branches_equally_before_transform():
    ctx=DecisionContext('d',BehavioralParameters(acceptance_utility_threshold=0),
        ReferencePoints(),0,(0,0),(0,0),rng_seed=1)
    spaces=[ParkingSpace('s','a',30,0)]
    a=CPTDecisionModel().evaluate_candidates(ctx,spaces).candidate_evaluations[0].diagnostics
    b=CPTDecisionModel().evaluate_candidates(replace(ctx,reference_points=replace(ctx.reference_points,r_walk_m=200)),spaces).candidate_evaluations[0].diagnostics
    assert a['success_outcome']-b['success_outcome']==pytest.approx(a['failure_outcome']-b['failure_outcome'])
