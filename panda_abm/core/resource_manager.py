"""Parking resource claims and releases.

Author: Judith Njoku
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from panda_abm.environment.parking_space import ParkingSpaceState

if TYPE_CHECKING:
    from panda_abm.environment.facility import Facility

__author__ = "Judith Njoku"


class ParkingResourceManager:
    """Owns parking occupancy so drivers cannot accidentally double park."""

    def __init__(self, facility: Facility, initial_states: dict[str, ParkingSpaceState]):
        self.facility = facility
        self.states = initial_states
        self._usable_ids = tuple(s.space_id for s in facility.spaces if not s.unavailable)

    def is_available(self, space_id: str) -> bool:
        state = self.states[space_id]
        return (not state.unavailable) and (not state.occupied)

    def occupant(self, space_id: str) -> str | None:
        return self.states[space_id].occupant_id

    def claim_space(self, agent_id: str, space_id: str) -> bool:
        state = self.states[space_id]
        if state.unavailable or state.occupied:
            return False
        state.mark_occupied(agent_id)
        return True

    def release_space(self, agent_id: str, space_id: str) -> bool:
        state = self.states[space_id]
        if state.occupant_id != agent_id:
            return False
        state.release()
        return True

    def usable_count(self) -> int:
        # Fixed physical inventory: closing an occupied bay must not make its
        # vehicle disappear from occupancy or silently change the denominator.
        return len(self._usable_ids)

    def occupied_count(self) -> int:
        return sum(self.states[sid].occupied for sid in self._usable_ids)

    def occupancy_rate(self) -> float:
        usable = self.usable_count()
        return 0.0 if usable == 0 else self.occupied_count() / usable
