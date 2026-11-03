from dataclasses import replace
from collections import Counter
import json

import pytest

from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.parameters import PERSONA_PARAMETER_PROFILES, parameters_for_persona
from panda_abm.behavior.references import ReferencePoints
from panda_abm.behavior.decision import CPTDecisionModel, DecisionContext, DeterministicUtilityModel, RandomUtilityModel
from panda_abm.environment import ParkingSpace, generate_synthetic_facility
from panda_abm.environment import load_facility_from_lot_config

MODELS=[DeterministicUtilityModel,RandomUtilityModel,CPTDecisionModel]


def context(persona,**kw):
    return DecisionContext(driver_id='probe',behavioral_parameters=replace(parameters_for_persona(persona),acceptance_utility_threshold=0),
        reference_points=ReferencePoints(),accumulated_search_time_s=0,current_position_m=(0,0),destination_m=(0,0),rng_seed=42,**kw)


def utilities(model,persona,spaces,**kw):
    result=model().evaluate_candidates(context(persona,**kw),spaces)
    return {e.space_id:e.utility for e in result.candidate_evaluations}


def test_mix_is_balanced_repeatable_and_covers_new_personas():
    facility=generate_synthetic_facility()
    names=tuple(PERSONA_PARAMETER_PROFILES)
    a=make_population(facility,size=80,seed=42,personas=names)
    b=make_population(facility,size=80,seed=42,personas=names)
    assert a.as_dict()==b.as_dict()
    assert Counter(d.attributes.persona for d in a.drivers)=={n:16 for n in names}
    for d in a.drivers:
        if d.attributes.persona=='accessibility_seeking':
            assert d.attributes.accessibility_eligibility and d.attributes.permit_type=='accessible'
            assert d.attributes.max_walking_distance_m==120
    with pytest.raises(ValueError):make_population(facility,personas=('unknown',))
    with pytest.raises(ValueError):make_population(facility,personas=())


def test_lot_config_prices_reach_cost_sensitive_decisions(tmp_path):
    path=tmp_path/'priced_lot.json'
    path.write_text(json.dumps({'meta':{'lot_name':'Price probe'},'slots':[
        {'id':'paid','local_x_m':10,'local_y_m':0,'price_per_hour':9},
        {'id':'free','local_x_m':200,'local_y_m':0,'price_per_hour':0},
    ]}))
    facility=load_facility_from_lot_config(path)
    result=DeterministicUtilityModel().evaluate_candidates(context('cost_sensitive'),list(facility.spaces))
    assert result.chosen_space_id=='free'


@pytest.mark.parametrize('model',MODELS)
def test_cost_sensitive_trades_walking_for_price(model):
    spaces=[ParkingSpace('near_paid','A',10,0,price_per_hour=9),ParkingSpace('far_free','A',200,0)]
    baseline=utilities(model,'convenience_seeker',spaces)
    cost=utilities(model,'cost_sensitive',spaces)
    assert baseline['near_paid']>baseline['far_free']
    assert cost['far_free']>cost['near_paid']


@pytest.mark.parametrize('model',MODELS)
def test_time_sensitive_prefers_quicker_approach_at_equal_walking_distance(model):
    spaces=[ParkingSpace('near_car','A',100,0),ParkingSpace('far_car','A',-100,0)]
    ctx=replace(context('time_sensitive'),current_position_m=(100,0))
    result=model().evaluate_candidates(ctx,spaces)
    u={e.space_id:e.utility for e in result.candidate_evaluations}
    assert u['near_car']>u['far_car']


@pytest.mark.parametrize('model',MODELS)
def test_risk_averse_avoids_rule_violation_when_illegal_alternatives_are_exposed(model):
    spaces=[ParkingSpace('near_illegal','A',10,0,reserved_type='staff'),ParkingSpace('far_legal','A',200,0)]
    baseline=utilities(model,'convenience_seeker',spaces,allow_illegal_alternatives=True)
    risk=utilities(model,'risk_averse',spaces,allow_illegal_alternatives=True)
    assert baseline['near_illegal']>baseline['far_legal']
    assert risk['far_legal']>risk['near_illegal']
    safe=model().evaluate_candidates(context('risk_averse'),spaces)
    assert not safe.candidate_evaluations[0].feasible


@pytest.mark.parametrize('model',MODELS)
def test_accessibility_seeking_prefers_accessible_spaces_but_respects_walking_cap(model):
    spaces=[ParkingSpace('regular','A',10,0),ParkingSpace('accessible','A',50,0,accessible=True),
        ParkingSpace('too_far','A',121,0,accessible=True)]
    ctx=context('accessibility_seeking',accessibility_eligibility=True,permit_type='accessible',max_walking_distance_m=120)
    result=model().evaluate_candidates(ctx,spaces)
    u={e.space_id:e.utility for e in result.candidate_evaluations}
    assert u['accessible']>u['regular']
    assert not result.candidate_evaluations[2].feasible
