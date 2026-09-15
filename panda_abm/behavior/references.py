"""Reference-point structures for CPT-capable decision models."""

from __future__ import annotations

from dataclasses import asdict, dataclass


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

    def update(self, observed_walk_m: float | None = None, observed_search_s: float | None = None) -> None:
        if not self.drift_enabled:
            return
        if observed_walk_m is not None:
            self.r_walk_m = (1.0 - self.kappa_walk) * self.r_walk_m + self.kappa_walk * observed_walk_m
        if observed_search_s is not None:
            self.r_search_s = (1.0 - self.kappa_search) * self.r_search_s + self.kappa_search * observed_search_s

    def as_dict(self) -> dict[str, float | bool]:
        return asdict(self)
