"""Factories for reproducible driver populations.

Author: Judith Njoku
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from panda_abm.behavior.parameters import BehavioralParameters, parameters_for_persona
from panda_abm.behavior.population import DriverAttributes, DriverSpec, PopulationSpec
from panda_abm.behavior.references import ReferencePoints, lot_distance_references
from panda_abm.behavior.cpt_parameters import cpt_parameters_for_persona,SHARED_CPT_PARAMETERS,PERSONA_CPT_PROFILE_VERSION
from panda_abm.environment.facility import Facility

__author__ = "Judith Njoku"


def make_controlled_population(
    facility: Facility,
    size: int = 12,
    seed: int = 42,
    heterogeneous: bool = True,
    population_id: str | None = None,
    personas: tuple[str, ...] = ("convenience_seeker",),
    cpt_profile_mode: str = 'persona',
) -> PopulationSpec:
    """Legacy prescribed profiles, only for explicitly controlled experiments."""

    if cpt_profile_mode not in ('shared','persona'):
        raise ValueError('CPT profile mode must be shared or persona')
    rng = np.random.default_rng(seed)
    entry = facility.entry_points[0] if facility.entry_points else (0.0, 0.0)
    module_centers = _module_centers(facility)
    module_ids = sorted(module_centers)
    drivers: list[DriverSpec] = []

    if not personas:
        raise ValueError("At least one persona is required")
    for persona in personas:
        parameters_for_persona(persona)
    schedule = [personas[i % len(personas)] for i in range(size)]
    if len(personas) > 1:
        np.random.default_rng(np.random.SeedSequence([seed, 173])).shuffle(schedule)
    for i in range(size):
        persona = schedule[i]
        base_params = parameters_for_persona(persona)
        module_id = module_ids[i % len(module_ids)]
        dest_x, dest_y = (
            facility.walmart_doors[i % len(facility.walmart_doors)]
            if facility.walmart_doors else module_centers[module_id]
        )
        attrs = DriverAttributes(
            driver_id=f"D{i:04d}",
            arrival_exit_id=facility.entry_point_ids[i % len(facility.entry_point_ids)] if facility.entry_point_ids else None,
            preferred_exit_id=facility.entry_point_ids[i % len(facility.entry_point_ids)] if facility.entry_point_ids else None,
            walmart_door_id=facility.walmart_door_ids[i % len(facility.walmart_door_ids)] if facility.walmart_door_ids else None,
            destination_x_m=float(dest_x if facility.walmart_doors else dest_x + rng.normal(0.0, 2.0)),
            destination_y_m=float(dest_y if facility.walmart_doors else dest_y + rng.normal(0.0, 2.0)),
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
        if persona == "accessibility_seeking":
            attrs = replace(attrs, accessibility_eligibility=True, permit_type="accessible",
                            mobility_limitation=True, max_walking_distance_m=120.)
        elif persona == "time_sensitive":
            attrs = replace(attrs, trip_urgency=max(.8, attrs.trip_urgency))

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
                beta_exit=base_params.beta_exit,
                beta_approach=base_params.beta_approach,
                beta_accessibility=base_params.beta_accessibility,
            )
        else:
            params = base_params

        refs = ReferencePoints(
            r_walk_m=float(np.clip(rng.normal(80.0 if persona == "accessibility_seeking" else 120.0, 25.0), 50.0, 250.0)),
            r_search_s=float(np.clip(rng.normal(120.0 if persona == "time_sensitive" else 300.0, 75.0), 60.0, 900.0)),
            kappa_walk=0.0,
            kappa_search=0.0,
            drift_enabled=False,
        )
        refs = lot_distance_references(facility, attrs, refs)
        cp=cpt_parameters_for_persona(persona) if cpt_profile_mode=='persona' else SHARED_CPT_PARAMETERS
        source=PERSONA_CPT_PROFILE_VERSION if cpt_profile_mode=='persona' else 'shared_tk92_benchmark'
        drivers.append(DriverSpec(attrs, params, refs,cp,source))

    return PopulationSpec(
        population_id=population_id or f"pop_{'het' if heterogeneous else 'hom'}_{size}_{seed}_{'_'.join(personas)}_cpt_{cpt_profile_mode}",
        seed=seed,
        drivers=tuple(drivers),
        generation_notes=f"Experimental persona mix {personas}; balanced, seeded assignment. Accessibility-seeking drivers are eligible and capped at 120 m walking. Distance expectations use fixed legal-inventory medians for the chosen door and exit. Profiles and expectations are uncalibrated.",
        generation_method='controlled_mixture_legacy_v1',
        parameterization={'personas':personas,'cpt_profile_mode':cpt_profile_mode,'heterogeneous':heterogeneous,'status':'prescribed groups, not emergent profiles'},
    )


def _module_centers(facility: Facility) -> dict[str, tuple[float, float]]:
    centers: dict[str, tuple[list[float], list[float]]] = {}
    for space in facility.spaces:
        xs, ys = centers.setdefault(space.module_id, ([], []))
        xs.append(space.x_m)
        ys.append(space.y_m)
    return {module: (float(np.mean(xs)), float(np.mean(ys))) for module, (xs, ys) in centers.items()}


# The primary generator never looks up a named profile. Kept here as the public
# import location while the old generator remains explicitly named above.
from panda_abm.behavior.continuous import make_population
