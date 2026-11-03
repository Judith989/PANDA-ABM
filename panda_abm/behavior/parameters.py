"""Behavioral parameter vector for generic driver agents.

Author: Judith Njoku
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

__author__ = "Judith Njoku"


@dataclass(frozen=True)
class BehavioralParameters:
    """Continuous behavioral parameters used by decision models.

    Defaults are structural placeholders for Milestone 1, not calibrated PANDA
    or Wyoming values.
    """

    beta_walk: float = 0.90
    beta_price: float = 0.20
    beta_search: float = 0.40
    beta_availability: float = 0.70
    beta_risk: float = 0.60
    beta_patience: float = 0.5
    beta_proximity: float = 0.5
    beta_curb: float = 0.0
    beta_familiarity: float = 0.4
    beta_learning: float = 0.0
    beta_guidance: float = 0.0
    beta_compliance: float = 0.9
    beta_enforcement: float = 0.8
    decision_temperature: float = 0.35
    acceptance_utility_threshold: float = 1.75
    beta_exit: float = 0.0  # Optional preference for proximity to the driver's intended lot exit.
    beta_approach: float = 0.0
    beta_accessibility: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


PERSONA_PARAMETER_PROFILES: dict[str, BehavioralParameters] = {
    "convenience_seeker": BehavioralParameters(
        beta_walk=0.90,
        beta_price=0.20,
        beta_search=0.40,
        beta_risk=0.60,
        beta_availability=0.70,
        beta_familiarity=0.40,
        acceptance_utility_threshold=1.75,
        decision_temperature=0.35,
    ),
    # Experimental profiles. Active weights sum to 3.2, as in the baseline;
    # this limits utility-scale differences from changing acceptance by accident.
    "cost_sensitive": BehavioralParameters(
        beta_walk=.5, beta_price=1.2, beta_search=.4, beta_availability=.6,
        beta_risk=.3, beta_familiarity=.2,
    ),
    "time_sensitive": BehavioralParameters(
        beta_walk=.7, beta_price=.1, beta_search=.8, beta_availability=.6,
        beta_risk=.2, beta_familiarity=.2, beta_approach=.6,
        acceptance_utility_threshold=1.45,
    ),
    "risk_averse": BehavioralParameters(
        beta_walk=.4, beta_price=.1, beta_search=.3, beta_availability=.8,
        beta_risk=1.4, beta_familiarity=.2, decision_temperature=.20,
    ),
    "accessibility_seeking": BehavioralParameters(
        beta_walk=1., beta_price=.1, beta_search=.3, beta_availability=.6,
        beta_risk=.3, beta_familiarity=.2, beta_accessibility=.7,
    ),
}


def parameters_for_persona(persona: str) -> BehavioralParameters:
    """Return the base parameter profile for a named driver persona."""

    try:
        return PERSONA_PARAMETER_PROFILES[persona]
    except KeyError as exc:
        raise ValueError(f"Unknown persona: {persona}") from exc
