"""Metrics derived from the PANDA-ABM event log.

Author: Judith Njoku
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from panda_abm.core.events import EventLogger

__author__ = "Judith Njoku"


@dataclass
class MetricsCollector:
    """Turns raw events into tables for analysis."""

    event_logger: EventLogger

    def events(self) -> pd.DataFrame:
        return self.event_logger.dataframe()

    def final_agent_metrics(self) -> pd.DataFrame:
        events = self.events()
        if events.empty:
            return pd.DataFrame()

        agent_events = events[events["agent_id"].notna()].copy()
        if agent_events.empty:
            return pd.DataFrame()

        latest = agent_events.sort_values("time_s").groupby("agent_id", as_index=False).tail(1)
        rows = []
        for row in latest.itertuples(index=False):
            parked = _agent_has_event(agent_events, row.agent_id, "ParkingStarted")
            abandoned = _agent_has_event(agent_events, row.agent_id, "SearchAbandoned")
            rows.append(
                {
                    "run_id": row.run_id,
                    "scenario_id": row.scenario_id,
                    "replication_id": row.replication_id,
                    "seed": row.seed,
                    "decision_model": row.decision_model,
                    "driver_id": row.agent_id,
                    "persona": getattr(row, "detail_persona", None),
                    "arrival_time": getattr(row, "detail_arrival_time", None),
                    "search_time": row.search_time_s,
                    "search_started_s": getattr(row, "detail_search_started_s", None),
                    "search_ended_s": getattr(row, "detail_search_ended_s", None),
                    "parking_time_s": getattr(row, "detail_parking_time_s", None),
                    "search_distance": row.search_distance_m,
                    "walking_distance": getattr(row, "detail_walking_distance", None) if parked else None,
                    "chosen_space": getattr(row, "detail_chosen_space", None) if parked else None,
                    "chosen_module": getattr(row, "detail_chosen_module", None) if parked else None,
                    "rejected_spaces": getattr(row, "detail_rejected_spaces", None),
                    "candidate_evaluations": getattr(row, "detail_candidate_evaluations", None),
                    "module_switches": getattr(row, "detail_module_switches", None),
                    "parked": parked,
                    "abandoned": abandoned,
                    "violation": getattr(row, "detail_violation", False),
                    "lost_space_events": getattr(row, "detail_lost_space_events", 0),
                    "utility_of_chosen_action": getattr(row, "detail_utility_of_chosen_action", None),
                    "r_walk": getattr(row, "detail_r_walk", None),
                    "r_search": getattr(row, "detail_r_search", None),
                    "r_exit": getattr(row, "detail_r_exit", None),
                    "distance_reference_policy": getattr(row, "detail_distance_reference_policy", None),
                    "reference_space_count": getattr(row, "detail_reference_space_count", None),
                    **{f'cpt_{key}':getattr(row,f'detail_cpt_{key}',None) for key in ('alpha','beta','lambda_loss','gamma','gamma_loss','parameter_source')},
                    "vehicle_type": getattr(row, "detail_vehicle_type", None),
                    "guidance_access": getattr(row, "detail_guidance_access", None),
                    "information_mode":getattr(row,'detail_information_mode','unaided'),
                    "information_reports_received":getattr(row,'detail_information_reports_received',0),
                    "information_route_changes":getattr(row,'detail_information_route_changes',0),
                    "remote_targets_selected":getattr(row,'detail_remote_targets_selected',0),
                    "beta_walk": getattr(row, "detail_beta_walk", None),
                    "beta_price": getattr(row, "detail_beta_price", None),
                    "beta_search": getattr(row, "detail_beta_search", None),
                    "beta_risk": getattr(row, "detail_beta_risk", None),
                    "beta_availability": getattr(row, "detail_beta_availability", None),
                    "beta_familiarity": getattr(row, "detail_beta_familiarity", None),
                    "acceptance_utility_threshold": getattr(row, "detail_acceptance_utility_threshold", None),
                }
            )
        return pd.DataFrame(rows)

    def system_metrics(self) -> pd.DataFrame:
        events = self.events()
        if events.empty:
            return pd.DataFrame()
        system = events[events["event_type"] == "SystemSnapshot"].copy()
        if system.empty:
            return pd.DataFrame()
        return pd.DataFrame(
            {
                "run_id": system["run_id"],
                "scenario_id": system["scenario_id"],
                "replication_id": system["replication_id"],
                "seed": system["seed"],
                "decision_model": system["decision_model"],
                "timestep_s": system["time_s"],
                "occupied_spaces": system.get("detail_occupied_spaces"),
                "usable_spaces": system.get("detail_usable_spaces"),
                "occupancy_rate": system.get("detail_occupancy_rate"),
                "active_searchers": system.get("detail_active_searchers"),
                "targeting_agents": system.get("detail_targeting_agents"),
                "parked_agents": system.get("detail_parked_agents"),
                "abandoned_agents": system.get("detail_abandoned_agents"),
            }
        )

    def decision_log(self) -> pd.DataFrame:
        events = self.events()
        if events.empty:
            return pd.DataFrame()
        decisions = events[events["event_type"] == "CandidateEvaluated"].copy()
        if decisions.empty:
            return pd.DataFrame()
        return pd.DataFrame(
            {
                "run_id": decisions["run_id"],
                "scenario_id": decisions["scenario_id"],
                "replication_id": decisions["replication_id"],
                "seed": decisions["seed"],
                "decision_model": decisions["decision_model"],
                "driver_id": decisions["agent_id"],
                "timestep_s": decisions["time_s"],
                "space_id": decisions["space_id"],
                "feasible": decisions.get("detail_feasible"),
                "utility": decisions["utility"],
                "probability": decisions["probability"],
                "chosen": decisions.get("detail_chosen"),
            }
        )

    def trajectories(self) -> pd.DataFrame:
        events = self.events()
        if events.empty:
            return pd.DataFrame()
        moving = events[events["agent_id"].notna()].copy()
        if moving.empty:
            return pd.DataFrame()
        return pd.DataFrame(
            {
                "run_id": moving["run_id"],
                "scenario_id": moving["scenario_id"],
                "replication_id": moving["replication_id"],
                "seed": moving["seed"],
                "decision_model": moving["decision_model"],
                "driver_id": moving["agent_id"],
                "persona": moving.get("detail_persona"),
                "timestep_s": moving["time_s"],
                "state": moving["agent_state"],
                "x_m": moving["x_m"],
                "y_m": moving["y_m"],
                "chosen_space": moving.get("detail_chosen_space"),
                "search_time": moving["search_time_s"],
                "candidate_space_ids": moving.get("detail_candidate_space_ids"),
                "event_type": moving["event_type"],
            }
        )


def _agent_has_event(events: pd.DataFrame, agent_id: str, event_type: str) -> bool:
    subset = events[(events["agent_id"] == agent_id) & (events["event_type"] == event_type)]
    return not subset.empty


def coefficient_of_variation(values: list[int]) -> float:
    if not values:
        return 0.0
    series = pd.Series(values, dtype=float)
    mean = float(series.mean())
    return 0.0 if mean == 0.0 else float(series.std(ddof=0) / mean)
