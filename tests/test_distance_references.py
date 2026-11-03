from dataclasses import replace
from statistics import median
import math
import pytest

from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.references import ReferencePoints, lot_distance_references
from panda_abm.behavior.decision.cpt import CPTDecisionModel
from panda_abm.behavior.decision.base import DecisionContext
from panda_abm.behavior.parameters import BehavioralParameters
from panda_abm.environment import load_facility_from_lot_config, ParkingSpace


def test_factory_references_follow_chosen_door_exit_and_walking_limits():
    facility = load_facility_from_lot_config('data/lot_config.json')
    population = make_population(facility, size=20, personas=('convenience_seeker','accessibility_seeking'))
    for driver in population.drivers:
        a, r = driver.attributes, driver.reference_points
        usable = [s for s in facility.spaces if not s.unavailable
                  and s.is_compatible_with_vehicle(a.vehicle_type)
                  and (not s.accessible or a.accessibility_eligibility)
                  and (not s.reserved_type or a.permit_type == (s.permit_requirement or s.reserved_type))
                  and (a.max_walking_distance_m is None or math.dist((s.x_m,s.y_m),a.destination)<=a.max_walking_distance_m)]
        assert r.r_walk_m == pytest.approx(median(math.dist((s.x_m,s.y_m),a.destination) for s in usable))
        assert r.r_exit_m == pytest.approx(median(getattr(s,f'distance_to_{a.preferred_exit_id}_m') for s in usable))
        assert r.reference_space_count == len(usable)
        assert r.r_exit_m > 0
        if a.max_walking_distance_m is not None:
            assert r.r_walk_m <= a.max_walking_distance_m


def test_references_are_order_independent_and_do_not_mutate_explicit_input():
    facility = load_facility_from_lot_config('data/lot_config.json')
    a = make_population(facility,size=1).drivers[0].attributes
    explicit = ReferencePoints(r_walk_m=75,r_exit_m=80)
    r = lot_distance_references(facility,a,explicit)
    assert r == lot_distance_references(replace(facility,spaces=tuple(reversed(facility.spaces))),a,explicit)
    assert explicit.r_walk_m == 75 and explicit.r_exit_m == 80
    empty = lot_distance_references(replace(facility,spaces=()),a,explicit)
    assert empty.r_walk_m == 75 and empty.r_exit_m == 80
    assert empty.reference_space_count == 0


def test_distance_gains_and_losses_are_relative_to_nonzero_expectations():
    # Isolate distance references; certainty removes failure-outcome effects.
    params = BehavioralParameters(beta_walk=1,beta_exit=1,beta_search=0,
                                  acceptance_utility_threshold=0)
    ctx = DecisionContext('D',params,ReferencePoints(r_walk_m=100,r_exit_m=150),0,(0,0),(0,0),preferred_exit_id='exit_a')
    spaces = [ParkingSpace('better','A',50,0,distance_to_exit_a_m=100),
              ParkingSpace('expected','A',100,0,distance_to_exit_a_m=150),
              ParkingSpace('worse','A',150,0,distance_to_exit_a_m=200)]
    result = CPTDecisionModel().evaluate_candidates(ctx,spaces)
    better, expected, worse = result.candidate_evaluations
    assert better.diagnostics['success_outcome'] > 0
    assert expected.diagnostics['success_outcome'] == pytest.approx(0)
    assert worse.diagnostics['success_outcome'] < 0
    assert better.utility > expected.utility > worse.utility
    assert expected.diagnostics['r_exit_m'] == 150
