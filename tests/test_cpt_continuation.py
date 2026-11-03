from dataclasses import replace
import pytest
from panda_abm.behavior import BehavioralParameters,ReferencePoints
from panda_abm.behavior.decision.base import DecisionContext
from panda_abm.behavior.decision.cpt import CPTDecisionModel,cumulative_prospect_value
from panda_abm.behavior.decision.transforms import linear_utility
from panda_abm.environment import ParkingSpace


def context(**kwargs):
    return DecisionContext('D',BehavioralParameters(acceptance_utility_threshold=0),
        ReferencePoints(r_walk_m=80),0,(0,0),(0,0),rng_seed=42,**kwargs)


@pytest.mark.parametrize('elapsed',[0,100,300,550])
def test_reasonable_offer_is_not_rejected_because_elapsed_search_is_missing_from_continuation(elapsed):
    ctx=replace(context(approach_times_s={'S':5},availability_probabilities={'S':.95}),accumulated_search_time_s=elapsed)
    result=CPTDecisionModel().evaluate_candidates(ctx,[ParkingSpace('S','A',80,0)])
    e=result.candidate_evaluations[0]
    assert result.chosen_action=='park'
    assert e.utility>e.diagnostics['continuation_value']


def test_continuation_is_same_terminal_lottery_after_one_more_scan():
    ctx=context(approach_times_s={'S':5},availability_probabilities={'S':.8})
    e=CPTDecisionModel().evaluate_candidates(ctx,[ParkingSpace('S','A',100,0)]).candidate_evaluations[0]
    cost=ctx.behavioral_parameters.beta_search*ctx.decision_interval_s/600
    expected=cumulative_prospect_value(((e.diagnostics['success_outcome']-cost,.8),(e.diagnostics['failure_outcome']-cost,.2)))
    assert e.diagnostics['continuation_value']==pytest.approx(expected)


def test_rejecting_a_bad_sample_cannot_hide_an_acceptable_space():
    ctx=context(continuation_outcomes=((0.,1.),))
    ctx=replace(ctx,behavioral_parameters=replace(ctx.behavioral_parameters,decision_temperature=1e6))
    spaces=[ParkingSpace('good','A',10,0),ParkingSpace('poor','A',240,0)]
    for seed in range(20):
        result=CPTDecisionModel().evaluate_candidates(replace(ctx,rng_seed=seed),spaces)
        assert result.chosen_space_id=='good'
        assert result.probabilities['poor']==0


def test_better_explicit_future_prospect_still_causes_continuation():
    ctx=context(continuation_outcomes=((10.,1.),))
    result=CPTDecisionModel().evaluate_candidates(ctx,[ParkingSpace('S','A',80,0)])
    assert result.chosen_action=='continue'
    assert result.diagnostics['reason']=='continuation_preferred'


def test_absolute_aspiration_is_not_relaxed_by_continuation_fix():
    ctx=replace(context(),behavioral_parameters=BehavioralParameters(acceptance_utility_threshold=1e6))
    result=CPTDecisionModel().evaluate_candidates(ctx,[ParkingSpace('S','A',0,0)])
    assert result.chosen_action=='continue'
    assert result.diagnostics['reason']=='below_acceptance_threshold'


def test_continuation_cannot_forecast_parking_after_the_deadline():
    ctx=context(approach_times_s={'S':5},remaining_search_time_s=8)
    e=CPTDecisionModel().evaluate_candidates(ctx,[ParkingSpace('S','A',80,0)]).candidate_evaluations[0]
    cost=ctx.behavioral_parameters.beta_search*ctx.decision_interval_s/600
    assert e.diagnostics['continuation_value']==pytest.approx(cumulative_prospect_value(((e.diagnostics['failure_outcome']-cost,1.),)))


def test_unreachable_current_offer_is_infeasible():
    ctx=context(approach_times_s={'S':15},remaining_search_time_s=8)
    result=CPTDecisionModel().evaluate_candidates(ctx,[ParkingSpace('S','A',80,0)])
    assert not result.candidate_evaluations[0].feasible
    assert result.chosen_action=='continue'


def test_multiple_observed_offers_form_one_normalized_terminal_lottery():
    ctx=context(availability_probabilities={'near':.9,'far':.4})
    spaces=[ParkingSpace('near','A',20,0),ParkingSpace('far','A',150,0),
            ParkingSpace('blocked','A',0,0,unavailable=True)]
    result=CPTDecisionModel().evaluate_candidates(ctx,spaces)
    feasible=[e for e in result.candidate_evaluations if e.feasible]
    cost=ctx.behavioral_parameters.beta_search*ctx.decision_interval_s/600
    lottery=[]
    for e in feasible:
        p=e.diagnostics['success_probability']
        lottery.extend(((e.diagnostics['success_outcome']-cost,p/2),
                        (e.diagnostics['failure_outcome']-cost,(1-p)/2)))
    assert sum(p for _,p in lottery)==pytest.approx(1)
    expected=cumulative_prospect_value(lottery)
    assert all(e.diagnostics['continuation_value']==pytest.approx(expected) for e in result.candidate_evaluations)


def test_empty_explicit_continuation_is_invalid_instead_of_silently_using_default():
    with pytest.raises(ValueError,match='sum to one'):
        CPTDecisionModel().evaluate_candidates(context(continuation_outcomes=()),[ParkingSpace('S','A',80,0)])
