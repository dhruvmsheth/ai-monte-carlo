#!/usr/bin/env python
"""Run Monte Carlo simulation for one or all scenarios.

Usage:
    PYTHONPATH=. python scripts/run_simulation.py                        # all 5 scenarios, 100 draws
    PYTHONPATH=. python scripts/run_simulation.py --scenario s1          # single scenario
    PYTHONPATH=. python scripts/run_simulation.py --n-draws 10000        # full run
    PYTHONPATH=. python scripts/run_simulation.py --scenario s4 --n-draws 50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.simulation.runner import run_scenario

SCENARIOS_DIR = Path("configs/scenarios")
OUTPUT_DIR = Path("outputs/simulation")

SCENARIO_FILES = {
    "s1": "s1_laissez_faire.yaml",
    "s2": "s2_majority_50.yaml",
    "s3": "s3_supermajority_75.yaml",
    "s4": "s4_firm_consent_50.yaml",
    "s5": "s5_firm_consent_75.yaml",
}


def run_one(scenario_key: str, n_draws: int) -> dict:
    """Run a single scenario and save results."""
    scenario_file = SCENARIOS_DIR / SCENARIO_FILES[scenario_key]
    cfg = load_config(scenario_file)

    print(f"\n{'='*60}")
    print(f"Running {scenario_key}: {cfg.scenario.name} ({n_draws} draws)")
    print(f"{'='*60}")

    result = run_scenario(cfg=cfg, n_draws=n_draws, progress_interval=max(1, n_draws // 10))

    print(f"\n{result.summary_table()}")

    # Save results
    out_dir = OUTPUT_DIR / scenario_key
    out_dir.mkdir(parents=True, exist_ok=True)

    # Monthly time series
    if result.monthly_time_series is not None:
        result.monthly_time_series.to_csv(out_dir / "monthly_time_series.csv", index=False)

    # Aggregate summary
    with open(out_dir / "aggregate.json", "w") as f:
        json.dump(result.aggregate, f, indent=2)

    # Per-draw summaries
    draw_summaries = [dr.summary_dict() for dr in result.draw_results]
    pd.DataFrame(draw_summaries).to_csv(out_dir / "draw_summaries.csv", index=False)

    return result.aggregate


def main():
    parser = argparse.ArgumentParser(description="Run Monte Carlo simulation")
    parser.add_argument(
        "--scenario", "-s",
        choices=list(SCENARIO_FILES.keys()) + ["all"],
        default="all",
        help="Which scenario to run (default: all)",
    )
    parser.add_argument(
        "--n-draws", "-n",
        type=int,
        default=100,
        help="Number of Monte Carlo draws (default: 100)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()

    if args.scenario == "all":
        all_results = {}
        for key in SCENARIO_FILES:
            all_results[key] = run_one(key, args.n_draws)

        # Save comparative summary
        print(f"\n\n{'='*60}")
        print("COMPARATIVE SUMMARY")
        print(f"{'='*60}")
        for key, agg in all_results.items():
            tb = agg["total_built"]
            gc = agg["gini_coefficient"]
            fc = agg["firm_cost_m"]
            print(
                f"  {key:5s}: built={tb['mean']:6.0f} [{tb['p2_5']:.0f}-{tb['p97_5']:.0f}]  "
                f"gini={gc['mean']:.3f}  firm_cost=${fc['mean']:.0f}M"
            )

        with open(OUTPUT_DIR / "comparative_summary.json", "w") as f:
            json.dump(all_results, f, indent=2)
    else:
        run_one(args.scenario, args.n_draws)

    elapsed = time.time() - t0
    print(f"\nTotal elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
