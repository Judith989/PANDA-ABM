"""Choice-set construction for parking alternatives.

Author: Judith Njoku
"""

from __future__ import annotations

import math

from panda_abm.environment.perception import PerceivedSpace
from panda_abm.environment.parking_space import ParkingSpace

__author__ = "Judith Njoku"


class ChoiceSetBuilder:
    """Applies hard rules before the decision model sees alternatives."""

    def __init__(self, allow_illegal_alternatives: bool = False):
        self.allow_illegal_alternatives = allow_illegal_alternatives

    def build(self, agent, observations: list[PerceivedSpace]) -> list[ParkingSpace]:
        feasible: list[ParkingSpace] = []
        for observed in observations:
            space = observed.space
            if not observed.perceived_available:
                continue
            if not space.is_compatible_with_vehicle(agent.attributes.vehicle_type):
                continue
            if space.accessible and not agent.attributes.accessibility_eligibility and not self.allow_illegal_alternatives:
                continue
            required_permit = space.permit_requirement or space.reserved_type
            if space.reserved_type and agent.attributes.permit_type != required_permit and not self.allow_illegal_alternatives:
                continue
            if agent.attributes.max_walking_distance_m is not None:
                walk = math.hypot(
                    space.x_m - agent.attributes.destination_x_m,
                    space.y_m - agent.attributes.destination_y_m,
                )
                if walk > agent.attributes.max_walking_distance_m:
                    continue
            feasible.append(space)
        return feasible
