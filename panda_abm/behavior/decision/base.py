"""Common decision-model interface.

All decision models receive equivalent candidate information and return the same
result shape. This is the key fairness constraint for M0/M1/M2 comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from panda_abm.behavior.parameters import BehavioralParameters
from panda_abm.behavior.references import ReferencePoints
from panda_abm.behavior.cpt_parameters import CPTParameters
from panda_abm.environment.parking_space import ParkingSpace

__author__ = "Judith Njoku"


@dataclass(frozen=True)
class DecisionContext:
    """Information available to a decision model at one search step."""

    driver_id: str
    behavioral_parameters: BehavioralParameters
    reference_points: ReferencePoints
    accumulated_search_time_s: float
    current_position_m: tuple[float, float]
    destination_m: tuple[float, float]
    vehicle_type: str = "sedan"
    accessibility_eligibility: bool = False
    permit_type: str | None = None
    familiarity: float = 0.5
    allow_illegal_alternatives: bool = False
    rng_seed: int | None = None
    preferred_exit_id: str | None = None
    search_speed_m_per_s: float = 5.0
    max_walking_distance_m: float | None = None
    approach_times_s: dict[str, float] = field(default_factory=dict)
    availability_probabilities: dict[str, float] = field(default_factory=dict)
    decision_interval_s: float = 10.0
    failure_delay_s: float = 30.0
    continuation_outcomes: tuple[tuple[float, float], ...] | None = None
    remaining_search_time_s: float | None = None
    cpt_parameters: CPTParameters | None = None


@dataclass(frozen=True)
class CandidateEvaluation:
    """Utility/value record for one parking candidate."""

    space_id: str
    feasible: bool
    utility: float
    features: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionResult:
    """Model-independent decision result."""

    chosen_action: str
    chosen_space_id: str | None
    chosen_utility: float | None
    candidate_evaluations: tuple[CandidateEvaluation, ...]
    probabilities: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, float | str | int | bool] = field(default_factory=dict)

    def evaluations_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "space_id": item.space_id,
                "feasible": item.feasible,
                "utility": item.utility,
                **{f"feature_{k}": v for k, v in item.features.items()},
                **{f"diagnostic_{k}": v for k, v in item.diagnostics.items()},
            }
            for item in self.candidate_evaluations
        )


class DecisionModel(Protocol):
    """Protocol implemented by M0, M1, and M2."""

    model_name: str

    def evaluate_candidates(
        self,
        context: DecisionContext,
        candidates: list[ParkingSpace],
        perceived_state: object | None = None,
        forecast: object | None = None,
    ) -> DecisionResult:
        ...
