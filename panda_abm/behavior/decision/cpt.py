"""M2 CPT-enhanced random utility model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from panda_abm.behavior.decision.base import CandidateEvaluation, DecisionContext, DecisionResult
from panda_abm.behavior.decision.random_utility import RandomUtilityModel
from panda_abm.behavior.decision.transforms import FEATURE_SPECS, stable_softmax
from panda_abm.environment.parking_space import ParkingSpace

__author__ = "Judith Njoku"


@dataclass(frozen=True)
class CPTParameters:
    """Literature-prior placeholders, not site-calibrated PANDA parameters."""

    alpha: float = 0.88
    beta: float = 0.88
    lambda_loss: float = 2.25
    gamma: float = 0.61


def cpt_value(delta: float, alpha: float = 0.88, beta: float = 0.88, lambda_loss: float = 2.25) -> float:
    """Reference-dependent CPT value function."""

    if delta >= 0:
        return float(delta**alpha)
    return float(-lambda_loss * ((-delta) ** beta))


def probability_weight(p: float, gamma: float = 0.61) -> float:
    """Prelec/Tversky-Kahneman style probability weighting function."""

    if not 0.0 <= p <= 1.0:
        raise ValueError("Probability must be within [0, 1]")
    if p in (0.0, 1.0):
        return float(p)
    numerator = p**gamma
    denominator = (p**gamma + (1.0 - p) ** gamma) ** (1.0 / gamma)
    return float(np.clip(numerator / denominator, 0.0, 1.0))


class CPTDecisionModel:
    """CPT-enhanced RUM using reference-dependent walk/search components."""

    model_name = "cpt"

    def __init__(self, cpt_parameters: CPTParameters | None = None):
        self.cpt_parameters = cpt_parameters or CPTParameters()

    def evaluate_candidates(
        self,
        context: DecisionContext,
        candidates: list[ParkingSpace],
        perceived_state: object | None = None,
        forecast: object | None = None,
    ) -> DecisionResult:
        base = RandomUtilityModel(epsilon_scale=0.0).evaluate_candidates(context, candidates, perceived_state, forecast)
        cpt_evaluations: list[CandidateEvaluation] = []
        params = context.behavioral_parameters
        refs = context.reference_points
        cp = self.cpt_parameters

        for item in base.candidate_evaluations:
            features = dict(item.features)
            diagnostics = dict(item.diagnostics)
            utility = item.utility

            walk_delta = refs.r_walk_m - features["walking_distance_m"]
            search_delta = refs.r_search_s - features["search_time_s"]
            walk_cpt = cpt_value(walk_delta / FEATURE_SPECS["walking_distance_m"].scale, cp.alpha, cp.beta, cp.lambda_loss)
            search_cpt = cpt_value(search_delta / FEATURE_SPECS["search_time_s"].scale, cp.alpha, cp.beta, cp.lambda_loss)

            utility += params.beta_walk * walk_cpt
            utility += params.beta_search * search_cpt

            raw_availability = features["availability_probability"]
            weighted_availability = probability_weight(raw_availability, cp.gamma)
            utility += params.beta_availability * (weighted_availability - raw_availability)

            diagnostics.update(
                {
                    "r_walk_m": refs.r_walk_m,
                    "r_search_s": refs.r_search_s,
                    "walk_delta_m": walk_delta,
                    "search_delta_s": search_delta,
                    "walk_cpt_value": walk_cpt,
                    "search_cpt_value": search_cpt,
                    "raw_availability_probability": raw_availability,
                    "weighted_availability_probability": weighted_availability,
                }
            )
            cpt_evaluations.append(CandidateEvaluation(item.space_id, item.feasible, float(utility), features, diagnostics))

        feasible = [item for item in cpt_evaluations if item.feasible]
        if not feasible:
            return DecisionResult("continue", None, None, tuple(cpt_evaluations), diagnostics={"reason": "no_feasible_candidates"})

        utilities = np.array([item.utility for item in feasible], dtype=float)
        probs = stable_softmax(utilities, temperature=params.decision_temperature)
        rng = np.random.default_rng(context.rng_seed)
        picked = feasible[int(rng.choice(np.arange(len(feasible)), p=probs))]
        probabilities = {item.space_id: float(prob) for item, prob in zip(feasible, probs)}
        threshold = params.acceptance_utility_threshold
        if picked.utility < threshold:
            return DecisionResult(
                "continue",
                None,
                None,
                tuple(cpt_evaluations),
                probabilities,
                diagnostics={
                    "reason": "below_acceptance_threshold",
                    "sampled_space_id": picked.space_id,
                    "sampled_utility": picked.utility,
                    "acceptance_threshold": threshold,
                },
            )
        return DecisionResult("park", picked.space_id, picked.utility, tuple(cpt_evaluations), probabilities)
