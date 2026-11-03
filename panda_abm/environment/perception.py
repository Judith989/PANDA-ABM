"""Driver perception of the parking environment.

Author: Judith Njoku
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from panda_abm.environment.facility import Facility
from panda_abm.environment.parking_space import ParkingSpace

__author__ = "Judith Njoku"


@dataclass(frozen=True)
class PerceivedSpace:
    """What a driver currently believes about one observed space."""

    space: ParkingSpace
    distance_from_driver_m: float
    true_occupied: bool
    perceived_available: bool
    forecast_available_probability: float | None = None
    information_source: str = 'local'
    observed_at_s: float | None = None


class RadiusPerception:
    """Drivers see nearby spaces, plus optional forecast information."""

    def __init__(self, radius_m: float = 60.0):
        self.radius_m = radius_m

    def observe(self, model, agent) -> list[PerceivedSpace]:
        observations: list[PerceivedSpace] = []
        forecast = model.forecast_provider.forecast(model, agent) if agent.attributes.guidance_access else {}
        for space in model.facility.spaces:
            dist = math.hypot(space.x_m - agent.x_m, space.y_m - agent.y_m)
            if dist > self.radius_m:
                continue
            state = model.resource_manager.states[space.space_id]
            probability = forecast.get(space.space_id)
            observations.append(
                PerceivedSpace(
                    space=space,
                    distance_from_driver_m=dist,
                    true_occupied=state.occupied,
                    perceived_available=(not state.occupied) and (not state.unavailable),
                    forecast_available_probability=probability,
                    observed_at_s=model.clock_s,
                )
            )
        return observations


class SpaceInformationPerception:
    """Accurate current space reports, refreshed at a searching driver's scan.

    This exposes current occupancy beyond visibility, never future availability
    or another driver's intention. It neither reserves spaces nor updates a
    committed target while travelling. Legacy forecast providers are separate.
    """
    def observe(self,model,agent):
        return [PerceivedSpace(space=s,distance_from_driver_m=math.dist((s.x_m,s.y_m),(agent.x_m,agent.y_m)),
            true_occupied=model.space_states[s.space_id].occupied,
            perceived_available=not(model.space_states[s.space_id].occupied or model.space_states[s.space_id].unavailable),
            information_source='space_report',observed_at_s=model.clock_s) for s in model.facility.spaces]
