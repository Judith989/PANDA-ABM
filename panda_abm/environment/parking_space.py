"""Parking-space domain objects.
The Geometry is separated from mutable occupancy so observed, simulated, predicted,
and counterfactual states can reuse the same facility layout.

Author: Judith Njoku
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from panda_abm.core.states import SpaceType


@dataclass(frozen=True)
class ParkingSpace:
    """Immutable parking-space geometry and restrictions.

    Coordinates use local metres when available. Real latitude/longitude can be
    carried beside local x/y for later visualization or geospatial adapters.
    """

    space_id: str
    module_id: str
    x_m: float
    y_m: float
    latitude: float | None = None
    longitude: float | None = None
    space_type: SpaceType = SpaceType.REGULAR
    reserved_type: str | None = None
    accessible: bool = False
    permit_requirement: str | None = None
    price_per_hour: float = 0.0
    unavailable: bool = False
    legal_restrictions: tuple[str, ...] = field(default_factory=tuple)
    network_node_id: str | None = None
    distance_to_door_1_m: float | None = None
    distance_to_door_2_m: float | None = None
    distance_to_exit_a_m: float | None = None
    distance_to_exit_b_m: float | None = None

    def is_compatible_with_vehicle(self, vehicle_type: str) -> bool:
        """Return whether a vehicle type can physically use this space.

        Stage A uses only a conservative placeholder. Later stages can replace
        this with dimensions and turning constraints.
        """

        if self.space_type == SpaceType.LOADING and vehicle_type not in {"van", "truck"}:
            return False
        return True


@dataclass
class ParkingSpaceState:
    """Mutable occupancy/state associated with a parking space."""

    space_id: str
    occupied: bool = False
    occupant_id: str | None = None
    unavailable: bool = False
    observed_status: str | None = None

    def mark_occupied(self, driver_id: str) -> None:
        self.occupied = True
        self.occupant_id = driver_id

    def release(self) -> None:
        self.occupied = False
        self.occupant_id = None

    @classmethod
    def from_space(cls, space: ParkingSpace) -> "ParkingSpaceState":
        return cls(space_id=space.space_id, unavailable=space.unavailable)


def parking_space_from_lot_config_slot(slot: Mapping[str, object]) -> ParkingSpace:
    """Map an existing PANDA lot_config slot dict into the clean domain model."""

    raw_type = str(slot.get("type") or "regular").lower()
    if bool(slot.get("is_accessible")):
        space_type = SpaceType.ACCESSIBLE
    elif bool(slot.get("is_reserved")):
        space_type = SpaceType.RESERVED
    else:
        space_type = SpaceType(raw_type) if raw_type in SpaceType._value2member_map_ else SpaceType.REGULAR

    return ParkingSpace(
        space_id=str(slot["id"]),
        module_id=str(slot.get("module") or slot.get("module_id") or "unknown"),
        x_m=float(slot["local_x_m"]),
        y_m=float(slot["local_y_m"]),
        latitude=float(slot["lat"]) if slot.get("lat") is not None else None,
        longitude=float(slot["lon"]) if slot.get("lon") is not None else None,
        space_type=space_type,
        accessible=bool(slot.get("is_accessible")),
        reserved_type="reserved" if bool(slot.get("is_reserved")) else None,
        unavailable=bool(slot.get("is_blocked")) or bool(slot.get("is_unavailable")),
        price_per_hour=float(slot.get("price_per_hour", 0.0)),
        distance_to_door_1_m=slot.get("distance_to_door_1_m"),
        distance_to_door_2_m=slot.get("distance_to_door_2_m"),
        distance_to_exit_a_m=slot.get("distance_to_exit_a_m"),
        distance_to_exit_b_m=slot.get("distance_to_exit_b_m"),
    )
