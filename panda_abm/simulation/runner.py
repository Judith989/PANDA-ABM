"""Experiment runner for matched decision-model simulations.

Author: Judith Njoku
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from panda_abm.analysis import (
    plot_chosen_space_distribution,
    plot_occupancy_over_time,
    plot_search_time_distribution,
    plot_walking_distance_boxplot,
)
from panda_abm.behavior.factory import make_population
from panda_abm.behavior.population import PopulationSpec
from panda_abm.core.model import ParkingModel
from panda_abm.environment import Facility, generate_synthetic_facility
from panda_abm.export import export_event_stream_json, export_trajectory_json, export_twin_state_json
from panda_abm.twin import build_twin_state

__author__ = "Judith Njoku"


@dataclass(frozen=True)
class RunConfig:
    scenario_id: str = "demo"
    seed: int = 42
    repetitions: int = 5
    population_size: int = 24
    heterogeneous: bool = True
    initial_occupancy_rate: float = 0.25
    decision_models: tuple[str, ...] = ("deterministic", "rum", "cpt")


def run_decision_model_comparison(
    config: RunConfig = RunConfig(),
    output_dir: str | Path = "results",
    facility: Facility | None = None,
    population: PopulationSpec | None = None,
) -> dict[str, pd.DataFrame]:
    """Run M0/M1/M2 on matched synthetic conditions and save results."""

    output_dir = Path(output_dir)
    facility = facility or generate_synthetic_facility(seed=config.seed)
    population = population or make_population(
        facility,
        size=config.population_size,
        seed=config.seed,
        heterogeneous=config.heterogeneous,
    )

    agent_frames = []
    system_frames = []
    decision_frames = []
    trajectory_frames = []
    event_frames = []

    for rep in range(config.repetitions):
        rep_seed = config.seed + rep
        for decision_model in config.decision_models:
            run_id = f"{config.scenario_id}_{decision_model}_rep{rep:03d}"
            model = ParkingModel(
                facility=facility,
                population=population,
                decision_model=decision_model,
                run_id=run_id,
                scenario_id=config.scenario_id,
                seed=rep_seed,
                initial_occupancy_rate=config.initial_occupancy_rate,
            )
            model.run_until_complete()
            events = model.metrics.events()
            event_frames.append(events)
            agent_frames.append(model.metrics.final_agent_metrics())
            system_frames.append(model.metrics.system_metrics())
            decision_frames.append(model.metrics.decision_log())
            trajectories = model.metrics.trajectories()
            trajectory_frames.append(trajectories)
            metadata = {
                "state_type": "simulated_current",
                "scenario_id": config.scenario_id,
                "run_id": run_id,
                "replication_id": f"rep{rep:03d}",
                "decision_model": decision_model,
                "facility_id": facility.facility_id,
                "population_id": population.population_id,
                "seed": rep_seed,
                "author": "Judith Njoku",
            }
            export_trajectory_json(
                trajectories,
                output_dir / "twin_exports" / f"{run_id}.json",
                metadata=metadata,
            )
            export_event_stream_json(events, output_dir / "event_exports" / f"{run_id}.json", metadata=metadata)
            export_twin_state_json(build_twin_state(model), output_dir / "state_exports" / f"{run_id}.json")

    outputs = {
        "event_log": _concat_nonempty(event_frames),
        "agent_metrics": _concat_nonempty(agent_frames),
        "system_metrics": _concat_nonempty(system_frames),
        "decision_log": _concat_nonempty(decision_frames),
        "trajectories": _concat_nonempty(trajectory_frames),
    }
    _save_outputs(outputs, output_dir)
    if not outputs["agent_metrics"].empty:
        plot_search_time_distribution(outputs["agent_metrics"], output_dir / "figures" / "search_time_distribution.png")
        plot_walking_distance_boxplot(outputs["agent_metrics"], output_dir / "figures" / "walking_distance_boxplot.png")
        plot_chosen_space_distribution(outputs["agent_metrics"], output_dir / "figures" / "chosen_space_distribution.png")
    if not outputs["system_metrics"].empty:
        plot_occupancy_over_time(outputs["system_metrics"], output_dir / "figures" / "occupancy_over_time.png")
    return outputs


def summarize_agent_metrics(agent_metrics: pd.DataFrame) -> pd.DataFrame:
    """Return standard model-comparison metrics."""

    grouped = agent_metrics.groupby("decision_model", dropna=False)
    return grouped.agg(
        drivers=("driver_id", "count"),
        success_rate=("parked", "mean"),
        abandonment_rate=("abandoned", "mean"),
        mean_search_time=("search_time", "mean"),
        median_search_time=("search_time", "median"),
        p90_search_time=("search_time", lambda s: s.quantile(0.90)),
        mean_walking_distance=("walking_distance", "mean"),
        mean_search_distance=("search_distance", "mean"),
        mean_rejected_spaces=("rejected_spaces", "mean"),
    ).reset_index()


def _save_outputs(outputs: dict[str, pd.DataFrame], output_dir: Path) -> None:
    paths = {
        "event_log": output_dir / "raw" / "events" / "events.csv",
        "agent_metrics": output_dir / "raw" / "agents" / "agent_metrics.csv",
        "system_metrics": output_dir / "raw" / "system" / "system_metrics.csv",
        "decision_log": output_dir / "raw" / "decision_log.csv",
        "trajectories": output_dir / "raw" / "trajectories" / "trajectories.csv",
    }
    for key, df in outputs.items():
        path = paths[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    summary = summarize_agent_metrics(outputs["agent_metrics"])
    table_path = output_dir / "tables" / "model_comparison.csv"
    table_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(table_path, index=False)


def _concat_nonempty(frames: list[pd.DataFrame]) -> pd.DataFrame:
    valid = [frame.dropna(axis=1, how="all") for frame in frames if not frame.empty]
    return pd.concat(valid, ignore_index=True) if valid else pd.DataFrame()
