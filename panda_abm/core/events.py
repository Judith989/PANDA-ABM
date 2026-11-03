"""Event records for the PANDA-ABM simulation.

Author: Judith Njoku
"""

from __future__ import annotations

from panda_abm.behavior.cpt_parameters import CPTParameters

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

__author__ = "Judith Njoku"


@dataclass(frozen=True)
class EventRecord:
    """One thing that happened in the simulation."""

    run_id: str
    scenario_id: str
    replication_id: str
    seed: int
    decision_model: str
    time_s: float
    event_type: str
    agent_id: str | None = None
    space_id: str | None = None
    module_id: str | None = None
    agent_state: str | None = None
    search_time_s: float | None = None
    search_distance_m: float | None = None
    utility: float | None = None
    probability: float | None = None
    x_m: float | None = None
    y_m: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_flat_dict(self) -> dict[str, Any]:
        row = asdict(self)
        details = row.pop("details") or {}
        for key, value in details.items():
            row[f"detail_{key}"] = value
        return row


class EventLogger:
    """Small event store used by the model, metrics, and twin exporter."""

    def __init__(
        self,
        run_id: str,
        scenario_id: str,
        replication_id: str,
        seed: int,
        decision_model: str,
    ):
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.replication_id = replication_id
        self.seed = seed
        self.decision_model = decision_model
        self.records: list[EventRecord] = []

    def log(
        self,
        event_type: str,
        time_s: float,
        agent=None,
        space=None,
        space_id: str | None = None,
        module_id: str | None = None,
        utility: float | None = None,
        probability: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if space is not None:
            space_id = getattr(space, "space_id", space_id)
            module_id = getattr(space, "module_id", module_id)

        event_details = dict(details or {})
        if agent is not None:
            event_details.setdefault("persona", agent.attributes.persona)
            event_details.setdefault("arrival_exit_id", agent.attributes.arrival_exit_id)
            event_details.setdefault("preferred_exit_id", agent.attributes.preferred_exit_id)
            event_details.setdefault("walmart_door_id", agent.attributes.walmart_door_id)
            event_details.setdefault("vehicle_type", agent.attributes.vehicle_type)
            event_details.setdefault("arrival_time", agent.arrival_time_s)
            event_details.setdefault("search_started_s", agent.search_started_s)
            event_details.setdefault("search_ended_s", agent.search_ended_s)
            event_details.setdefault("parking_time_s", agent.parking_time_s)
            event_details.setdefault("chosen_space", agent.chosen_space_id)
            event_details.setdefault("chosen_module", agent.chosen_module)
            event_details.setdefault("walking_distance", agent.walking_distance_m)
            event_details.setdefault("rejected_spaces", agent.rejected_spaces)
            event_details.setdefault("candidate_evaluations", agent.candidate_evaluations)
            event_details.setdefault("module_switches", agent.module_switches)
            event_details.setdefault("lost_space_events", agent.lost_space_events)
            event_details.setdefault("violation", agent.violation)
            event_details.setdefault("utility_of_chosen_action", agent.utility_of_chosen_action)
            event_details.setdefault("r_walk", agent.reference_points.r_walk_m)
            event_details.setdefault("r_search", agent.reference_points.r_search_s)
            event_details.setdefault("r_exit", agent.reference_points.r_exit_m)
            event_details.setdefault("distance_reference_policy", agent.reference_points.distance_reference_policy)
            event_details.setdefault("reference_space_count", agent.reference_points.reference_space_count)
            override=getattr(agent.decision_model,'cpt_parameters',None)
            cp=override or agent.spec.cpt_parameters or CPTParameters()
            if cp is not None:
                for key,value in cp.as_dict().items():event_details.setdefault(f'cpt_{key}',value)
            event_details.setdefault('cpt_parameter_source','explicit_model_override' if override is not None else agent.spec.cpt_parameter_source)
            event_details.setdefault("guidance_access", agent.attributes.guidance_access)
            event_details.setdefault('information_mode',agent.model.information_mode)
            event_details.setdefault('information_reports_received',agent.information_reports_received)
            event_details.setdefault('information_route_changes',agent.information_route_changes)
            event_details.setdefault('remote_targets_selected',agent.remote_targets_selected)
            event_details.setdefault("beta_walk", agent.parameters.beta_walk)
            event_details.setdefault("beta_approach", agent.parameters.beta_approach)
            event_details.setdefault("beta_accessibility", agent.parameters.beta_accessibility)
            event_details.setdefault("beta_price", agent.parameters.beta_price)
            event_details.setdefault("beta_search", agent.parameters.beta_search)
            event_details.setdefault("beta_risk", agent.parameters.beta_risk)
            event_details.setdefault("beta_availability", agent.parameters.beta_availability)
            event_details.setdefault("beta_familiarity", agent.parameters.beta_familiarity)
            event_details.setdefault("acceptance_utility_threshold", agent.parameters.acceptance_utility_threshold)

        self.records.append(
            EventRecord(
                run_id=self.run_id,
                scenario_id=self.scenario_id,
                replication_id=self.replication_id,
                seed=self.seed,
                decision_model=self.decision_model,
                time_s=float(time_s),
                event_type=event_type,
                agent_id=getattr(agent, "driver_id", None),
                space_id=space_id,
                module_id=module_id,
                agent_state=getattr(getattr(agent, "state", None), "value", None),
                search_time_s=getattr(agent, "search_time_s", None),
                search_distance_m=getattr(agent, "search_distance_m", None),
                utility=utility,
                probability=probability,
                x_m=getattr(agent, "x_m", None),
                y_m=getattr(agent, "y_m", None),
                details=event_details,
            )
        )

    def dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([record.as_flat_dict() for record in self.records])
