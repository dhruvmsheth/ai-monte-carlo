#!/usr/bin/env python
"""Generate animated map GIF from saved Monte Carlo simulation data.

Reads per-draw monthly county builds from outputs/simulation/<scenario>/
and renders an animated GIF showing mean facility growth over time.
No simulation is run — all data comes from a prior run_simulation.py run.

Usage:
    PYTHONPATH=. python scripts/generate_gif.py -s s1
    PYTHONPATH=. python scripts/generate_gif.py -s all --frame-months 3
    PYTHONPATH=. python scripts/generate_gif.py -s s4 --cluster-distance 1.0
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.viz.map_animation import (
    MONTH_NAMES,
    SCENARIO_LABELS,
    BG_COLOR,
    cluster_builds,
    extract_centroids,
    load_geojson,
    render_frame,
)

SCENARIOS_DIR = Path("configs/scenarios")
SIM_OUTPUT_DIR = Path("outputs/simulation")
GIF_OUTPUT_DIR = Path("outputs/animation")

SCENARIO_KEYS = ["s1", "s2", "s3", "s4", "s5"]

ALL_PROBS_PATH = Path("data/processed/all_county_approval_probs.csv")


def load_mean_snapshots(
    scenario_key: str,
    start_year: int = 2026,
    start_month: int = 1,
) -> list[dict]:
    """Load county_builds_by_month.csv and compute mean builds per month.

    Returns list of 120 monthly snapshots with:
        month, year, calendar_month, county_builds (mean), total_built, cumulative_gw
    """
    builds_path = SIM_OUTPUT_DIR / scenario_key / "county_builds_by_month.csv"
    if not builds_path.exists():
        raise FileNotFoundError(
            f"No simulation data for {scenario_key}. "
            f"Run: PYTHONPATH=. python scripts/run_simulation.py -s {scenario_key}"
        )

    df = pd.read_csv(builds_path, dtype={"fips": str})
    n_draws = df["draw_id"].nunique()
    n_months = df["month"].max()

    print(f"  Loaded {len(df)} rows from {n_draws} draws, {n_months} months")

    # Also load draw summaries for cumulative GW
    summaries_path = SIM_OUTPUT_DIR / scenario_key / "draw_summaries.csv"
    avg_gw_per_facility = 0.3  # Default: 300 MW
    if summaries_path.exists():
        summaries = pd.read_csv(summaries_path)
        mean_gw = summaries["cumulative_gw"].mean()
        mean_built = summaries["total_built"].mean()
        if mean_built > 0:
            avg_gw_per_facility = mean_gw / mean_built

    snapshots = []
    for month in range(1, n_months + 1):
        cal_month = ((start_month - 1 + month - 1) % 12) + 1
        cal_year = start_year + (start_month - 1 + month - 1) // 12

        month_data = df[df["month"] == month]
        # Mean builds per county across draws
        mean_builds: dict[str, float] = {}
        if not month_data.empty:
            agg = month_data.groupby("fips")["builds"].sum() / n_draws
            mean_builds = agg.to_dict()

        total_built = sum(mean_builds.values())
        cumulative_gw = total_built * avg_gw_per_facility

        snapshots.append({
            "month": month,
            "year": cal_year,
            "calendar_month": cal_month,
            "county_builds": mean_builds,
            "total_built": total_built,
            "cumulative_gw": cumulative_gw,
            "n_draws": n_draws,
        })

    return snapshots


def generate_gif(
    scenario_key: str,
    snapshots: list[dict],
    centroids: dict[str, tuple[float, float]],
    all_probs: dict[str, float],
    frame_every_n_months: int = 6,
    gif_duration_ms: int = 300,
    cluster_distance: float = 0.8,
) -> Path:
    """Render and assemble GIF from pre-computed snapshots."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    import shutil

    GIF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frames_dir = GIF_OUTPUT_DIR / f"_{scenario_key}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    scenario_label = SCENARIO_LABELS.get(scenario_key, scenario_key)
    n_draws = snapshots[-1].get("n_draws", "?")

    # Max builds for consistent scale
    final_builds = snapshots[-1]["county_builds"]
    max_builds = max(final_builds.values()) if final_builds else 1
    max_builds = max(max_builds, 3)

    # Select frame indices
    indices = list(range(0, len(snapshots), frame_every_n_months))
    if (len(snapshots) - 1) not in indices:
        indices.append(len(snapshots) - 1)

    fig, ax = plt.subplots(figsize=(14, 8), facecolor=BG_COLOR)

    print(f"  Rendering {len(indices)} frames...")
    frame_paths = []
    for i, idx in enumerate(indices):
        snap = snapshots[idx]
        month_name = MONTH_NAMES[snap["calendar_month"] - 1]
        time_label = f"{month_name} {snap['year']}"
        stats_label = (
            f"{snap['total_built']:.0f} facilities  \u00b7  {snap['cumulative_gw']:.1f} GW"
            f"  (mean of {n_draws} draws)"
        )

        clusters = cluster_builds(snap["county_builds"], centroids, cluster_distance)

        render_frame(
            ax=ax,
            centroids=centroids,
            all_probs=all_probs,
            clusters=clusters,
            scenario_label=scenario_label,
            time_label=time_label,
            stats_label=stats_label,
            max_builds=max_builds,
        )

        fp = frames_dir / f"frame_{idx:04d}.png"
        fig.savefig(str(fp), dpi=150, facecolor=BG_COLOR, bbox_inches="tight", pad_inches=0.3)
        frame_paths.append(fp)

        if (i + 1) % 5 == 0 or i == len(indices) - 1:
            print(f"    Frame {i + 1}/{len(indices)} done")

    plt.close(fig)

    # Assemble GIF
    gif_path = GIF_OUTPUT_DIR / f"{scenario_key}_evolution.gif"
    frames = [Image.open(fp).convert("RGB") for fp in frame_paths]

    durations = [gif_duration_ms] * len(frames)
    if len(durations) > 1:
        durations[-1] = gif_duration_ms * 5

    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )

    shutil.rmtree(frames_dir)

    size_kb = gif_path.stat().st_size / 1024
    print(f"  Saved: {gif_path} ({len(frames)} frames, {size_kb:.0f} KB)")
    return gif_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate animated map GIF from saved simulation data"
    )
    parser.add_argument(
        "--scenario", "-s",
        choices=SCENARIO_KEYS + ["all"],
        required=True,
        help="Which scenario (s1-s5 or 'all')",
    )
    parser.add_argument(
        "--frame-months",
        type=int,
        default=6,
        help="Render a frame every N months (default: 6 -> 21 frames)",
    )
    parser.add_argument(
        "--gif-duration",
        type=int,
        default=300,
        help="Duration per frame in ms (default: 300)",
    )
    parser.add_argument(
        "--cluster-distance",
        type=float,
        default=0.8,
        help="Clustering distance in degrees (default: 0.8 ~ 50mi)",
    )
    args = parser.parse_args()

    # Load shared data
    print("Loading map data...")
    geojson = load_geojson()
    centroids = extract_centroids(geojson)
    probs_df = pd.read_csv(ALL_PROBS_PATH, dtype={"fips": str})
    all_probs = dict(zip(probs_df["fips"], probs_df["approval_prob"]))

    scenarios = SCENARIO_KEYS if args.scenario == "all" else [args.scenario]

    t0 = time.time()
    for key in scenarios:
        print(f"\n--- {key} ---")
        snapshots = load_mean_snapshots(key)
        generate_gif(
            scenario_key=key,
            snapshots=snapshots,
            centroids=centroids,
            all_probs=all_probs,
            frame_every_n_months=args.frame_months,
            gif_duration_ms=args.gif_duration,
            cluster_distance=args.cluster_distance,
        )

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s ({elapsed / 60:.1f} min)")


if __name__ == "__main__":
    main()
