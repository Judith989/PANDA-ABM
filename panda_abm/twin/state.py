"""Build simulation state snapshots for future Cesium integration.

Author: Judith Njoku
"""

from __future__ import annotations

__author__ = "Judith Njoku"


def build_twin_state(model, state_type: str = "simulated_current") -> dict:
    """Return a JSON-friendly view of vehicles and spaces at one tick."""

    vehicles = []
    for agent in model.agents:
        vehicles.append(
            {
                "vehicle_id": agent.driver_id,
                "persona": agent.attributes.persona,
                "vehicle_type": agent.attributes.vehicle_type,
                "state": agent.state.value,
                "x_m": agent.x_m,
                "y_m": agent.y_m,
                "chosen_space_id": agent.chosen_space_id,
                "search_time": agent.search_time_s,
                "candidate_space_ids": list(agent.last_candidate_space_ids),
            }
        )

    spaces = []
    for space in model.facility.spaces:
        state = model.resource_manager.states[space.space_id]
        spaces.append(
            {
                "space_id": space.space_id,
                "module_id": space.module_id,
                "x_m": space.x_m,
                "y_m": space.y_m,
                "latitude": space.latitude,
                "longitude": space.longitude,
                "occupied": state.occupied,
                "occupant_id": state.occupant_id,
                "unavailable": state.unavailable,
                "space_type": space.space_type.value,
            }
        )

    return {
        "run_id": model.run_id,
        "scenario_id": model.scenario_id,
        "decision_model": model.decision_model_name,
        "time_s": model.clock_s,
        "state_type": state_type,
        "author": "Judith Njoku",
        "system": {
            "occupied_spaces": model.resource_manager.occupied_count(),
            "usable_spaces": model.resource_manager.usable_count(),
            "occupancy_rate": model.resource_manager.occupancy_rate(),
        },
        "vehicles": vehicles,
        "spaces": spaces,
    }
