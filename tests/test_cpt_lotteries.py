import math
import pytest
from panda_abm.behavior.decision.cpt import CPTParameters,cumulative_prospect_value,cpt_value,probability_weight,CPTDecisionModel
from panda_abm.behavior.decision.base import DecisionContext
from panda_abm.behavior import BehavioralParameters,ReferencePoints
from panda_abm.environment import ParkingSpace


def test_cumulative_gains_match_hand_calculation_and_differ_from_separable_weights():
    # High outcome's upper-tail mass is .2; low outcome's weight is w(1)-w(.2).
    expected=probability_weight(.2)*cpt_value(100)+(1-probability_weight(.2))*cpt_value(10)
    actual=cumulative_prospect_value(((10,.8),(100,.2)))
    assert actual==pytest.approx(expected)
    separable=probability_weight(.8)*cpt_value(10)+probability_weight(.2)*cpt_value(100)
    assert not math.isclose(actual,separable)


def test_cumulative_losses_match_hand_calculation():
    cp=CPTParameters()
    expected=probability_weight(.2,cp.gamma_loss)*cpt_value(-100)+(1-probability_weight(.2,cp.gamma_loss))*cpt_value(-10)
    assert cumulative_prospect_value(((-100,.2),(-10,.8)))==pytest.approx(expected)


def test_mixed_lottery_does_not_renormalize_sign_branches():
    cp=CPTParameters()
    expected=probability_weight(.3,cp.gamma_loss)*cpt_value(-50)+probability_weight(.7,cp.gamma)*cpt_value(100)
    assert cumulative_prospect_value(((-50,.3),(100,.7)))==pytest.approx(expected)


def test_linear_parameters_reduce_to_expected_value():
    cp=CPTParameters(alpha=1,beta=1,lambda_loss=1,gamma=1,gamma_loss=1)
    lottery=((-30,.2),(-10,.1),(0,.1),(20,.4),(100,.2))
    assert cumulative_prospect_value(lottery,cp)==pytest.approx(sum(x*p for x,p in lottery))


def test_order_ties_zero_probability_and_reference_invariance():
    a=((-10,.2),(20,.8))
    assert cumulative_prospect_value(a)==pytest.approx(cumulative_prospect_value(tuple(reversed(a))))
    assert cumulative_prospect_value(a)==pytest.approx(cumulative_prospect_value(((-10,.2),(20,.3),(20,.5),(999,0))))
    assert cumulative_prospect_value(a)==pytest.approx(cumulative_prospect_value(((90,.2),(120,.8)),reference=100))
    assert cumulative_prospect_value(((12,1.),))==pytest.approx(cpt_value(12))


@pytest.mark.parametrize('lottery',[(),((0,.9),),((0,-.1),(1,1.1)),((float('nan'),1),),((1,float('inf')), )])
def test_invalid_lotteries_rejected(lottery):
    with pytest.raises(ValueError):cumulative_prospect_value(lottery)


def test_first_order_dominance_on_positive_negative_and_mixed_lotteries():
    for low in [(-100,-20),(-20,20),(10,100)]:
        assert cumulative_prospect_value(((low[0]+1,.4),(low[1]+1,.6)))>cumulative_prospect_value(((low[0],.4),(low[1],.6)))


def test_probability_reaches_cpt_without_double_counting_linear_walk_value():
    ctx=DecisionContext('D',BehavioralParameters(acceptance_utility_threshold=0),ReferencePoints(),0,(0,0),(0,0),
        availability_probabilities={'certain':1.,'uncertain':.4})
    result=CPTDecisionModel().evaluate_candidates(ctx,[ParkingSpace('certain','A',10,0),ParkingSpace('uncertain','A',10,0)])
    a,b=result.candidate_evaluations
    assert a.utility>b.utility
    assert a.utility==pytest.approx(cpt_value(a.diagnostics['success_outcome']))
    assert b.utility==pytest.approx(cumulative_prospect_value(((b.diagnostics['success_outcome'],.4),(b.diagnostics['failure_outcome'],.6))))
