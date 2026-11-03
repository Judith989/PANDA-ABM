"""Reference-point structures for CPT-capable decision models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from statistics import median


@dataclass
class ReferencePoints:
    """Reference values and optional drift controls.

    Reference drift is disabled by default. This keeps mobility constraints and
    reference assumptions explicit rather than smuggled into every run.
    """

    r_walk_m: float = 120.0
    r_search_s: float = 300.0
    kappa_walk: float = 0.0
    kappa_search: float = 0.0
    drift_enabled: bool = False
    r_exit_m: float = 0.0
    distance_reference_policy: str = "explicit"
    reference_space_count: int = 0

    def update(self, observed_walk_m: float | None = None, observed_search_s: float | None = None) -> None:
        if not self.drift_enabled:
            return
        if observed_walk_m is not None:
            self.r_walk_m = (1.0 - self.kappa_walk) * self.r_walk_m + self.kappa_walk * observed_walk_m
        if observed_search_s is not None:
            self.r_search_s = (1.0 - self.kappa_search) * self.r_search_s + self.kappa_search * observed_search_s

    def as_dict(self) -> dict[str, float | bool | str | int]:
        return asdict(self)


def lot_distance_references(facility, attributes, references: ReferencePoints) -> ReferencePoints:
    """Fixed median expectations from the driver's legal, physically usable inventory.

    Uses static geometry, never occupancy or the current candidate set. This is
    a transparent prior, not an empirically calibrated expectation. Explicit
    ReferencePoints supplied directly to a population remain supported.
    """
    walks, exits = [], []
    for space in facility.spaces:
        if space.unavailable or not space.is_compatible_with_vehicle(attributes.vehicle_type):
            continue
        if space.accessible and not attributes.accessibility_eligibility:
            continue
        if space.reserved_type and attributes.permit_type != (space.permit_requirement or space.reserved_type):
            continue
        walk = math.dist((space.x_m, space.y_m), attributes.destination)
        if attributes.max_walking_distance_m is not None and walk > attributes.max_walking_distance_m:
            continue
        walks.append(walk)
        if attributes.preferred_exit_id:
            distance = getattr(space, f'distance_to_{attributes.preferred_exit_id}_m', None)
            if distance is None and attributes.preferred_exit_id in facility.exit_point_ids:
                point = facility.exit_points[facility.exit_point_ids.index(attributes.preferred_exit_id)]
                distance = math.dist((space.x_m, space.y_m), point)
            if distance is not None:
                exits.append(float(distance))
    return replace(references,
        r_walk_m=float(median(walks)) if walks else references.r_walk_m,
        r_exit_m=float(median(exits)) if exits else references.r_exit_m,
        distance_reference_policy='legal_inventory_median' if walks else 'no_usable_inventory_fallback',
        reference_space_count=len(walks))
