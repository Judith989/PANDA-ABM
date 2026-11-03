"""Drivers follow connected aisles, patrol repeatedly, and time search by timestamps."""
from __future__ import annotations
import math
from mesa import Agent
from panda_abm.behavior.decision.base import DecisionContext
from panda_abm.core.states import DriverState

class DriverAgent(Agent):
    def __init__(self,model,spec,decision_model,start_position_m):
        super().__init__(model)
        self.spec=spec;self.driver_id=spec.driver_id;self.attributes=spec.attributes
        self.parameters=spec.behavioral_parameters;self.reference_points=spec.reference_points
        self.decision_model=decision_model;self.state=DriverState.NOT_ARRIVED
        self.x_m,self.y_m=start_position_m
        self.search_time_s=0.;self.search_distance_m=0.;self.rejected_spaces=0;self.candidate_evaluations=0
        self.module_switches=0;self.last_module=None;self.chosen_space_id=None;self.chosen_module=None
        self.utility_of_chosen_action=None;self.last_decision=None;self.last_candidate_space_ids=[]
        self.walking_distance_m=None;self.arrival_time_s=spec.attributes.arrival_time_s
        self.parking_time_s=None;self.search_started_s=None;self.search_ended_s=None
        self.activity_time_left_s=float(spec.attributes.expected_dwell_duration_s)
        self.violation=False;self.lost_space_events=0;self.path=[(self.x_m,self.y_m)]
        self.route=[];self.patrol_goal=None;self.aisle_visits={};self.next_decision_s=self.arrival_time_s
        self.last_tick_s=self.arrival_time_s;self.attempt_ready_s=0.;self._candidate_times={};self._candidate_probabilities={}
        self.information_aisle_id=None;self.information_reports_received=0;self.information_route_changes=0
        self.remote_targets_selected=0;self._observations_by_id={}

    def log(self,event,**kwargs):self.model.event_logger.log(event,self.model.clock_s,agent=self,**kwargs)

    def step(self):
        now=self.model.clock_s
        if now<self.arrival_time_s or self.state in (DriverState.LEFT,DriverState.ABANDONED):return
        dt=max(0.,now-self.last_tick_s);self.last_tick_s=now
        if self.state==DriverState.NOT_ARRIVED:
            self.state=DriverState.ARRIVING;self.log('AgentArrived');self.search_started_s=now;self.state=DriverState.SEARCHING
            self.log('SearchStarted');dt=0.
        if self.state in (DriverState.SEARCHING,DriverState.TARGETING):
            self.search_time_s=now-self.search_started_s
            if self.search_time_s>=self.model.max_search_time_s:
                self.search_ended_s=now;self.state=DriverState.ABANDONED;self.route=[];self.log('SearchAbandoned');return
        if self.state==DriverState.SEARCHING:
            self._advance_route(dt)
            if not self.route and self.patrol_goal is not None:
                self.aisle_visits[self.patrol_goal]=self.aisle_visits.get(self.patrol_goal,0)+1
                self.log('AisleEndVisited',details={'node_id':self.patrol_goal})
                self.patrol_goal=None
            if now+1e-9>=self.next_decision_s:
                self.next_decision_s=now+self.model.decision_interval_s
                self._search_step()
            if self.state==DriverState.SEARCHING and not self.route:
                self.patrol_goal=self.model.navigation.next_patrol((self.x_m,self.y_m),self.aisle_visits)
                self.route=self.model.navigation.route((self.x_m,self.y_m),self.patrol_goal)
            return
        if self.state==DriverState.TARGETING:
            self._advance_route(dt)
            if self.route or now+1e-9<self.attempt_ready_s:return
            target=self.model.facility.space_by_id[self.chosen_space_id]
            self.log('SpaceClaimAttempted',space=target)
            if self.model.try_park(self,target.space_id):return
            self.lost_space_events+=1;self.rejected_spaces+=1
            self.chosen_space_id=None;self.chosen_module=None;self.state=DriverState.SEARCHING
            self.next_decision_s=now;self.log('LostSpace',space=target);return
        if self.state==DriverState.PARKED:
            self.state=DriverState.WALKING_TO_DESTINATION;self.log('WalkingToDestinationStarted')
        if self.state==DriverState.WALKING_TO_DESTINATION:
            if now+1e-9>=self.destination_ready_s:
                self.state=DriverState.AT_DESTINATION;self.dwell_end_s=now+self.attributes.expected_dwell_duration_s
                self.log('DestinationReached')
            return
        if self.state==DriverState.AT_DESTINATION:
            self.activity_time_left_s=max(0.,self.dwell_end_s-now)
            if now+1e-9>=self.dwell_end_s:
                self.state=DriverState.RETURNING_TO_VEHICLE
                self.return_ready_s=now+self.walking_distance_m/self.model.walk_speed_m_per_s
                self.log('ReturningToVehicleStarted')
            return
        if self.state==DriverState.RETURNING_TO_VEHICLE:
            if now+1e-9>=self.return_ready_s:self._start_exiting()
            return
        if self.state==DriverState.EXITING:
            self._advance_route(dt,count_search=False)
            if not self.route:self.state=DriverState.LEFT;self.log('AgentExited')

    @property
    def information_mode(self):
        return self.model.information_mode_for(self)

    def _search_step(self):
        report=None
        if self.information_mode=='aisle':
            report=self.model.aisle_information.snapshot(self)
            self.information_reports_received+=1
            self.log('InformationReceived',details=dict(information_mode='aisle',report_time_s=report.observed_at_s,
                free_counts=report.free_counts,compatible_capacity=report.compatible_capacity))
        observations=self.model.perceive(self)
        self._observations_by_id={o.space.space_id:o for o in observations}
        if self.information_mode=='space':
            self.information_reports_received+=1
            self.log('InformationReceived',details=dict(information_mode='space',report_time_s=self.model.clock_s,
                reported_available=sum(o.perceived_available for o in observations),
                oldest_observation_s=min((o.observed_at_s for o in observations),default=self.model.clock_s)))
        feasible=self.model.build_choice_set(self,observations)
        self.last_candidate_space_ids=[s.space_id for s in feasible]
        self.candidate_evaluations+=len(feasible)
        self.log('CandidateObserved',details={'observed_count':len(observations),'feasible_count':len(feasible),
            'candidate_space_ids':'|'.join(self.last_candidate_space_ids)})
        self._candidate_times={};self._candidate_probabilities={}
        if feasible:
            distances=self.model.navigation.distances((self.x_m,self.y_m),
                [self.model.navigation.space_nodes[s.space_id] for s in feasible])
            forecast={o.space.space_id:o.forecast_available_probability for o in observations}
            for s in feasible:
                travel=distances[self.model.navigation.space_nodes[s.space_id]]/self.model.search_speed_m_per_s
                self._candidate_times[s.space_id]=travel+self.model.parking_maneuver_s
                supplied=forecast[s.space_id]
                # Explicit assumed survival probability until the claim attempt.
                p=(1. if supplied is None else supplied)*math.exp(-self.model.claim_hazard_per_s*(travel+self.model.parking_maneuver_s))
                self._candidate_probabilities[s.space_id]=p
        context=self._decision_context()
        decision=self.decision_model.evaluate_candidates(context,feasible)
        self.last_decision=decision
        for e in decision.candidate_evaluations:
            self.log('CandidateEvaluated',space_id=e.space_id,utility=e.utility,probability=decision.probabilities.get(e.space_id),
                details={'feasible':e.feasible,'chosen':e.space_id==decision.chosen_space_id,
                    **{f'feature_{k}':v for k,v in e.features.items()},**{f'cpt_{k}':v for k,v in e.diagnostics.items()}})
        if decision.chosen_action=='park' and decision.chosen_space_id:
            self._select_target(decision);return
        self.rejected_spaces+=len(feasible)
        self.log('CandidateRejected',details={'reason':decision.diagnostics.get('reason','continue_search')})
        if report is not None:self.model.aisle_information.plan_search(self,report)

    def _decision_context(self):
        return DecisionContext(driver_id=self.driver_id,behavioral_parameters=self.parameters,reference_points=self.reference_points,
            accumulated_search_time_s=self.search_time_s,current_position_m=(self.x_m,self.y_m),destination_m=self.attributes.destination,
            vehicle_type=self.attributes.vehicle_type,accessibility_eligibility=self.attributes.accessibility_eligibility,
            permit_type=self.attributes.permit_type,familiarity=self.attributes.local_familiarity,
            allow_illegal_alternatives=self.model.allow_illegal_alternatives,
            rng_seed=self.model.seed_for_driver_step(self.driver_id,self.search_time_s),preferred_exit_id=self.attributes.preferred_exit_id,
            search_speed_m_per_s=self.model.search_speed_m_per_s,max_walking_distance_m=self.attributes.max_walking_distance_m,
            approach_times_s=self._candidate_times,availability_probabilities=self._candidate_probabilities,
            decision_interval_s=self.model.decision_interval_s,failure_delay_s=self.model.failure_delay_s,
            remaining_search_time_s=max(0.,self.model.max_search_time_s-self.search_time_s),
            cpt_parameters=self.spec.cpt_parameters)

    def _select_target(self,decision):
        target=self.model.facility.space_by_id[decision.chosen_space_id]
        self.chosen_space_id=target.space_id;self.chosen_module=target.module_id
        if self.last_module is not None and self.last_module!=target.module_id:self.module_switches+=1
        self.last_module=target.module_id;self.utility_of_chosen_action=decision.chosen_utility
        self.route=self.model.navigation.route((self.x_m,self.y_m),self.model.navigation.space_nodes[target.space_id])
        self.patrol_goal=None;self.state=DriverState.TARGETING
        self.information_aisle_id=None
        self.attempt_ready_s=self.model.clock_s+self._candidate_times[target.space_id]
        observation=self._observations_by_id.get(target.space_id)
        distance=math.dist((self.x_m,self.y_m),(target.x_m,target.y_m))
        if distance>self.model.perception_radius_m+1e-9:self.remote_targets_selected+=1
        self.log('TargetSelected',space=target,utility=decision.chosen_utility,details=dict(
            information_mode=self.information_mode,target_distance_at_selection_m=distance,
            information_source=observation.information_source if observation else 'custom',
            report_time_s=observation.observed_at_s if observation else None))

    def _advance_route(self,dt,count_search=True):
        budget=self.model.search_speed_m_per_s*dt
        while self.route:
            x,y=self.route[0];dx=x-self.x_m;dy=y-self.y_m;distance=math.hypot(dx,dy)
            if distance<1e-9:self.route.pop(0);continue
            if budget<=1e-9:break
            move=min(distance,budget);self.x_m+=dx/distance*move;self.y_m+=dy/distance*move;budget-=move
            if count_search:self.search_distance_m+=move
            self.path.append((self.x_m,self.y_m))
            if move>=distance-1e-9:self.route.pop(0)
        if dt and self.state in (DriverState.SEARCHING,DriverState.TARGETING):
            self.log('VehicleMovingToTarget' if self.state==DriverState.TARGETING else 'VehicleSearchingAisle')

    def park_at(self,space,utility):
        self.state=DriverState.PARKED;self.chosen_space_id=space.space_id;self.chosen_module=space.module_id
        self.utility_of_chosen_action=utility;self.parking_time_s=self.model.clock_s
        self.search_ended_s=self.parking_time_s;self.search_time_s=self.search_ended_s-self.search_started_s
        self.walking_distance_m=math.dist((space.x_m,space.y_m),self.attributes.destination)
        self.x_m=space.x_m;self.y_m=space.y_m;self.path.append((self.x_m,self.y_m))
        self.destination_ready_s=self.parking_time_s+self.walking_distance_m/self.model.walk_speed_m_per_s
        self.violation=bool((space.accessible and not self.attributes.accessibility_eligibility) or
            (space.reserved_type and self.attributes.permit_type!=(space.permit_requirement or space.reserved_type)))
        self.log('SpaceClaimSucceeded',space=space,utility=utility);self.log('ParkingStarted',space=space,utility=utility)

    def _start_exiting(self):
        if self.chosen_space_id:self.model.release_parking(self,self.chosen_space_id)
        self.state=DriverState.EXITING;self.log('ParkingEnded',space_id=self.chosen_space_id)
        exits=self.model.facility.exit_points
        if exits:
            ids=self.model.facility.exit_point_ids
            index=ids.index(self.attributes.preferred_exit_id) if self.attributes.preferred_exit_id in ids else 0
            node=self.model.navigation._node(exits[index])
            self.route=self.model.navigation.route((self.x_m,self.y_m),node)
        else:self.route=[]
