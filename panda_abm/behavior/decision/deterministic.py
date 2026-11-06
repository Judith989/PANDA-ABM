"""M0 deterministic generalized utility baseline."""

from __future__ import annotations

from panda_abm.behavior.decision.base import CandidateEvaluation, DecisionContext, DecisionResult
from panda_abm.behavior.decision.transforms import build_candidate_features, linear_utility
from panda_abm.environment.parking_space import ParkingSpace

__author__ = "Judith Njoku"


class DeterministicUtilityModel:
    """Choose the feasible candidate with maximum deterministic utility."""

    model_name = "deterministic"

    def evaluate_candidates(
        self,
        context: DecisionContext,
        candidates: list[ParkingSpace],
        perceived_state: object | None = None,
        forecast: object | None = None,
    ) -> DecisionResult:
        evaluations: list[CandidateEvaluation] = []
        for candidate in candidates:
            feasible = (not candidate.unavailable) and candidate.is_compatible_with_vehicle(context.vehicle_type)
            if candidate.accessible and not context.accessibility_eligibility:
                feasible = feasible and context.allow_illegal_alternatives
            required_permit = candidate.permit_requirement or candidate.reserved_type
            if candidate.reserved_type and context.permit_type != required_permit:
                feasible = feasible and context.allow_illegal_alternatives
            rule_violation = (
                candidate.accessible and not context.accessibility_eligibility
            ) or (bool(candidate.reserved_type) and context.permit_type != required_permit)

            features = build_candidate_features(
                candidate,
                destination_m=context.destination_m,
                accumulated_search_time_s=context.accumulated_search_time_s,
                familiarity=context.familiarity,
                preferred_exit_id=context.preferred_exit_id,
                current_position_m=context.current_position_m,
                search_speed_m_per_s=context.search_speed_m_per_s,
                accessibility_eligibility=context.accessibility_eligibility,
                rule_risk=float(rule_violation),
                availability_probability=context.availability_probabilities.get(candidate.space_id, 1.0),
            )
            if candidate.space_id in context.walking_distances_m:
                features['walking_distance_m']=context.walking_distances_m[candidate.space_id]
            if candidate.space_id in context.approach_times_s:
                features['approach_time_s'] = context.approach_times_s[candidate.space_id]
            if context.remaining_search_time_s is not None:
                feasible = feasible and features['approach_time_s'] < context.remaining_search_time_s
            if context.max_walking_distance_m is not None:
                feasible = feasible and features["walking_distance_m"] <= context.max_walking_distance_m
            utility = linear_utility(features, context.behavioral_parameters)
            evaluations.append(CandidateEvaluation(candidate.space_id, feasible, utility, features))

        feasible_evals = [item for item in evaluations if item.feasible]
        if not feasible_evals:
            return DecisionResult("continue", None, None, tuple(evaluations), diagnostics={"reason": "no_feasible_candidates"})

        chosen = max(feasible_evals, key=lambda item: item.utility)
        threshold = context.behavioral_parameters.acceptance_utility_threshold
        if chosen.utility < threshold:
            return DecisionResult(
                "continue",
                None,
                None,
                tuple(evaluations),
                diagnostics={
                    "reason": "below_acceptance_threshold",
                    "best_space_id": chosen.space_id,
                    "best_utility": chosen.utility,
                    "acceptance_threshold": threshold,
                },
            )
        return DecisionResult("park", chosen.space_id, chosen.utility, tuple(evaluations))
