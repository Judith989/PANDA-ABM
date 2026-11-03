from dataclasses import replace
import math
import pytest
from panda_abm.behavior import CPTParameters,ReferencePoints,BehavioralParameters
from panda_abm.behavior.cpt_parameters import PERSONA_CPT_PROFILES,cpt_parameters_for_persona
from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.decision import CPTDecisionModel,DecisionContext
from panda_abm.environment import ParkingSpace,generate_synthetic_facility


def test_profiles_are_explicit_and_only_evidenced_hypothesis_is_changed():
    assert cpt_parameters_for_persona('risk_averse').lambda_loss==3.
    for name,cp in PERSONA_CPT_PROFILES.items():
        if name!='risk_averse':assert cp==CPTParameters()
    with pytest.raises(ValueError):cpt_parameters_for_persona('unknown')


def test_profile_mode_preserves_matched_population_and_rng():
    f=generate_synthetic_facility()
    a=make_population(f,size=20,personas=tuple(PERSONA_CPT_PROFILES),cpt_profile_mode='shared')
    b=make_population(f,size=20,personas=tuple(PERSONA_CPT_PROFILES),cpt_profile_mode='persona')
    for x,y in zip(a.drivers,b.drivers):
        assert x.attributes==y.attributes
        assert x.behavioral_parameters==y.behavioral_parameters
        assert x.reference_points==y.reference_points
        assert x.cpt_parameters==CPTParameters()
        assert y.as_dict()['cpt_parameters']==y.cpt_parameters.as_dict()
    with pytest.raises(ValueError):make_population(f,cpt_profile_mode='invalid')


def test_context_parameters_used_but_model_override_has_precedence():
    ctx=DecisionContext('D',BehavioralParameters(),ReferencePoints(),0,(0,0),(0,0),cpt_parameters=CPTParameters(lambda_loss=3))
    candidates=[ParkingSpace('S','A',50,0)]
    dynamic=CPTDecisionModel().evaluate_candidates(ctx,candidates).candidate_evaluations[0]
    fixed=CPTDecisionModel(CPTParameters(lambda_loss=1)).evaluate_candidates(ctx,candidates).candidate_evaluations[0]
    assert dynamic.diagnostics['lambda_loss']==3
    assert fixed.diagnostics['lambda_loss']==1


def test_increasing_loss_aversion_penalizes_fixed_mixed_prospect():
    ctx=DecisionContext('D',BehavioralParameters(),ReferencePoints(),0,(0,0),(0,0),availability_probabilities={'S':.6})
    values=[]
    for coefficient in (1,1.6,2.25,3,4):
        e=CPTDecisionModel(CPTParameters(lambda_loss=coefficient)).evaluate_candidates(ctx,[ParkingSpace('S','A',50,0)]).candidate_evaluations[0]
        assert e.diagnostics['success_outcome']>0 and e.diagnostics['failure_outcome']<0
        values.append(e.utility)
    assert all(a>b for a,b in zip(values,values[1:]))


def test_unchanged_persona_profile_is_exact_decision_control():
    ctx=DecisionContext('D',BehavioralParameters(),ReferencePoints(),100,(0,0),(0,0),rng_seed=42)
    spaces=[ParkingSpace('A','A',30,0),ParkingSpace('B','A',100,0)]
    a=CPTDecisionModel().evaluate_candidates(replace(ctx,cpt_parameters=CPTParameters()),spaces)
    b=CPTDecisionModel().evaluate_candidates(replace(ctx,cpt_parameters=cpt_parameters_for_persona('time_sensitive')),spaces)
    assert a==b


@pytest.mark.parametrize('value',[float('nan'),float('inf'),0,-1])
def test_invalid_loss_aversion_rejected(value):
    with pytest.raises(ValueError):CPTParameters(lambda_loss=value)
