"""Reusable plotting functions for PANDA-ABM outputs.

Author: Judith Njoku
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

__author__ = "Judith Njoku"


def plot_search_time_distribution(agent_metrics: pd.DataFrame, save_path: str | Path | None = None):
    required = {"decision_model", "search_time"}
    _validate_columns(agent_metrics, required)
    fig, ax = plt.subplots(figsize=(8, 5))
    for model_name, group in agent_metrics.groupby("decision_model"):
        group["search_time"].dropna().plot(kind="hist", bins=15, alpha=0.45, ax=ax, label=model_name)
    ax.set_title("Search Time Distribution By Decision Model")
    ax.set_xlabel("Search time (s)")
    ax.set_ylabel("Driver count")
    ax.legend()
    ax.grid(alpha=0.25)
    _save(fig, save_path)
    return fig, ax


def plot_walking_distance_boxplot(agent_metrics: pd.DataFrame, save_path: str | Path | None = None):
    required = {"decision_model", "walking_distance"}
    _validate_columns(agent_metrics, required)
    fig, ax = plt.subplots(figsize=(8, 5))
    grouped = [
        (name, group["walking_distance"].dropna().to_numpy())
        for name, group in agent_metrics.groupby("decision_model")
    ]
    labels = [name for name, values in grouped if len(values)]
    data = [values for _, values in grouped if len(values)]
    if data:
        ax.boxplot(data)
        ax.set_xticklabels(labels)
    else:
        ax.text(0.5, 0.5, "No parked drivers", ha="center", va="center")
    ax.set_title("Walking Distance By Decision Model")
    ax.set_xlabel("Decision model")
    ax.set_ylabel("Walking distance (m)")
    ax.grid(alpha=0.25)
    _save(fig, save_path)
    return fig, ax


def plot_occupancy_over_time(system_metrics: pd.DataFrame, save_path: str | Path | None = None):
    required = {"decision_model", "timestep_s", "occupancy_rate"}
    _validate_columns(system_metrics, required)
    fig, ax = plt.subplots(figsize=(9, 5))
    for model_name, group in system_metrics.groupby("decision_model"):
        mean_curve = group.groupby("timestep_s")["occupancy_rate"].mean().reset_index()
        ax.plot(mean_curve["timestep_s"], mean_curve["occupancy_rate"], label=model_name)
    ax.set_title("Mean Occupancy Rate Over Time")
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Occupancy rate")
    ax.set_ylim(0.0, 1.0)
    ax.legend()
    ax.grid(alpha=0.25)
    _save(fig, save_path)
    return fig, ax


def plot_chosen_space_distribution(agent_metrics: pd.DataFrame, save_path: str | Path | None = None):
    required = {"chosen_space"}
    _validate_columns(agent_metrics, required)
    chosen = agent_metrics["chosen_space"].dropna()
    fig, ax = plt.subplots(figsize=(10, 5))
    if chosen.empty:
        ax.text(0.5, 0.5, "No parked drivers", ha="center", va="center")
        ax.set_axis_off()
    else:
        counts = chosen.value_counts().head(20)
        counts.sort_values().plot(kind="barh", ax=ax)
        ax.set_title("Most Frequently Chosen Spaces")
        ax.set_xlabel("Selections")
        ax.set_ylabel("Space ID")
        ax.grid(axis="x", alpha=0.25)
    _save(fig, save_path)
    return fig, ax


def _validate_columns(df: pd.DataFrame, required: set[str]) -> None:
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def _save(fig, save_path: str | Path | None) -> None:
    if save_path is None:
        return
    path = Path(save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
