"""Factories for reproducible driver populations.

Author: Judith Njoku
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from panda_abm.behavior.parameters import BehavioralParameters, parameters_for_persona
from panda_abm.behavior.population import DriverAttributes, DriverSpec, PopulationSpec
from panda_abm.behavior.references import ReferencePoints
from panda_abm.environment.facility import Facility

__author__ = "Judith Njoku"


def make_population(
    facility: Facility,
    size: int = 12,
    seed: int = 42,
    heterogeneous: bool = True,
    population_id: str | None = None,
) -> PopulationSpec:
    """Create a frozen population that can be reused across M0, M1, and M2."""

    rng = np.random.default_rng(seed)
    entry = facility.entry_points[0] if facility.entry_points else (0.0, 0.0)
    module_centers = _module_centers(facility)
    module_ids = sorted(module_centers)
    drivers: list[DriverSpec] = []

    persona = "convenience_seeker"
    base_params = parameters_for_persona(persona)
    for i in range(size):
        module_id = module_ids[i % len(module_ids)]
        dest_x, dest_y = module_centers[module_id]
        attrs = DriverAttributes(
            driver_id=f"D{i:04d}",
            destination_x_m=float(dest_x + rng.normal(0.0, 2.0)),
            destination_y_m=float(dest_y + rng.normal(0.0, 2.0)),
            persona=persona,
            trip_purpose="shopping",
            expected_dwell_duration_s=int(rng.integers(900, 3600)),
            arrival_time_s=int(i * 20),
            local_familiarity=float(np.clip(rng.normal(0.55, 0.18), 0.0, 1.0)),
            accessibility_eligibility=bool(rng.random() < 0.08),
            mobility_limitation=bool(rng.random() < 0.10),
            max_walking_distance_m=float(rng.choice([80.0, 120.0, 200.0])) if rng.random() < 0.12 else None,
            permit_type=None,
            vehicle_type=str(rng.choice(["sedan", "compact", "suv", "van", "truck"], p=[0.42, 0.18, 0.24, 0.10, 0.06])),
            vehicle_occupancy=int(rng.integers(1, 5)),
            trip_urgency=float(np.clip(rng.beta(2.0, 2.0), 0.0, 1.0)),
            value_of_time=float(np.clip(rng.lognormal(mean=0.0, sigma=0.25), 0.4, 2.2)),
            guidance_access=False,
        )

        if attrs.accessibility_eligibility:
            attrs = replace(attrs, permit_type="accessible")

        if heterogeneous:
            params = BehavioralParameters(
                beta_walk=float(np.clip(rng.normal(base_params.beta_walk, 0.20), 0.05, 2.5)),
                beta_price=float(np.clip(rng.normal(base_params.beta_price, 0.10), 0.0, 1.5)),
                beta_search=float(np.clip(rng.normal(base_params.beta_search, 0.15), 0.05, 2.0)),
                beta_availability=float(np.clip(rng.normal(base_params.beta_availability, 0.18), 0.05, 2.0)),
                beta_risk=float(np.clip(rng.normal(base_params.beta_risk, 0.15), 0.0, 2.0)),
                beta_patience=float(np.clip(rng.normal(base_params.beta_patience, 0.12), 0.0, 2.0)),
                beta_proximity=float(np.clip(rng.normal(base_params.beta_proximity, 0.12), 0.0, 2.0)),
                beta_curb=0.0,
                beta_familiarity=float(np.clip(rng.normal(base_params.beta_familiarity, 0.15), 0.0, 1.5)),
                beta_learning=0.0,
                beta_guidance=0.0,
                beta_compliance=float(np.clip(rng.normal(base_params.beta_compliance, 0.12), 0.0, 1.0)),
                beta_enforcement=float(np.clip(rng.normal(base_params.beta_enforcement, 0.15), 0.0, 2.0)),
                decision_temperature=float(np.clip(rng.normal(base_params.decision_temperature, 0.08), 0.05, 1.5)),
                acceptance_utility_threshold=float(
                    np.clip(rng.normal(base_params.acceptance_utility_threshold, 0.12), 0.5, 3.0)
                ),
            )
        else:
            params = base_params

        refs = ReferencePoints(
            r_walk_m=float(np.clip(rng.normal(120.0, 25.0), 50.0, 250.0)),
            r_search_s=float(np.clip(rng.normal(300.0, 75.0), 60.0, 900.0)),
            kappa_walk=0.0,
            kappa_search=0.0,
            drift_enabled=False,
        )
        drivers.append(DriverSpec(attrs, params, refs))

    return PopulationSpec(
        population_id=population_id or f"pop_{'het' if heterogeneous else 'hom'}_{size}_{seed}",
        seed=seed,
        drivers=tuple(drivers),
        generation_notes="synthetic population for reproducible Milestone 1 experiments",
    )


def _module_centers(facility: Facility) -> dict[str, tuple[float, float]]:
    centers: dict[str, tuple[list[float], list[float]]] = {}
    for space in facility.spaces:
        xs, ys = centers.setdefault(space.module_id, ([], []))
        xs.append(space.x_m)
        ys.append(space.y_m)
    return {module: (float(np.mean(xs)), float(np.mean(ys))) for module, (xs, ys) in centers.items()}
