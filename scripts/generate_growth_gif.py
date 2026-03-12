#!/usr/bin/env python
"""Generate animated GIF comparing GW growth across all 5 scenarios.

Reads monthly_time_series.csv from outputs/simulation/<scenario>/.
No simulation is run.

Usage:
    PYTHONPATH=. python scripts/generate_growth_gif.py
"""

from __future__ import annotations

from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

BG = "#0d1117"
OUTPUT = Path("outputs/animation/gw_growth_comparison.gif")
SIM_DIR = Path("outputs/simulation")

SCENARIOS = {
    "s1": ("Laissez-faire", "#00e5ff"),
    "s2": ("Majority 50%", "#66bb6a"),
    "s3": ("Supermajority 75%", "#ffa726"),
    "s4": ("Firm-borne 50%", "#ab47bc"),
    "s5": ("Firm-borne 75%", "#ef5350"),
}


def main() -> None:
    # Load time series for each scenario
    data: dict[str, pd.DataFrame] = {}
    for key in SCENARIOS:
        path = SIM_DIR / key / "monthly_time_series.csv"
        if not path.exists():
            print(f"Missing {path} — run simulation first")
            return
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(
            df["year"].astype(str) + "-" + df["calendar_month"].astype(str) + "-1"
        )
        data[key] = df

    n_months = len(data["s1"])
    y_max = max(df["p97_5_cumulative_gw"].max() for df in data.values()) * 1.05

    # Render frames (every 2 months for smooth animation)
    frames_dir = Path("outputs/animation/_gw_frames")
    frames_dir.mkdir(parents=True, exist_ok=True)

    frame_indices = list(range(0, n_months, 2))
    if (n_months - 1) not in frame_indices:
        frame_indices.append(n_months - 1)

    fig, ax = plt.subplots(figsize=(12, 6), facecolor=BG)
    frame_paths = []

    for fi, idx in enumerate(frame_indices):
        ax.clear()
        ax.set_facecolor(BG)

        for key, (label, color) in SCENARIOS.items():
            df = data[key]
            sub = df.iloc[:idx + 1]
            ax.plot(sub["date"], sub["mean_cumulative_gw"], color=color, linewidth=2, label=label)
            ax.fill_between(
                sub["date"],
                sub["p2_5_cumulative_gw"],
                sub["p97_5_cumulative_gw"],
                color=color, alpha=0.15,
            )

        ax.set_xlim(data["s1"]["date"].iloc[0], data["s1"]["date"].iloc[-1])
        ax.set_ylim(0, y_max)
        ax.set_ylabel("Cumulative GW", color="white", fontsize=12)
        ax.tick_params(colors="white", labelsize=9)
        ax.spines["bottom"].set_color("#444")
        ax.spines["left"].set_color("#444")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", color="#222", linewidth=0.5)

        date_str = data["s1"]["date"].iloc[idx].strftime("%b %Y")
        ax.set_title(
            f"Data Center Capacity Growth by Consent Regime\n{date_str}",
            color="white", fontsize=14, fontweight="bold", pad=10,
        )
        ax.legend(
            loc="upper left", fontsize=9, framealpha=0.3,
            facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
        )

        fp = frames_dir / f"frame_{fi:04d}.png"
        fig.savefig(str(fp), dpi=150, facecolor=BG, bbox_inches="tight", pad_inches=0.3)
        frame_paths.append(fp)

    plt.close(fig)

    # Assemble GIF
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [Image.open(fp).convert("RGB") for fp in frame_paths]
    durations = [100] * len(frames)
    durations[-1] = 2000

    frames[0].save(
        OUTPUT, save_all=True, append_images=frames[1:],
        duration=durations, loop=0,
    )

    shutil.rmtree(frames_dir)
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Saved: {OUTPUT} ({len(frames)} frames, {size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
