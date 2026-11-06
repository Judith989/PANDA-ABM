"""Parking-facility domain object and small synthetic demo generator.

Author: Judith Njoku
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import math
from pathlib import Path
import json

import numpy as np

from panda_abm.core.states import SpaceType
from panda_abm.environment.coordinates import lat_lon_to_local_m
from panda_abm.environment.parking_space import (
    ParkingSpace,
    ParkingSpaceState,
    parking_space_from_lot_config_slot,
)



@dataclass(frozen=True)
class Facility:
    """Immutable parking facility layout."""

    facility_id: str
    name: str
    spaces: tuple[ParkingSpace, ...]
    entry_points: tuple[tuple[float, float], ...]
    exit_points: tuple[tuple[float, float], ...]
    coordinate_system: str = "local_m"
    synthetic: bool = False
    walmart_doors: tuple[tuple[float, float], ...] = ()
    entry_point_ids: tuple[str, ...] = ()
    exit_point_ids: tuple[str, ...] = ()
    walmart_door_ids: tuple[str, ...] = ()

    aisle_network: dict | None = None
    pedestrian_network: dict | None = None

    @cached_property
    def walking_network(self):
        from panda_abm.environment.pedestrian_navigation import PedestrianNetwork
        return PedestrianNetwork(self.pedestrian_network) if self.pedestrian_network is not None else None

    def walking_distance(self,space,attributes):
        if self.walking_network is None:return math.dist((space.x_m,space.y_m),attributes.destination)
        return self.walking_network.distance(space.space_id,attributes.walmart_door_id)

    def walking_route(self,space,attributes):
        return self.walking_network.route(space.space_id,attributes.walmart_door_id) if self.walking_network is not None else None


    @property
    def space_by_id(self) -> dict[str, ParkingSpace]:
        return {space.space_id: space for space in self.spaces}

    @property
    def module_ids(self) -> tuple[str, ...]:
        return tuple(sorted({space.module_id for space in self.spaces}))

    def initial_space_states(self) -> dict[str, ParkingSpaceState]:
        return {space.space_id: ParkingSpaceState.from_space(space) for space in self.spaces}


def generate_synthetic_facility(seed: int = 42) -> Facility:
    """Create the tested small synthetic demo facility.

    The facility here has 36 spaces across three modules. It is deliberately tiny so
    tests and examples stay fast while exercising modules, restrictions, and
    local metric coordinates.
    """

    rng = np.random.default_rng(seed)
    spaces: list[ParkingSpace] = []
    modules = ("A", "B", "C")
    idx = 0
    for module_i, module_id in enumerate(modules):
        base_x = module_i * 40.0
        for row in range(3):
            for col in range(4):
                is_accessible = row == 0 and col == 0
                is_reserved = row == 0 and col == 1
                unavailable = bool(rng.random() < 0.08)
                spaces.append(
                    ParkingSpace(
                        space_id=f"S{idx:03d}",
                        module_id=module_id,
                        x_m=base_x + col * 3.0,
                        y_m=row * 6.0,
                        space_type=(
                            SpaceType.ACCESSIBLE
                            if is_accessible
                            else SpaceType.RESERVED
                            if is_reserved
                            else SpaceType.REGULAR
                        ),
                        accessible=is_accessible,
                        reserved_type="permit" if is_reserved else None,
                        permit_requirement="accessible" if is_accessible else "reserved" if is_reserved else None,
                        price_per_hour=float(1.0 + 0.4 * module_i + 0.1 * row),
                        unavailable=unavailable,
                    )
                )
                idx += 1

    return Facility(
        facility_id="synthetic_demo",
        name="Synthetic Demo Parking Facility",
        spaces=tuple(spaces),
        entry_points=((0.0, -8.0),),
        exit_points=((95.0, -8.0),),
        synthetic=True,
    )


def load_facility_from_lot_config(path: str | Path) -> Facility:
    """Here we will load the existing PANDA lot_config.json into Stage A domain objects."""

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if raw.get('pedestrian_network') is not None:
        from panda_abm.twin.environments import validate_environment,facility_from_environment
        return facility_from_environment(validate_environment(raw))
    spaces = tuple(parking_space_from_lot_config_slot(slot) for slot in raw["slots"])
    meta = raw.get("meta", {})
    def local_points(key: str) -> tuple[tuple[float, float], ...]:
        return tuple(
            lat_lon_to_local_m(float(p["lat"]), float(p["lon"]), float(meta["ref_lat"]), float(meta["ref_lon"]))
            for p in raw.get(key, [])
        )

    entry_points = local_points("entry_points")
    exit_points = local_points("exit_points")
    return Facility(
        facility_id=str(meta.get("lot_name", "panda_lot")).lower().replace(" ", "_"),
        name=str(meta.get("lot_name", "PANDA Facility")),
        spaces=spaces,
        entry_points=entry_points,
        exit_points=exit_points,
        coordinate_system="local_m",
        synthetic=False,
        walmart_doors=local_points("walmart_doors"),
        entry_point_ids=tuple(p["id"] for p in raw.get("entry_points", [])),
        exit_point_ids=tuple(p["id"] for p in raw.get("exit_points", [])),
        walmart_door_ids=tuple(p["id"] for p in raw.get("walmart_doors", [])),
    )
