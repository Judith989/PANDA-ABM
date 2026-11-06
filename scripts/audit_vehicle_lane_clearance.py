"""Report estimated bay/lane conflicts without silently changing site geometry.

This static screening assumes every bay is occupied by the largest configured
vehicle. It is deliberately conservative and is not a congestion measurement.
"""
import argparse
import json
import math
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]


def audit(path):
    raw = json.loads(path.read_text(encoding="utf8"))
    network = raw["aisle_network"]
    nodes = network["nodes"]
    slots = raw["slots"]
    centres = {(round(s["local_x_m"], 7), round(s["local_y_m"], 7)) for s in slots}
    from panda_abm.environment.pedestrian_geometry import bay_polygon
    bays = [Polygon(bay_polygon(dict(s, length_m=5.55, width_m=2.12))) for s in slots]
    tree = STRtree(bays)
    conflicts = []
    seen = set()
    for start, end in network["edges"]:
        p, q = nodes[start], nodes[end]
        if any(tuple(round(v, 7) for v in x) in centres for x in (p, q)):
            continue  # Bay entry is checked separately by the maneuver guard.
        directions = [(start, end)] if network.get("directed") else [(start, end), (end, start)]
        for a, b in directions:
            if (a, b) in seen:
                continue
            seen.add((a, b))
            p, q = nodes[a], nodes[b]
            length = math.dist(p, q)
            if length < 1e-8:
                continue
            ux, uy = (q[0]-p[0])/length, (q[1]-p[1])/length
            # Same 1.2-m right offset and largest-vehicle width as the engine.
            points = [(x+uy*1.2, y-ux*1.2) for x, y in (p, q)]
            corridor = LineString(points).buffer(1.06, cap_style=2)
            hits = tree.query(corridor, predicate="intersects")
            if len(hits):
                conflicts.append({"edge": [a, b], "bay_ids": [slots[int(i)]["id"] for i in hits]})
    return {"config": str(path.relative_to(ROOT)), "screening_only": True,
            "assumption": "All bays occupied by 5.45 m x 2.02 m vehicles, with 0.1 m footprint padding",
            "directed_road_segments": len(seen), "conflicting_segments": len(conflicts),
            "conflicts": conflicts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"research/vehicle_clearance_20261105/lane_screening.json")
    args = parser.parse_args()
    reports = [audit(ROOT/"data"/name) for name in (
        "lot_config.json", "lot_config.satellite_estimated.json",
        "lot_config.downtown_laramie.json", "lot_config.synthetic.json")]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, indent=2)+"\n", encoding="utf8")
    for report in reports:
        print(report["config"], report["conflicting_segments"], "conflicting road directions of", report["directed_road_segments"])
