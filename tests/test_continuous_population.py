from dataclasses import replace
import numpy as np
import pytest
from panda_abm.behavior.factory import make_population
from panda_abm.behavior.continuous import PopulationPriors,PREFERENCE_MEANS
from panda_abm.behavior.population import PopulationSpec
from panda_abm.core.model import ParkingModel
from panda_abm.environment import generate_synthetic_facility


def test_primary_population_has_no_assigned_personas_and_is_reproducible():
    f=generate_synthetic_facility()
    a=make_population(f,size=100,seed=42);b=make_population(f,size=100,seed=42)
    assert a.as_dict()==b.as_dict()
    assert all(d.attributes.persona is None for d in a.drivers)
    assert a.generation_method=='continuous_generic_v1'
    for field in PREFERENCE_MEANS:
        assert len({getattr(d.behavioral_parameters,field) for d in a.drivers})==100
    for d in a.drivers:
        assert sum(getattr(d.behavioral_parameters,k) for k in PREFERENCE_MEANS)==pytest.approx(3.2)
        assert d.cpt_parameters.lambda_loss>0
    assert len({d.cpt_parameters.lambda_loss for d in a.drivers})==100


def test_homogeneous_control_keeps_trips_constraints_but_removes_preference_variation():
    f=generate_synthetic_facility()
    a=make_population(f,size=200,seed=42);b=make_population(f,size=200,seed=42,heterogeneous=False)
    assert [d.attributes for d in a.drivers]==[d.attributes for d in b.drivers]
    assert len({d.behavioral_parameters for d in b.drivers})==1
    assert len({d.cpt_parameters for d in b.drivers})==1
    assert len({d.reference_points.r_search_s for d in b.drivers})==1
    assert {d.attributes.accessibility_eligibility for d in a.drivers}=={False,True}
    assert any(d.attributes.mobility_limitation and not d.attributes.accessibility_eligibility for d in a.drivers)
    assert any(d.attributes.accessibility_eligibility and not d.attributes.mobility_limitation for d in a.drivers)
    for d in a.drivers:
        if d.attributes.mobility_limitation:assert 50<=d.attributes.max_walking_distance_m<=150
        else:assert d.attributes.max_walking_distance_m is None


def test_parameter_modes_do_not_resample_attributes_or_preferences():
    f=generate_synthetic_facility()
    a=make_population(f,size=20);b=make_population(f,size=20,cpt_parameter_mode='shared')
    assert [d.attributes for d in a.drivers]==[d.attributes for d in b.drivers]
    assert [d.behavioral_parameters for d in a.drivers]==[d.behavioral_parameters for d in b.drivers]
    assert [d.reference_points for d in a.drivers]==[d.reference_points for d in b.drivers]
    with pytest.raises(TypeError):make_population(f,personas=('risk_averse',))


@pytest.mark.parametrize('model_name',['deterministic','rum','cpt'])
def test_descriptive_label_changes_cannot_change_physics_or_decisions(model_name):
    f=generate_synthetic_facility()
    p=make_population(f,size=8,seed=42)
    renamed=replace(p,drivers=tuple(replace(d,attributes=replace(d.attributes,persona='arbitrary_descriptive_label')) for d in p.drivers))
    signatures=[]
    for pop in (p,renamed):
        model=ParkingModel(f,pop,decision_model=model_name,seed=42)
        model.run_until_complete()
        signatures.append([(a.driver_id,a.chosen_space_id,a.search_time_s,tuple(a.path)) for a in model.agents])
    assert signatures[0]==signatures[1]


def test_common_random_numbers_available_across_decision_models():
    f=generate_synthetic_facility();p=make_population(f,size=1)
    models=[ParkingModel(f,p,decision_model=name,decision_seed_namespace='matched',run_id='same') for name in ('deterministic','rum','cpt')]
    assert len({m.seed_for_driver_step('D0000',20) for m in models})==1


@pytest.mark.parametrize('kwargs',[{'preference_concentration':0},{'walking_limit_min_m':200},{'cpt_value_mean':1},{'accessibility_probability':2}])
def test_invalid_structural_priors_rejected(kwargs):
    with pytest.raises(ValueError):PopulationPriors(**kwargs)


@pytest.mark.parametrize('name',['deterministic','rum','cpt'])
def test_all_models_share_deadline_feasibility(name):
    from panda_abm.behavior import BehavioralParameters,ReferencePoints
    from panda_abm.behavior.decision import DecisionContext
    from panda_abm.core.model import DECISION_MODELS
    from panda_abm.environment import ParkingSpace
    ctx=DecisionContext('D',BehavioralParameters(),ReferencePoints(),0,(0,0),(0,0),
        approach_times_s={'S':20},remaining_search_time_s=10)
    result=DECISION_MODELS[name]().evaluate_candidates(ctx,[ParkingSpace('S','A',10,0)])
    assert not result.candidate_evaluations[0].feasible
    assert result.chosen_action=='continue'
