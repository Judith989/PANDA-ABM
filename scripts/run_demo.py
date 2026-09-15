"""Run a small PANDA-ABM demonstration experiment.

Author: Judith Njoku
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from panda_abm.simulation import RunConfig, run_decision_model_comparison, summarize_agent_metrics

__author__ = "Judith Njoku"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small PANDA-ABM demo.")
    parser.add_argument("--output", default="results/demo", help="Folder where CSVs, plots, and JSON exports are written.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible results.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = RunConfig(
        scenario_id="demo",
        seed=args.seed,
        repetitions=3,
        population_size=18,
        initial_occupancy_rate=0.30,
    )
    outputs = run_decision_model_comparison(config=config, output_dir=args.output)
    summary = summarize_agent_metrics(outputs["agent_metrics"])

    print("\nPANDA-ABM demo complete")
    print(f"Author: Judith Njoku")
    print(f"Output folder: {Path(args.output).resolve()}")
    print("\nModel comparison summary:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
