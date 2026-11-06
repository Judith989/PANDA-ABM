"""Feature construction, orientation, and softmax utilities."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from panda_abm.behavior.parameters import BehavioralParameters
from panda_abm.environment.parking_space import ParkingSpace

__author__ = "Judith Njoku"


@dataclass(frozen=True)
class FeatureSpec:
    """Feature metadata used for orientation and normalization."""

    name: str
    direction: int
    scale: float
    weight_name: str
    description: str


FEATURE_SPECS: dict[str, FeatureSpec] = {
    "approach_time_s": FeatureSpec("approach_time_s", -1, 120., "beta_approach", "Estimated time to reach the candidate from the current position"),
    "accessibility_match": FeatureSpec("accessibility_match", 1, 1., "beta_accessibility", "Accessible space for an eligible driver"),
    "exit_distance_m": FeatureSpec("exit_distance_m", -1, 300.0, "beta_exit", "Straight-line distance to the driver's preferred parking-lot exit"),
    "walking_distance_m": FeatureSpec("walking_distance_m", -1, 250.0, "beta_walk", "Walking distance to destination"),
    "price_per_hour": FeatureSpec("price_per_hour", -1, 10.0, "beta_price", "Parking price"),
    "search_time_s": FeatureSpec("search_time_s", -1, 600.0, "beta_search", "Accumulated search time"),
    "rule_risk": FeatureSpec("rule_risk", -1, 1.0, "beta_risk", "Regulatory or enforcement risk"),
    "availability_probability": FeatureSpec(
        "availability_probability", 1, 1.0, "beta_availability", "Believed availability probability"
    ),
    "familiarity": FeatureSpec("familiarity", 1, 1.0, "beta_familiarity", "Driver familiarity with the space/module"),
}


def euclidean_distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def normalize_feature(value: float, spec: FeatureSpec) -> float:
    if spec.scale <= 0:
        raise ValueError(f"Feature scale must be positive for {spec.name}")
    return float(np.clip(value / spec.scale, 0.0, 1.0))


def oriented_feature(value: float, spec: FeatureSpec) -> float:
    """Normalize and orient a feature so higher is always better."""

    normalized = normalize_feature(value, spec)
    if spec.direction == 1:
        return normalized
    if spec.direction == -1:
        return 1.0 - normalized
    raise ValueError(f"Feature direction must be +1 or -1 for {spec.name}")


def stable_softmax(values: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """Numerically stable softmax with configurable temperature."""

    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError("stable_softmax expects a 1D array")
    if len(arr) == 0:
        return arr
    temp = max(float(temperature), 1e-12)
    scaled = arr / temp
    scaled = scaled - np.max(scaled)
    exps = np.exp(scaled)
    return exps / exps.sum()


def build_candidate_features(
    candidate: ParkingSpace,
    destination_m: tuple[float, float],
    accumulated_search_time_s: float,
    familiarity: float,
    availability_probability: float | None = None,
    rule_risk: float | None = None,
    preferred_exit_id: str | None = None,
    current_position_m: tuple[float, float] = (0., 0.),
    search_speed_m_per_s: float = 5.,
    accessibility_eligibility: bool = False,
) -> dict[str, float]:
    """Construct raw candidate features with explicit units."""

    return {
        "approach_time_s": euclidean_distance_m(current_position_m, (candidate.x_m, candidate.y_m)) / max(search_speed_m_per_s, 1e-9),
        "accessibility_match": float(candidate.accessible and accessibility_eligibility),
        "exit_distance_m": (
            candidate.exit_distance(preferred_exit_id) or 0.0
            if preferred_exit_id else 0.0
        ),
        "walking_distance_m": euclidean_distance_m((candidate.x_m, candidate.y_m), destination_m),
        "price_per_hour": float(candidate.price_per_hour),
        "search_time_s": float(accumulated_search_time_s),
        "rule_risk": float(0.0 if rule_risk is None else rule_risk),
        "availability_probability": float(1.0 if availability_probability is None else availability_probability),
        "familiarity": float(familiarity),
    }


def linear_utility(features: dict[str, float], params: BehavioralParameters) -> float:
    """Compute oriented linear utility where each feature is higher-is-better."""

    utility = 0.0
    for name, spec in FEATURE_SPECS.items():
        weight = float(getattr(params, spec.weight_name))
        utility += weight * oriented_feature(features[name], spec)
    return utility
