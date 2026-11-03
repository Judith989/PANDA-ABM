"""Regression tests for publication audit failures, not hypothesis tests."""
import importlib.util
from pathlib import Path
import pandas as pd
import pytest
from panda_abm.behavior.continuous import make_population
from panda_abm.core.model import ParkingModel
from panda_abm.environment import generate_synthetic_facility


@pytest.mark.parametrize('radius',[-1,float('nan'),float('inf')])
def test_invalid_visibility_cannot_silently_change_observation_scope(radius):
    facility=generate_synthetic_facility()
    with pytest.raises(ValueError):
        ParkingModel(facility,make_population(facility,size=1),perception_radius_m=radius)


def test_abandonment_does_not_reduce_reported_parked_walking_distance():
    path=Path(__file__).resolve().parents[1]/'scripts/analyze_continuous_population.py'
    pytest.importorskip('sklearn')
    spec=importlib.util.spec_from_file_location('continuous_audit_summary',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    common=dict(scenario='s',population='p',model='m',violation=False,rejected_candidates=0)
    frame=pd.DataFrame([dict(**common,driver='parked',success=True,walk_m=100.,search_s=10),
                        dict(**common,driver='abandoned',success=False,walk_m=0.,search_s=600)])
    row=module.summarize_models(frame).iloc[0]
    assert row.mean_walk_parked_m==100
    assert row.mean_search_s==305
    assert row.drivers==2 and row.parked==1


def test_profile_validation_cannot_include_training_replications():
    pytest.importorskip('sklearn')
    from panda_abm.analysis.profiles import explore_behavioral_regimes
    with pytest.raises(ValueError,match='disjoint'):
        explore_behavioral_regimes(pd.DataFrame(),[1,2],[2,3])


def test_profile_stability_cannot_be_assumed_without_bootstrap_refits():
    pytest.importorskip('sklearn')
    from panda_abm.analysis.profiles import explore_behavioral_regimes
    with pytest.raises(ValueError,match='positive'):
        explore_behavioral_regimes(pd.DataFrame(),[1],[2],bootstrap_repetitions=0)


def test_standard_runner_summary_also_excludes_unobserved_walking():
    from panda_abm.simulation.runner import summarize_agent_metrics
    common=dict(decision_model='m',rejected_spaces=0,search_distance=10)
    frame=pd.DataFrame([dict(**common,driver_id='parked',parked=True,abandoned=False,walking_distance=100.,search_time=10),
                        dict(**common,driver_id='failed',parked=False,abandoned=True,walking_distance=0.,search_time=600)])
    row=summarize_agent_metrics(frame).iloc[0]
    assert row.mean_walking_distance==100
    assert row.mean_search_time==305


def test_exported_failed_driver_has_no_realized_walk_or_parked_space():
    facility=generate_synthetic_facility(91)
    model=ParkingModel(facility,make_population(facility,size=1,seed=91),initial_occupancy_rate=1)
    model.run_until_complete()
    frame=model.metrics.final_agent_metrics()
    assert frame.abandoned.all() and not frame.parked.any()
    assert frame.walking_distance.isna().all() and frame.chosen_space.isna().all()
