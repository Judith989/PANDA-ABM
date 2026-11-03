"""Mesa parking model for Milestone 1.

Author: Judith Njoku
"""

from __future__ import annotations

import hashlib
import math

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
from panda_abm.environment.perception import RadiusPerception,SpaceInformationPerception
from panda_abm.environment.information import INFORMATION_MODES,AisleInformationService
from panda_abm.environment.parking_space import ParkingSpace
from panda_abm.environment.navigation import AisleNetwork
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
        integration_seconds: float = 1.0,
        decision_interval_s: float = 10.0,
        parking_maneuver_s: float = 2.0,
        claim_hazard_per_s: float = 0.002,
        failure_delay_s: float = 30.0,
        decision_seed_namespace: str | None = None,
        information_mode: str = 'unaided',
    ):
        super().__init__(rng=seed)
        if information_mode not in INFORMATION_MODES:
            raise ValueError(f'Information mode must be one of {INFORMATION_MODES}')
        self.information_mode=information_mode
        self.facility = facility
        self.population = population
        self.decision_model_name = decision_model if isinstance(decision_model, str) else decision_model.model_name
        self.decision_model = self._build_decision_model(decision_model)
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.replication_id = replication_id
        self.seed = seed
        self.decision_seed_namespace=decision_seed_namespace
        self.rng = np.random.default_rng(seed)
        self.step_seconds = step_seconds
        values=(integration_seconds,step_seconds,decision_interval_s,search_speed_m_per_s,max_search_time_s,claim_hazard_per_s,parking_maneuver_s,failure_delay_s,perception_radius_m)
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Model time, speed and probability parameters must be finite')
        if integration_seconds <= 0 or step_seconds <= 0 or decision_interval_s <= 0 or search_speed_m_per_s <= 0 or max_search_time_s <= 0:
            raise ValueError('Time intervals and speed must be positive')
        if abs(step_seconds / integration_seconds - round(step_seconds / integration_seconds)) > 1e-9:
            raise ValueError('Output interval must be a multiple of the integration resolution')
        if claim_hazard_per_s < 0 or parking_maneuver_s < 0 or failure_delay_s < 0:
            raise ValueError('Hazard and delays must be nonnegative')
        if perception_radius_m < 0:
            raise ValueError('Perception radius must be nonnegative')
        if not 0 <= initial_occupancy_rate <= 1:
            raise ValueError('Initial occupancy must be in [0,1]')
        for duration in (decision_interval_s,max_search_time_s):
            if abs(duration/integration_seconds-round(duration/integration_seconds)) > 1e-9:
                raise ValueError('Decision interval and search deadline must align with physical resolution')
        ids=[d.driver_id for d in population.drivers]
        if len(ids)!=len(set(ids)):
            raise ValueError('Driver IDs must be unique')
        for d in population.drivers:
            arrival=d.attributes.arrival_time_s
            if arrival<0 or not math.isfinite(arrival) or abs(arrival/integration_seconds-round(arrival/integration_seconds))>1e-9:
                raise ValueError('Arrival times must be nonnegative and align with physical resolution')
        self.integration_seconds = integration_seconds
        self.decision_interval_s = decision_interval_s
        self.parking_maneuver_s = parking_maneuver_s
        self.claim_hazard_per_s = claim_hazard_per_s
        self.failure_delay_s = failure_delay_s
        self.walk_speed_m_per_s = 1.4
        self.navigation = AisleNetwork(facility)
        self.scheduler_rng = np.random.default_rng(np.random.SeedSequence([seed, 9281]))
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
        self.perception_model = SpaceInformationPerception() if information_mode=='space' else RadiusPerception(radius_m=perception_radius_m)
        self.choice_set_builder = ChoiceSetBuilder(allow_illegal_alternatives=allow_illegal_alternatives)
        self.continuation_model = SimpleContinuationModel()
        self.forecast_provider = forecast_provider or NullForecastProvider()
        self.aisle_information=AisleInformationService(self)

        self._initialize_occupancy(initial_occupancy_rate)

        for index, spec in enumerate(population.drivers):
            entry_index = (
                facility.entry_point_ids.index(spec.attributes.arrival_exit_id)
                if spec.attributes.arrival_exit_id else index % len(facility.entry_points) if facility.entry_points else 0
            )
            start = facility.entry_points[entry_index] if facility.entry_points else (0.0, 0.0)
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
        namespace=self.decision_seed_namespace or self.decision_model_name
        raw = f"{self.seed}:{self.run_id}:{namespace}:{driver_id}:{search_time_s}".encode("utf-8")
        return int(hashlib.sha256(raw).hexdigest()[:8], 16)

    def perceive(self, agent: DriverAgent):
        return self.perception_model.observe(self, agent)

    def information_mode_for(self, agent: DriverAgent):
        return self.information_mode

    def before_physical_tick(self):
        """Extension point for timestamped information and exogenous events."""
        pass

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
        # step_seconds is output cadence. Physical resolution and decisions are
        # independent, so batching cannot alter trajectories or tie draws.
        for _ in range(round(self.step_seconds / self.integration_seconds)):
            self.before_physical_tick()
            agents = sorted(self.agents, key=lambda a: a.driver_id)
            self.scheduler_rng.shuffle(agents)
            for agent in agents:
                agent.step()
            self.clock_s = round(self.clock_s + self.integration_seconds, 9)
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
        super().step()

    def run_until_complete(self) -> None:
        if not self.population.drivers:
            return
        latest_arrival = max(d.attributes.arrival_time_s for d in self.population.drivers)
        route_bound = sum(e['weight'] for _,_,e in self.navigation.graph.edges(data=True)) / self.search_speed_m_per_s
        max_runtime = latest_arrival + self.max_search_time_s + max(d.attributes.expected_dwell_duration_s for d in self.population.drivers) + route_bound + 2000
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
        else:
            raise RuntimeError('Simulation time bound reached with unfinished drivers')
