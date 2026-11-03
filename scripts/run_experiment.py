"""Run a configurable PANDA-ABM M0/M1/M2 experiment.

Author: Judith Njoku
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from panda_abm.environment import load_facility_from_lot_config
from panda_abm.behavior.parameters import PERSONA_PARAMETER_PROFILES
from panda_abm.simulation import RunConfig, run_decision_model_comparison, summarize_agent_metrics

__author__ = "Judith Njoku"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PANDA-ABM decision-model experiments.")
    parser.add_argument("--output", default="results/experiment", help="Folder where outputs are written.")
    parser.add_argument(
        "--facility-config",
        default=None,
        help="Optional path to lot_config.json. If omitted, the synthetic facility is used.",
    )
    parser.add_argument("--scenario-id", default="baseline", help="Scenario label stored in all result files.")
    parser.add_argument("--seed", type=int, default=42, help="Base random seed.")
    parser.add_argument("--personas", nargs="+", choices=list(PERSONA_PARAMETER_PROFILES), default=None, help="Explicit legacy controlled mixture; omitted for generic continuous drivers.")
    parser.add_argument('--cpt-profile-mode',choices=['shared','persona'],default='shared',help='Only used with explicit controlled --personas.')
    parser.add_argument('--cpt-parameter-mode',choices=['continuous','shared'],default='continuous',help='Generic continuous per-driver CPT priors or shared TK92 benchmark.')
    parser.add_argument('--information-mode',choices=['unaided','aisle','space'],default='unaided',help='Local search, aggregate aisle counts, or current space availability reports.')
    parser.add_argument("--repetitions", type=int, default=10, help="Monte Carlo repetitions per decision model.")
    parser.add_argument("--population-size", type=int, default=48, help="Number of drivers in each repetition.")
    parser.add_argument("--initial-occupancy-rate", type=float, default=0.35, help="Initial occupied share of usable spaces.")
    parser.add_argument(
        "--homogeneous",
        action="store_true",
        help="Use one parameter set for all drivers instead of a heterogeneous synthetic population.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = RunConfig(
        scenario_id=args.scenario_id,
        seed=args.seed,
        personas=tuple(args.personas) if args.personas is not None else None,
        cpt_profile_mode=args.cpt_profile_mode,
        cpt_parameter_mode=args.cpt_parameter_mode,
        information_mode=args.information_mode,
        repetitions=args.repetitions,
        population_size=args.population_size,
        heterogeneous=not args.homogeneous,
        initial_occupancy_rate=args.initial_occupancy_rate,
    )

    facility = None
    if args.facility_config:
        facility = load_facility_from_lot_config(args.facility_config)

    outputs = run_decision_model_comparison(
        config=config,
        output_dir=args.output,
        facility=facility,
    )
    summary = summarize_agent_metrics(outputs["agent_metrics"])

    print("\nPANDA-ABM experiment complete")
    print("Author: Judith Njoku")
    print(f"Output folder: {Path(args.output).resolve()}")
    print("\nModel comparison summary:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
