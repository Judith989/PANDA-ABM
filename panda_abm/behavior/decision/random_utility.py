"""M1 heterogeneous random utility model."""

from __future__ import annotations

import numpy as np

from panda_abm.behavior.decision.base import CandidateEvaluation, DecisionContext, DecisionResult
from panda_abm.behavior.decision.deterministic import DeterministicUtilityModel
from panda_abm.behavior.decision.transforms import stable_softmax
from panda_abm.environment.parking_space import ParkingSpace

__author__ = "Judith Njoku"


class RandomUtilityModel:
    """Sample a feasible candidate with logit/softmax choice probabilities."""

    model_name = "rum"

    def __init__(self, epsilon_scale: float = 0.0):
        self.epsilon_scale = epsilon_scale

    def evaluate_candidates(
        self,
        context: DecisionContext,
        candidates: list[ParkingSpace],
        perceived_state: object | None = None,
        forecast: object | None = None,
    ) -> DecisionResult:
        base_result = DeterministicUtilityModel().evaluate_candidates(context, candidates, perceived_state, forecast)
        evaluations = list(base_result.candidate_evaluations)
        feasible_indices = [i for i, item in enumerate(evaluations) if item.feasible]
        if not feasible_indices:
            return DecisionResult("continue", None, None, tuple(evaluations), diagnostics={"reason": "no_feasible_candidates"})

        rng = np.random.default_rng(context.rng_seed)
        utilities = np.array([evaluations[i].utility for i in feasible_indices], dtype=float)
        if self.epsilon_scale:
            utilities = utilities + rng.normal(0.0, self.epsilon_scale, size=len(utilities))
            updated = []
            feasible_map = dict(zip(feasible_indices, utilities))
            for i, item in enumerate(evaluations):
                updated.append(
                    CandidateEvaluation(item.space_id, item.feasible, float(feasible_map.get(i, item.utility)), item.features, item.diagnostics)
                )
            evaluations = updated

        probs = stable_softmax(utilities, temperature=context.behavioral_parameters.decision_temperature)
        picked_local = int(rng.choice(np.arange(len(feasible_indices)), p=probs))
        picked_eval = evaluations[feasible_indices[picked_local]]
        probabilities = {evaluations[idx].space_id: float(prob) for idx, prob in zip(feasible_indices, probs)}
        threshold = context.behavioral_parameters.acceptance_utility_threshold
        if picked_eval.utility < threshold:
            return DecisionResult(
                "continue",
                None,
                None,
                tuple(evaluations),
                probabilities,
                diagnostics={
                    "reason": "below_acceptance_threshold",
                    "sampled_space_id": picked_eval.space_id,
                    "sampled_utility": picked_eval.utility,
                    "acceptance_threshold": threshold,
                },
            )
        return DecisionResult("park", picked_eval.space_id, picked_eval.utility, tuple(evaluations), probabilities)
