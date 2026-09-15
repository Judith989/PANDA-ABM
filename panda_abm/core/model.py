"""Mesa parking model for Milestone 1.

Author: Judith Njoku
"""

from __future__ import annotations

import hashlib

import numpy as np
from mesa import Model

from panda_abm.behavior.decision import CPTDecisionModel, DeterministicUtilityModel, RandomUtilityModel
from panda_abm.behavior.decision.base import DecisionModel
from panda_abm.behavior.decision.continuation import SimpleContinuationModel
from panda_abm.behavior.population import PopulationSpec
from panda_abm.core.agent import DriverAgent
from panda_abm.core.events import EventLogger
from panda_abm.core.resource_manager import ParkingResourceManager
from panda_abm.core.states import DriverState
from panda_abm.environment.choice_set import ChoiceSetBuilder
from panda_abm.environment.facility import Facility
from panda_abm.environment.perception import RadiusPerception
from panda_abm.environment.parking_space import ParkingSpace
from panda_abm.forecasting import ForecastProvider, NullForecastProvider
from panda_abm.metrics.collector import MetricsCollector

__author__ = "Judith Njoku"


DECISION_MODELS = {
    "deterministic": DeterministicUtilityModel,
    "m0": DeterministicUtilityModel,
    "rum": RandomUtilityModel,
    "m1": RandomUtilityModel,
    "cpt": CPTDecisionModel,
    "m2": CPTDecisionModel,
}


class ParkingModel(Model):
    """Mesa model that keeps search, claims, events, and twin state separate."""

    def __init__(
        self,
        facility: Facility,
        population: PopulationSpec,
        decision_model: str | DecisionModel = "rum",
        run_id: str = "run_001",
        scenario_id: str = "demo",
        replication_id: str = "rep000",
        seed: int = 42,
        step_seconds: int = 10,
        max_search_time_s: int = 600,
        perception_radius_m: float = 60.0,
        search_speed_m_per_s: float = 5.0,
        allow_illegal_alternatives: bool = False,
        initial_occupancy_rate: float = 0.25,
        forecast_provider: ForecastProvider | None = None,
    ):
        super().__init__(rng=seed)
        self.facility = facility
        self.population = population
        self.decision_model_name = decision_model if isinstance(decision_model, str) else decision_model.model_name
        self.decision_model = self._build_decision_model(decision_model)
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.replication_id = replication_id
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.step_seconds = step_seconds
        self.clock_s = 0
        self.max_search_time_s = max_search_time_s
        self.perception_radius_m = perception_radius_m
        self.search_speed_m_per_s = search_speed_m_per_s
        self.allow_illegal_alternatives = allow_illegal_alternatives

        initial_states = facility.initial_space_states()
        self.resource_manager = ParkingResourceManager(facility, initial_states)
        self.space_states = self.resource_manager.states
        self.event_logger = EventLogger(
            run_id=run_id,
            scenario_id=scenario_id,
            replication_id=replication_id,
            seed=seed,
            decision_model=self.decision_model_name,
        )
        self.metrics = MetricsCollector(event_logger=self.event_logger)
        self.perception_model = RadiusPerception(radius_m=perception_radius_m)
        self.choice_set_builder = ChoiceSetBuilder(allow_illegal_alternatives=allow_illegal_alternatives)
        self.continuation_model = SimpleContinuationModel()
        self.forecast_provider = forecast_provider or NullForecastProvider()

        self._initialize_occupancy(initial_occupancy_rate)

        start = facility.entry_points[0] if facility.entry_points else (0.0, 0.0)
        for spec in population.drivers:
            DriverAgent(self, spec=spec, decision_model=self.decision_model, start_position_m=start)

    def _build_decision_model(self, decision_model: str | DecisionModel) -> DecisionModel:
        if not isinstance(decision_model, str):
            return decision_model
        key = decision_model.lower()
        if key not in DECISION_MODELS:
            raise ValueError(f"Unknown decision model: {decision_model}")
        return DECISION_MODELS[key]()

    def _initialize_occupancy(self, occupancy_rate: float) -> None:
        usable = [s for s in self.facility.spaces if not s.unavailable]
        n_occupied = int(round(len(usable) * occupancy_rate))
        chosen = set(self.rng.choice([s.space_id for s in usable], size=n_occupied, replace=False)) if n_occupied else set()
        for sid in chosen:
            self.resource_manager.claim_space("initial_occupancy", sid)
            self.event_logger.log("InitialSpaceOccupied", self.clock_s, space_id=sid)

    def seed_for_driver_step(self, driver_id: str, search_time_s: int) -> int:
        raw = f"{self.seed}:{self.run_id}:{self.decision_model_name}:{driver_id}:{search_time_s}".encode("utf-8")
        return int(hashlib.sha256(raw).hexdigest()[:8], 16)

    def perceive(self, agent: DriverAgent):
        return self.perception_model.observe(self, agent)

    def build_choice_set(self, agent: DriverAgent, observations):
        return self.choice_set_builder.build(agent, observations)

    def perceive_candidates(self, agent: DriverAgent) -> list[ParkingSpace]:
        return [observed.space for observed in self.perceive(agent)]

    def filter_candidates(self, agent: DriverAgent, candidates: list[ParkingSpace]) -> list[ParkingSpace]:
        observed_by_id = {observed.space.space_id: observed for observed in self.perceive(agent)}
        observations = [observed_by_id[space.space_id] for space in candidates if space.space_id in observed_by_id]
        return self.build_choice_set(agent, observations)

    def try_park(self, agent: DriverAgent, space_id: str) -> bool:
        space = self.facility.space_by_id[space_id]
        if not self.resource_manager.claim_space(agent.driver_id, space_id):
            self.event_logger.log("SpaceClaimFailed", self.clock_s, agent=agent, space=space)
            return False
        agent.park_at(space, agent.last_decision.chosen_utility if agent.last_decision else None)
        return True

    def release_parking(self, agent: DriverAgent, space_id: str) -> bool:
        space = self.facility.space_by_id[space_id]
        released = self.resource_manager.release_space(agent.driver_id, space_id)
        if released:
            self.event_logger.log("SpaceReleased", self.clock_s, agent=agent, space=space)
        return released

    def step(self) -> None:
        self.agents.do("step")
        self.event_logger.log(
            "SystemSnapshot",
            self.clock_s,
            details={
                "occupied_spaces": self.resource_manager.occupied_count(),
                "usable_spaces": self.resource_manager.usable_count(),
                "occupancy_rate": self.resource_manager.occupancy_rate(),
                "active_searchers": sum(1 for a in self.agents if getattr(a, "state", None) == DriverState.SEARCHING),
                "targeting_agents": sum(1 for a in self.agents if getattr(a, "state", None) == DriverState.TARGETING),
                "parked_agents": sum(1 for a in self.agents if getattr(a, "state", None) == DriverState.PARKED),
                "abandoned_agents": sum(1 for a in self.agents if getattr(a, "state", None) == DriverState.ABANDONED),
            },
        )
        self.clock_s += self.step_seconds
        super().step()

    def run_until_complete(self) -> None:
        latest_arrival = max(d.attributes.arrival_time_s for d in self.population.drivers)
        max_runtime = latest_arrival + self.max_search_time_s + max(d.attributes.expected_dwell_duration_s for d in self.population.drivers) + 120
        while self.clock_s <= max_runtime:
            self.step()
            active = [
                a
                for a in self.agents
                if getattr(a, "state", None)
                not in {DriverState.LEFT, DriverState.ABANDONED}
            ]
            if not active:
                break
