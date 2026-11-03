"""JSON export for future Cesium integration.

Author: Judith Njoku
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

__author__ = "Judith Njoku"


def export_trajectory_json(trajectories: pd.DataFrame, path: str | Path, metadata: dict) -> None:
    """Write a Cesium-ready but Cesium-independent trajectory JSON file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    if not trajectories.empty:
        for timestep, group in trajectories.groupby("timestep_s"):
            records.append(
                {
                    "timestep_s": float(timestep),
                    "vehicles": [
                        {
                            "vehicle_id": row.driver_id,
                            "persona": row.persona,
                            "state": row.state,
                            "x_m": float(row.x_m),
                            "y_m": float(row.y_m),
                            "chosen_space_id": row.chosen_space if pd.notna(row.chosen_space) else None,
                            "search_time": float(row.search_time),
                            "candidate_space_ids": (
                                str(row.candidate_space_ids).split("|")
                                if pd.notna(row.candidate_space_ids) and str(row.candidate_space_ids)
                                else []
                            ),
                        }
                        for row in group.itertuples(index=False)
                    ],
                }
            )
    payload = {"metadata": metadata, "timesteps": records}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def export_event_stream_json(events: pd.DataFrame, path: str | Path, metadata: dict) -> None:
    """Write raw events as a simple JSON stream for later frontend use."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for row in events.to_dict(orient="records"):
        clean = {key: _json_value(value) for key, value in row.items()}
        records.append(clean)
    path.write_text(json.dumps({"metadata": metadata, "events": records}, indent=2), encoding="utf-8")


def export_twin_state_json(twin_state: dict, path: str | Path) -> None:
    """Write one full digital-twin state snapshot."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(twin_state, indent=2), encoding="utf-8")


def _json_value(value):
    if isinstance(value, (list, dict)):
        return value
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value
