import copy
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from panda_abm.behavior.factory import make_population
from panda_abm.behavior.parameters import BehavioralParameters
from panda_abm.behavior.references import ReferencePoints
from panda_abm.behavior.decision import CPTDecisionModel, DecisionContext, DeterministicUtilityModel, RandomUtilityModel
from panda_abm.core.model import ParkingModel
from panda_abm.environment import ParkingSpace, load_facility_from_lot_config
from scripts.update_lot_distances import update_distances


def test_all_existing_spaces_have_distances_to_four_landmarks():
    raw = json.loads(Path('data/lot_config.json').read_text())
    assert len(raw['slots']) == 1315
    assert len(raw['walmart_doors']) == len(raw['parking_lot_exits']) == 2
    assert {p['id'] for p in raw['entry_points']} == {p['id'] for p in raw['exit_points']}
    for slot in raw['slots']:
        for key in ('walmart_doors', 'parking_lot_exits'):
            for point in raw[key]:
                expected = math.hypot(slot['local_x_m'] - point['local_x_m'], slot['local_y_m'] - point['local_y_m'])
                assert slot[f"distance_to_{point['id']}_m"] == pytest.approx(expected, abs=0.001)
        assert 'distance_to_entrance_m' not in slot
        assert 'distance_to_nearest_vehicle_access_m' not in slot


def test_refresh_is_repeatable_and_syncs_access_points():
    raw = json.loads(Path('data/lot_config.json').read_text())
    original_slots = [(p['id'], p['lat'], p['lon'], p['local_x_m'], p['local_y_m']) for p in raw['slots']]
    once = update_distances(copy.deepcopy(raw))
    assert update_distances(copy.deepcopy(once)) == once
    assert [(p['id'], p['lat'], p['lon'], p['local_x_m'], p['local_y_m']) for p in once['slots']] == original_slots
    once['parking_lot_exits'][0]['lat'] += 0.0001
    changed = update_distances(once)
    assert changed['entry_points'][0]['lat'] == changed['parking_lot_exits'][0]['lat']


def test_real_facility_uses_meters_doors_and_both_arrival_points():
    facility = load_facility_from_lot_config('data/lot_config.json')
    assert facility.coordinate_system == 'local_m'
    assert len(facility.walmart_doors) == len(facility.entry_points) == len(facility.exit_points) == 2
    assert all(-70 < y < -55 for x, y in facility.walmart_doors)
    population = make_population(facility, size=4)
    assert {d.attributes.destination for d in population.drivers} == set(facility.walmart_doors)
    model = ParkingModel(facility, population, initial_occupancy_rate=0)
    assert {(a.x_m, a.y_m) for a in model.agents} == set(facility.entry_points)
    for agent in model.agents:
        attrs=agent.attributes
        assert attrs.preferred_exit_id == attrs.arrival_exit_id
        assert (agent.x_m,agent.y_m) == facility.entry_points[facility.entry_point_ids.index(attrs.arrival_exit_id)]
        assert attrs.destination == facility.walmart_doors[facility.walmart_door_ids.index(attrs.walmart_door_id)]
    model.step()
    assert {r.details['arrival_exit_id'] for r in model.event_logger.records if r.event_type=='AgentArrived'} == {'exit_a'}


@pytest.mark.parametrize('decision_model', [DeterministicUtilityModel, RandomUtilityModel, CPTDecisionModel])
def test_exit_preference_increases_value_of_space_near_access(decision_model):
    # Equal walking distance isolates the new access preference from walking.
    near = ParkingSpace('near_access', 'A', 20, 0, distance_to_exit_a_m=10, distance_to_exit_b_m=250)
    far = ParkingSpace('far_access', 'A', -20, 0, distance_to_exit_a_m=200, distance_to_exit_b_m=10)
    context = DecisionContext(
        driver_id='D', behavioral_parameters=BehavioralParameters(beta_exit=1, acceptance_utility_threshold=0),
        reference_points=ReferencePoints(), accumulated_search_time_s=0,
        current_position_m=(0, 0), destination_m=(0, 0), rng_seed=42,
        preferred_exit_id='exit_a',
    )
    result = decision_model().evaluate_candidates(context, [far, near])
    utilities = {e.space_id: e.utility for e in result.candidate_evaluations}
    assert utilities['near_access'] > utilities['far_access']
    other_exit = replace(context, preferred_exit_id='exit_b')
    other_result = decision_model().evaluate_candidates(other_exit, [far, near])
    other_utilities = {e.space_id:e.utility for e in other_result.candidate_evaluations}
    assert other_utilities['far_access'] > other_utilities['near_access']
    neutral = replace(context, behavioral_parameters=replace(context.behavioral_parameters, beta_exit=0))
    result = decision_model().evaluate_candidates(neutral, [far, near])
    assert result.candidate_evaluations[0].utility == pytest.approx(result.candidate_evaluations[1].utility)
