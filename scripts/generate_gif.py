#!/usr/bin/env python
"""Generate animated map GIF for a scenario's simulation evolution.

Shows all 3,153 US counties colored by approval probability, with cyan
overlays on counties where facilities get built during the simulation.
Runs one deterministic "showcase" draw to produce the month-by-month map.

Usage:
    PYTHONPATH=. python scripts/generate_gif.py -s s1
    PYTHONPATH=. python scripts/generate_gif.py -s s4 --frame-months 3
    PYTHONPATH=. python scripts/generate_gif.py -s all
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.simulation.candidate import build_state_county_map, load_state_shares
from src.viz.map_animation import generate_scenario_gif

SCENARIOS_DIR = Path("configs/scenarios")
OUTPUT_DIR = Path("outputs/animation")

SCENARIO_FILES = {
    "s1": "s1_laissez_faire.yaml",
    "s2": "s2_majority_50.yaml",
    "s3": "s3_supermajority_75.yaml",
    "s4": "s4_firm_consent_50.yaml",
    "s5": "s5_firm_consent_75.yaml",
}

ALL_PROBS_PATH = Path("data/processed/all_county_approval_probs.csv")
FEATURE_MATRIX_PATH = Path("data/processed/county_feature_matrix.csv")


def main():
    parser = argparse.ArgumentParser(
        description="Generate animated map GIF for a scenario"
    )
    parser.add_argument(
        "--scenario", "-s",
        choices=list(SCENARIO_FILES.keys()) + ["all"],
        required=True,
        help="Which scenario (s1-s5 or 'all')",
    )
    parser.add_argument(
        "--frame-months",
        type=int,
        default=6,
        help="Render a frame every N months (default: 6 → 21 frames)",
    )
    parser.add_argument(
        "--gif-duration",
        type=int,
        default=300,
        help="Duration per frame in ms (default: 300)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load shared data (once)
    print("Loading data...")
    all_probs_df = pd.read_csv(ALL_PROBS_PATH, dtype={"fips": str})
    # Use all-county probs for simulation too (3,153 counties)
    sim_probs = dict(zip(all_probs_df["fips"], all_probs_df["approval_prob"]))
    feature_matrix = pd.read_csv(FEATURE_MATRIX_PATH, dtype={"fips": str})
    state_shares_df = load_state_shares()

    # Build state→county map from all 3,153 counties
    state_county_map = build_state_county_map(
        all_probs_df[["fips"]],
        feature_matrix,
    )

    initial_saturation: dict[str, int] = {}
    if "saturation_count" in feature_matrix.columns:
        initial_saturation = dict(
            zip(
                feature_matrix["fips"],
                feature_matrix["saturation_count"].fillna(0).astype(int),
            )
        )

    # County weights: existing facility counties get higher proposal weight
    existing_fips = set(feature_matrix["fips"].dropna())
    county_weights = {
        fips: (3.0 if fips in existing_fips else 1.0)
        for fips in sim_probs
    }

    scenarios = (
        list(SCENARIO_FILES.keys()) if args.scenario == "all"
        else [args.scenario]
    )

    t0 = time.time()
    for key in scenarios:
        print(f"\n--- {key} ---")
        cfg = load_config(SCENARIOS_DIR / SCENARIO_FILES[key])
        generate_scenario_gif(
            scenario_key=key,
            cfg=cfg,
            sim_approval_probs=sim_probs,
            all_approval_probs_df=all_probs_df,
            state_shares_df=state_shares_df,
            state_county_map=state_county_map,
            initial_saturation=initial_saturation,
            output_dir=OUTPUT_DIR,
            frame_every_n_months=args.frame_months,
            gif_duration_ms=args.gif_duration,
            county_weights=county_weights,
        )

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s ({elapsed / 60:.1f} min)")


if __name__ == "__main__":
    main()
