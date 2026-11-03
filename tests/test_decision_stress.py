"""Decision safety under large, restricted and numerically difficult choice sets."""
from dataclasses import replace
import math

import pytest

from panda_abm.behavior import BehavioralParameters, ReferencePoints
from panda_abm.behavior.decision import CPTDecisionModel, DecisionContext, DeterministicUtilityModel, RandomUtilityModel
from panda_abm.environment import ParkingSpace


MODELS = [DeterministicUtilityModel, RandomUtilityModel, CPTDecisionModel]


def make_context(temperature=0.35):
    return DecisionContext(
        driver_id='stress', behavioral_parameters=BehavioralParameters(
            decision_temperature=temperature, acceptance_utility_threshold=-100,
        ), reference_points=ReferencePoints(), accumulated_search_time_s=600,
        current_position_m=(0,0), destination_m=(0,0), rng_seed=42,
    )


@pytest.mark.parametrize('model_class', MODELS)
@pytest.mark.parametrize('size', [0,1,1000])
def test_empty_and_fully_blocked_sets_never_produce_parking(model_class,size):
    spaces=[ParkingSpace(str(i),'A',i,0,unavailable=True) for i in range(size)]
    result=model_class().evaluate_candidates(make_context(),spaces)
    assert result.chosen_action=='continue'
    assert result.chosen_space_id is None


@pytest.mark.parametrize('model_class', MODELS)
@pytest.mark.parametrize('temperature', [0,1e-12,0.35,1e6])
def test_large_mixed_choice_sets_are_finite_feasible_and_repeatable(model_class,temperature):
    spaces=[ParkingSpace(str(i),'A',i*10,0,unavailable=i%7==0,accessible=i%11==0,
        reserved_type='staff' if i%13==0 else None, price_per_hour=(i%20)*100) for i in range(1000)]
    context=make_context(temperature)
    model=model_class()
    a=model.evaluate_candidates(context,spaces)
    b=model.evaluate_candidates(context,spaces)
    assert a.chosen_space_id==b.chosen_space_id
    assert a.probabilities==b.probabilities
    assert all(math.isfinite(e.utility) for e in a.candidate_evaluations)
    feasible={e.space_id for e in a.candidate_evaluations if e.feasible}
    if a.chosen_action == 'park':
        assert a.chosen_space_id in feasible
    else:
        assert model_class is CPTDecisionModel
        assert a.diagnostics['reason'] == 'continuation_preferred'
    if a.probabilities:
        assert set(a.probabilities)==feasible
        assert sum(a.probabilities.values())==pytest.approx(1)
        assert all(math.isfinite(p) and 0<=p<=1 for p in a.probabilities.values())


@pytest.mark.parametrize('model_class', MODELS)
def test_unattainable_acceptance_threshold_rejects_every_candidate(model_class):
    context=make_context()
    context=replace(context,behavioral_parameters=replace(context.behavioral_parameters,acceptance_utility_threshold=1e6))
    result=model_class().evaluate_candidates(context,[ParkingSpace('best','A',0,0)])
    assert result.chosen_action=='continue'
    assert result.chosen_space_id is None
