import numpy as np
import pytest

from panda_abm.behavior import BehavioralParameters, ReferencePoints
from panda_abm.behavior.parameters import parameters_for_persona
from panda_abm.behavior.decision import (
    CPTDecisionModel,
    DecisionContext,
    DeterministicUtilityModel,
    RandomUtilityModel,
    cpt_value,
    probability_weight,
    stable_softmax,
)
from panda_abm.environment import ParkingSpace


def context(seed=123):
    return DecisionContext(
        driver_id="D001",
        behavioral_parameters=BehavioralParameters(decision_temperature=0.2, acceptance_utility_threshold=0.0),
        reference_points=ReferencePoints(r_walk_m=100.0, r_search_s=300.0),
        accumulated_search_time_s=60.0,
        current_position_m=(0.0, 0.0),
        destination_m=(0.0, 0.0),
        rng_seed=seed,
    )


def test_lower_walking_distance_increases_deterministic_utility():
    near = ParkingSpace("near", "A", 10.0, 0.0)
    far = ParkingSpace("far", "A", 100.0, 0.0)
    result = DeterministicUtilityModel().evaluate_candidates(context(), [far, near])
    utilities = {e.space_id: e.utility for e in result.candidate_evaluations}

    assert utilities["near"] > utilities["far"]
    assert result.chosen_space_id == "near"


def test_higher_search_burden_decreases_utility():
    space = ParkingSpace("S001", "A", 10.0, 0.0)
    low = DeterministicUtilityModel().evaluate_candidates(context(), [space])
    high_ctx = DecisionContext(
        driver_id="D001",
        behavioral_parameters=BehavioralParameters(acceptance_utility_threshold=0.0),
        reference_points=ReferencePoints(),
        accumulated_search_time_s=500.0,
        current_position_m=(0.0, 0.0),
        destination_m=(0.0, 0.0),
    )
    high = DeterministicUtilityModel().evaluate_candidates(high_ctx, [space])

    assert low.chosen_utility > high.chosen_utility


def test_unavailable_and_restricted_spaces_are_infeasible_by_default():
    unavailable = ParkingSpace("closed", "A", 0.0, 0.0, unavailable=True)
    reserved = ParkingSpace("reserved", "A", 1.0, 0.0, reserved_type="permit")
    result = DeterministicUtilityModel().evaluate_candidates(context(), [unavailable, reserved])

    assert result.chosen_action == "continue"
    assert all(not item.feasible for item in result.candidate_evaluations)


def test_random_utility_reproducible_under_fixed_seed():
    spaces = [ParkingSpace(f"S{i}", "A", float(i * 10), 0.0) for i in range(5)]
    first = RandomUtilityModel().evaluate_candidates(context(seed=88), spaces)
    second = RandomUtilityModel().evaluate_candidates(context(seed=88), spaces)

    assert first.chosen_space_id == second.chosen_space_id
    assert first.probabilities == second.probabilities


def test_stable_softmax_probabilities_sum_to_one():
    probs = stable_softmax(np.array([1000.0, 1001.0, 999.0]), temperature=0.5)

    assert np.isclose(probs.sum(), 1.0)
    assert np.all(probs >= 0.0)


def test_cpt_value_zero_and_loss_aversion():
    assert cpt_value(0.0) == 0.0
    assert abs(cpt_value(-1.0, lambda_loss=2.25)) > abs(cpt_value(1.0, lambda_loss=2.25))


def test_cpt_cost_orientation_signs():
    refs = ReferencePoints(r_walk_m=100.0, r_search_s=300.0)
    assert refs.r_walk_m - 80.0 > 0.0
    assert refs.r_walk_m - 140.0 < 0.0


def test_probability_weight_boundaries_and_range():
    assert probability_weight(0.0) == 0.0
    assert probability_weight(1.0) == 1.0
    mid = probability_weight(0.4)
    assert 0.0 <= mid <= 1.0
    with pytest.raises(ValueError):
        probability_weight(1.1)


def test_cpt_model_logs_reference_diagnostics():
    result = CPTDecisionModel().evaluate_candidates(context(), [ParkingSpace("S001", "A", 10.0, 0.0)])
    diagnostics = result.candidate_evaluations[0].diagnostics

    assert "walk_cpt_value" in diagnostics
    assert "weighted_availability_probability" in diagnostics


def test_convenience_seeker_profile_uses_requested_weights():
    params = parameters_for_persona("convenience_seeker")

    assert params.beta_walk == 0.90
    assert params.beta_price == 0.20
    assert params.beta_search == 0.40
    assert params.beta_risk == 0.60
    assert params.beta_availability == 0.70
    assert params.beta_familiarity == 0.40


def test_low_utility_space_is_rejected_by_acceptance_threshold():
    params = BehavioralParameters(acceptance_utility_threshold=3.5)
    strict_context = DecisionContext(
        driver_id="D001",
        behavioral_parameters=params,
        reference_points=ReferencePoints(),
        accumulated_search_time_s=500.0,
        current_position_m=(0.0, 0.0),
        destination_m=(0.0, 0.0),
    )
    far_expensive_space = ParkingSpace("bad_fit", "A", 240.0, 0.0, price_per_hour=9.0)

    result = DeterministicUtilityModel().evaluate_candidates(strict_context, [far_expensive_space])

    assert result.chosen_action == "continue"
    assert result.diagnostics["reason"] == "below_acceptance_threshold"
