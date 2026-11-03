"""Frozen driver population specifications.

Author: Judith Njoku
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from panda_abm.behavior.parameters import BehavioralParameters
from panda_abm.behavior.references import ReferencePoints
from panda_abm.behavior.cpt_parameters import CPTParameters

__author__ = "Judith Njoku"


@dataclass(frozen=True)
class DriverAttributes:
    """Observable driver/trip attributes independent of decision model."""

    driver_id: str
    destination_x_m: float
    destination_y_m: float
    persona: str | None = None  # Descriptive metadata only; primary generation leaves it unset.
    trip_purpose: str = "shopping"
    expected_dwell_duration_s: int = 1800
    arrival_time_s: int = 0
    local_familiarity: float = 0.5
    accessibility_eligibility: bool = False
    mobility_limitation: bool = False
    max_walking_distance_m: float | None = None
    permit_type: str | None = None
    vehicle_type: str = "sedan"
    vehicle_occupancy: int = 1
    trip_urgency: float = 0.5
    value_of_time: float = 1.0
    guidance_access: bool = False
    previous_parking_experience: dict[str, Any] | None = None
    arrival_exit_id: str | None = None
    preferred_exit_id: str | None = None
    walmart_door_id: str | None = None

    @property
    def destination(self) -> tuple[float, float]:
        return (self.destination_x_m, self.destination_y_m)


@dataclass(frozen=True)
class DriverSpec:
    """Frozen reusable specification for constructing one driver agent."""

    attributes: DriverAttributes
    behavioral_parameters: BehavioralParameters
    reference_points: ReferencePoints
    cpt_parameters: CPTParameters | None = None
    cpt_parameter_source: str = 'shared_tk92_benchmark'

    @property
    def driver_id(self) -> str:
        return self.attributes.driver_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "attributes": asdict(self.attributes),
            "behavioral_parameters": self.behavioral_parameters.as_dict(),
            "reference_points": self.reference_points.as_dict(),
            "cpt_parameters": self.cpt_parameters.as_dict() if self.cpt_parameters is not None else None,
            "cpt_parameter_source": self.cpt_parameter_source,
        }


@dataclass(frozen=True)
class PopulationSpec:
    """Frozen population reusable across M0/M1/M2 experiments."""

    population_id: str
    seed: int
    drivers: tuple[DriverSpec, ...]
    generation_notes: str = "synthetic structural placeholder"
    generation_method: str = 'legacy_or_explicit'
    parameterization: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "population_id": self.population_id,
            "generation_method": self.generation_method,
            "parameterization": self.parameterization,
            "seed": self.seed,
            "generation_notes": self.generation_notes,
            "drivers": [driver.as_dict() for driver in self.drivers],
        }
