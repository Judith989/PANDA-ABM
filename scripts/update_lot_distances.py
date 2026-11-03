"""Rebuild estimated local coordinates and straight-line landmark distances.

Run after editing the landmark lat/lon values in data/lot_config.json.
Existing parking-space centers and restrictions are preserved.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from panda_abm.environment.coordinates import lat_lon_to_local_m


def update_distances(raw: dict) -> dict:
    meta = raw["meta"]
    # Keep the simulation's entry/exit lists in sync with the canonical driveways.
    raw["entry_points"] = [dict(p) for p in raw["parking_lot_exits"] if p["allows_entry"]]
    raw["exit_points"] = [dict(p) for p in raw["parking_lot_exits"] if p["allows_exit"]]
    for key in ("walmart_doors", "parking_lot_exits", "entry_points", "exit_points"):
        for point in raw[key]:
            x, y = lat_lon_to_local_m(point["lat"], point["lon"], meta["ref_lat"], meta["ref_lon"])
            point["local_x_m"], point["local_y_m"] = round(x, 3), round(y, 3)
    for slot in raw["slots"]:
        for point in raw["walmart_doors"] + raw["parking_lot_exits"]:
            slot[f"distance_to_{point['id']}_m"] = round(
                math.hypot(slot["local_x_m"] - point["local_x_m"], slot["local_y_m"] - point["local_y_m"]), 3
            )
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "data" / "lot_config.json")
    args = parser.parse_args()
    raw = update_distances(json.loads(args.config.read_text(encoding="utf-8")))
    args.config.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    print(f"Updated distances for {len(raw['slots'])} estimated spaces: {args.config}")


if __name__ == "__main__":
    main()
