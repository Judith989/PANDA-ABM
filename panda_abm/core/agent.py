"""Generic Mesa driver agent.

Author: Judith Njoku
"""

from __future__ import annotations

import math

from mesa import Agent

from panda_abm.behavior.decision.base import DecisionContext, DecisionModel, DecisionResult
from panda_abm.behavior.population import DriverSpec
from panda_abm.core.states import DriverState
from panda_abm.environment.parking_space import ParkingSpace

__author__ = "Judith Njoku"


class DriverAgent(Agent):
    """One driver who searches, chooses, parks, visits a destination, then leaves."""

    def __init__(
        self,
        model,
        spec: DriverSpec,
        decision_model: DecisionModel,
        start_position_m: tuple[float, float],
    ):
        super().__init__(model)
        self.spec = spec
        self.driver_id = spec.driver_id
        self.attributes = spec.attributes
        self.parameters = spec.behavioral_parameters
        self.reference_points = spec.reference_points
        self.decision_model = decision_model
        self.state = DriverState.NOT_ARRIVED
        self.x_m, self.y_m = start_position_m
        self.search_time_s = 0.0
        self.search_distance_m = 0.0
        self.rejected_spaces = 0
        self.candidate_evaluations = 0
        self.module_switches = 0
        self.last_module: str | None = None
        self.chosen_space_id: str | None = None
        self.chosen_module: str | None = None
        self.utility_of_chosen_action: float | None = None
        self.last_decision: DecisionResult | None = None
        self.last_candidate_space_ids: list[str] = []
        self.walking_distance_m: float | None = None
        self.arrival_time_s = spec.attributes.arrival_time_s
        self.parking_time_s: float | None = None
        self.activity_time_left_s = float(spec.attributes.expected_dwell_duration_s)
        self.violation = False
        self.lost_space_events = 0
        self.path: list[tuple[float, float]] = [(self.x_m, self.y_m)]

    def step(self) -> None:
        if self.model.clock_s < self.arrival_time_s:
            return
        if self.state == DriverState.NOT_ARRIVED:
            self.state = DriverState.ARRIVING
            self.model.event_logger.log("AgentArrived", self.model.clock_s, agent=self)
            return
        if self.state == DriverState.ARRIVING:
            self.state = DriverState.SEARCHING
            self.model.event_logger.log("SearchStarted", self.model.clock_s, agent=self)
            return
        if self.state == DriverState.SEARCHING:
            self._search_step()
            return
        if self.state == DriverState.TARGETING:
            self._target_step()
            return
        if self.state == DriverState.PARKED:
            self._start_walking_to_destination()
            return
        if self.state == DriverState.WALKING_TO_DESTINATION:
            self.state = DriverState.AT_DESTINATION
            self.model.event_logger.log("DestinationReached", self.model.clock_s, agent=self)
            return
        if self.state == DriverState.AT_DESTINATION:
            self.activity_time_left_s -= self.model.step_seconds
            self.model.event_logger.log("AgentActivityStep", self.model.clock_s, agent=self)
            if self.activity_time_left_s <= 0:
                self.state = DriverState.RETURNING_TO_VEHICLE
                self.model.event_logger.log("ReturningToVehicleStarted", self.model.clock_s, agent=self)
            return
        if self.state == DriverState.RETURNING_TO_VEHICLE:
            self._start_exiting()
            return
        if self.state == DriverState.EXITING:
            self.state = DriverState.LEFT
            self.model.event_logger.log("AgentExited", self.model.clock_s, agent=self)

    def _search_step(self) -> None:
        if self.search_time_s >= self.model.max_search_time_s:
            self.state = DriverState.ABANDONED
            self.model.event_logger.log("SearchAbandoned", self.model.clock_s, agent=self)
            return

        observations = self.model.perceive(self)
        feasible = self.model.build_choice_set(self, observations)
        self.last_candidate_space_ids = [space.space_id for space in feasible]
        self.candidate_evaluations += len(feasible)
        self.model.event_logger.log(
            "CandidateObserved",
            self.model.clock_s,
            agent=self,
            details={
                "observed_count": len(observations),
                "feasible_count": len(feasible),
                "candidate_space_ids": "|".join(self.last_candidate_space_ids),
            },
        )

        context = self._decision_context()
        decision = self.decision_model.evaluate_candidates(context, feasible)
        self.last_decision = decision
        self._log_decision(decision, feasible, context)

        if decision.chosen_action == "park" and decision.chosen_space_id:
            self._select_target(decision)
            return

        self.rejected_spaces += len(feasible)
        self.model.event_logger.log(
            "CandidateRejected",
            self.model.clock_s,
            agent=self,
            details={"reason": decision.diagnostics.get("reason", "continue_search")},
        )
        self._move_toward_destination()
        self.search_time_s += self.model.step_seconds

    def _decision_context(self) -> DecisionContext:
        return DecisionContext(
            driver_id=self.driver_id,
            behavioral_parameters=self.parameters,
            reference_points=self.reference_points,
            accumulated_search_time_s=self.search_time_s,
            current_position_m=(self.x_m, self.y_m),
            destination_m=self.attributes.destination,
            vehicle_type=self.attributes.vehicle_type,
            accessibility_eligibility=self.attributes.accessibility_eligibility,
            permit_type=self.attributes.permit_type,
            familiarity=self.attributes.local_familiarity,
            allow_illegal_alternatives=self.model.allow_illegal_alternatives,
            rng_seed=self.model.seed_for_driver_step(self.driver_id, int(self.search_time_s)),
        )

    def _log_decision(self, decision: DecisionResult, feasible: list[ParkingSpace], context: DecisionContext) -> None:
        continuation_value = self.model.continuation_model.value(context, len(feasible))
        self.model.event_logger.log(
            "ContinuationEvaluated",
            self.model.clock_s,
            agent=self,
            utility=continuation_value,
            details={"feasible_count": len(feasible)},
        )
        for eval_item in decision.candidate_evaluations:
            self.model.event_logger.log(
                "CandidateEvaluated",
                self.model.clock_s,
                agent=self,
                space_id=eval_item.space_id,
                utility=eval_item.utility,
                probability=decision.probabilities.get(eval_item.space_id),
                details={
                    "feasible": eval_item.feasible,
                    "chosen": eval_item.space_id == decision.chosen_space_id,
                },
            )

    def _select_target(self, decision: DecisionResult) -> None:
        target = self.model.facility.space_by_id[decision.chosen_space_id]
        self.chosen_space_id = target.space_id
        self.chosen_module = target.module_id
        self.utility_of_chosen_action = decision.chosen_utility
        self.state = DriverState.TARGETING
        self.model.event_logger.log(
            "TargetSelected",
            self.model.clock_s,
            agent=self,
            space=target,
            utility=decision.chosen_utility,
        )

    def _target_step(self) -> None:
        if not self.chosen_space_id:
            self.state = DriverState.SEARCHING
            return
        target = self.model.facility.space_by_id[self.chosen_space_id]
        if not self._move_toward(target.x_m, target.y_m):
            self.search_time_s += self.model.step_seconds
            self.model.event_logger.log("VehicleMovingToTarget", self.model.clock_s, agent=self, space=target)
            return

        self.model.event_logger.log("SpaceClaimAttempted", self.model.clock_s, agent=self, space=target)
        if self.model.try_park(self, target.space_id):
            return
        self.lost_space_events += 1
        self.rejected_spaces += 1
        self.chosen_space_id = None
        self.chosen_module = None
        self.state = DriverState.SEARCHING
        self.model.event_logger.log("LostSpace", self.model.clock_s, agent=self, space=target)

    def _move_toward_destination(self) -> None:
        dest_x, dest_y = self.attributes.destination
        self._move_toward(dest_x, dest_y)

    def _move_toward(self, dest_x: float, dest_y: float) -> bool:
        dx = dest_x - self.x_m
        dy = dest_y - self.y_m
        distance = math.hypot(dx, dy)
        if distance < 1e-9:
            return True
        step = min(self.model.search_speed_m_per_s * self.model.step_seconds, distance)
        self.x_m += dx / distance * step
        self.y_m += dy / distance * step
        self.search_distance_m += step
        self.path.append((self.x_m, self.y_m))
        return step >= distance

    def park_at(self, space: ParkingSpace, utility: float | None) -> None:
        self.state = DriverState.PARKED
        self.chosen_space_id = space.space_id
        self.chosen_module = space.module_id
        self.utility_of_chosen_action = utility
        self.walking_distance_m = math.hypot(
            space.x_m - self.attributes.destination_x_m,
            space.y_m - self.attributes.destination_y_m,
        )
        self.x_m = space.x_m
        self.y_m = space.y_m
        self.parking_time_s = self.model.clock_s
        self.path.append((self.x_m, self.y_m))
        self.model.event_logger.log("SpaceClaimSucceeded", self.model.clock_s, agent=self, space=space, utility=utility)
        self.model.event_logger.log("ParkingStarted", self.model.clock_s, agent=self, space=space, utility=utility)

    def _start_walking_to_destination(self) -> None:
        self.state = DriverState.WALKING_TO_DESTINATION
        self.model.event_logger.log("WalkingToDestinationStarted", self.model.clock_s, agent=self)

    def _start_exiting(self) -> None:
        parked_space_id = self.chosen_space_id
        if parked_space_id:
            self.model.release_parking(self, parked_space_id)
        self.state = DriverState.EXITING
        self.model.event_logger.log("ParkingEnded", self.model.clock_s, agent=self, space_id=parked_space_id)
