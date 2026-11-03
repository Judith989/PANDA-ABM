"""Continuation value for accept-versus-search decisions.

Author: Judith Njoku
"""

from __future__ import annotations

from dataclasses import dataclass

from panda_abm.behavior.decision.base import DecisionContext

__author__ = "Judith Njoku"


@dataclass(frozen=True)
class SimpleContinuationModel:
    """Legacy heuristic retained for compatibility.

    CPTDecisionModel now compares explicit continuation and parking prospects;
    this heuristic is not part of its cumulative-prospect calculation.
    """

    opportunity_weight: float = 0.45
    time_penalty_weight: float = 0.35

    def value(self, context: DecisionContext, candidate_count: int) -> float:
        opportunity = min(candidate_count / 10.0, 1.0)
        search_burden = min(context.accumulated_search_time_s / 600.0, 1.0)
        return self.opportunity_weight * opportunity - self.time_penalty_weight * search_burden
