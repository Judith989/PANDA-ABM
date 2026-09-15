"""Tests for the runnable PANDA-ABM simulation layer.

Author: Judith Njoku
"""

from __future__ import annotations

import json
from dataclasses import replace

from panda_abm.behavior.factory import make_population
from panda_abm.core.model import ParkingModel
from panda_abm.environment import generate_synthetic_facility
from panda_abm.forecasting import PerfectForecastProvider
from panda_abm.simulation import RunConfig, run_decision_model_comparison

__author__ = "Judith Njoku"


def test_decision_model_comparison_writes_standard_outputs(tmp_path):
    config = RunConfig(
        scenario_id="pytest_demo",
        seed=7,
        repetitions=2,
        population_size=8,
        initial_occupancy_rate=0.20,
    )

    outputs = run_decision_model_comparison(config=config, output_dir=tmp_path)

    assert not outputs["agent_metrics"].empty
    assert not outputs["system_metrics"].empty
    assert not outputs["decision_log"].empty
    assert not outputs["trajectories"].empty
    assert not outputs["event_log"].empty
    assert set(outputs["agent_metrics"]["decision_model"]) == {"deterministic", "rum", "cpt"}

    expected_files = [
        tmp_path / "raw" / "events" / "events.csv",
        tmp_path / "raw" / "agents" / "agent_metrics.csv",
        tmp_path / "raw" / "system" / "system_metrics.csv",
        tmp_path / "raw" / "decision_log.csv",
        tmp_path / "raw" / "trajectories" / "trajectories.csv",
        tmp_path / "tables" / "model_comparison.csv",
        tmp_path / "figures" / "search_time_distribution.png",
        tmp_path / "figures" / "walking_distance_boxplot.png",
        tmp_path / "figures" / "chosen_space_distribution.png",
        tmp_path / "figures" / "occupancy_over_time.png",
    ]
    for path in expected_files:
        assert path.exists(), f"Missing expected output file: {path}"


def test_event_log_contains_the_main_driver_lifecycle(tmp_path):
    config = RunConfig(
        scenario_id="pytest_events",
        seed=11,
        repetitions=1,
        population_size=8,
        initial_occupancy_rate=0.10,
        decision_models=("rum",),
    )
    outputs = run_decision_model_comparison(config=config, output_dir=tmp_path)
    event_types = set(outputs["event_log"]["event_type"])

    expected = {
        "AgentArrived",
        "SearchStarted",
        "CandidateObserved",
        "TargetSelected",
        "SpaceClaimAttempted",
        "SpaceClaimSucceeded",
        "ParkingStarted",
        "SystemSnapshot",
    }
    assert expected.issubset(event_types)


def test_space_cannot_be_claimed_twice_before_release(tmp_path):
    config = RunConfig(
        scenario_id="pytest_resource_safety",
        seed=19,
        repetitions=1,
        population_size=20,
        initial_occupancy_rate=0.10,
        decision_models=("rum",),
    )
    outputs = run_decision_model_comparison(config=config, output_dir=tmp_path)
    events = outputs["event_log"].sort_values(["run_id", "time_s"]).reset_index(drop=True)

    active_by_run: dict[str, set[str]] = {}
    for row in events.itertuples(index=False):
        if not isinstance(row.space_id, str):
            continue
        active = active_by_run.setdefault(row.run_id, set())
        if row.event_type in {"InitialSpaceOccupied", "SpaceClaimSucceeded"}:
            assert row.space_id not in active, f"{row.space_id} was claimed twice before release in {row.run_id}"
            active.add(row.space_id)
        elif row.event_type == "SpaceReleased":
            active.discard(row.space_id)


def test_twin_json_export_contains_cesium_ready_fields(tmp_path):
    config = RunConfig(
        scenario_id="pytest_export",
        seed=13,
        repetitions=1,
        population_size=4,
        initial_occupancy_rate=0.10,
        decision_models=("rum",),
    )
    run_decision_model_comparison(config=config, output_dir=tmp_path)
    json_path = next((tmp_path / "twin_exports").glob("*.json"))

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["author"] == "Judith Njoku"
    assert payload["metadata"]["state_type"] == "simulated_current"
    assert payload["timesteps"]

    vehicle = payload["timesteps"][0]["vehicles"][0]
    assert {
        "vehicle_id",
        "persona",
        "state",
        "x_m",
        "y_m",
        "chosen_space_id",
        "search_time",
        "candidate_space_ids",
    }.issubset(vehicle)


def test_phase_two_json_exports_are_written(tmp_path):
    config = RunConfig(
        scenario_id="pytest_phase_two_exports",
        seed=23,
        repetitions=1,
        population_size=4,
        initial_occupancy_rate=0.10,
        decision_models=("rum",),
    )
    run_decision_model_comparison(config=config, output_dir=tmp_path)

    event_json = next((tmp_path / "event_exports").glob("*.json"))
    state_json = next((tmp_path / "state_exports").glob("*.json"))
    event_payload = json.loads(event_json.read_text(encoding="utf-8"))
    state_payload = json.loads(state_json.read_text(encoding="utf-8"))

    assert event_payload["metadata"]["author"] == "Judith Njoku"
    assert event_payload["events"]
    assert state_payload["state_type"] == "simulated_current"
    assert {"vehicles", "spaces", "system"}.issubset(state_payload)


def test_forecast_provider_does_not_mutate_occupancy_and_requires_guidance():
    facility = generate_synthetic_facility(seed=31)
    population = make_population(facility, size=2, seed=31, heterogeneous=False)
    first, second = population.drivers
    unguided = replace(first, attributes=replace(first.attributes, guidance_access=False))
    guided = replace(second, attributes=replace(second.attributes, guidance_access=True))
    population = replace(population, drivers=(unguided, guided))
    model = ParkingModel(
        facility=facility,
        population=population,
        decision_model="rum",
        seed=31,
        initial_occupancy_rate=0.25,
        forecast_provider=PerfectForecastProvider(),
    )

    before = model.resource_manager.occupied_count()
    forecast = model.forecast_provider.forecast(model, next(a for a in model.agents if a.driver_id == guided.driver_id))
    after = model.resource_manager.occupied_count()
    assert before == after
    assert forecast

    unguided_agent = next(a for a in model.agents if a.driver_id == unguided.driver_id)
    guided_agent = next(a for a in model.agents if a.driver_id == guided.driver_id)
    assert all(o.forecast_available_probability is None for o in model.perceive(unguided_agent))
    assert any(o.forecast_available_probability is not None for o in model.perceive(guided_agent))
