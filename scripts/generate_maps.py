#!/usr/bin/env python3
"""Generate interactive county-level approval probability maps.

Produces two HTML maps:
  1. 108 labeled counties (training set) — color = actual outcome + predicted prob
  2. 232 FracTracker counties — color = predicted approval probability

Usage:
    PYTHONPATH=. python scripts/generate_maps.py
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import pandas as pd
import plotly.express as px

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROBS_PATH = PROJECT_ROOT / "data" / "processed" / "county_approval_probs.csv"
MATRIX_PATH = PROJECT_ROOT / "data" / "processed" / "county_feature_matrix.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "figures"

GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"

COLOR_SCALE = [
    [0.0, "#d73027"],
    [0.25, "#fc8d59"],
    [0.44, "#fee08b"],
    [0.6, "#d9ef8b"],
    [0.8, "#91cf60"],
    [1.0, "#1a9850"],
]


def load_data() -> tuple[pd.DataFrame, dict]:
    """Load feature matrix, probs, and GeoJSON."""
    matrix = pd.read_csv(MATRIX_PATH, dtype={"fips": str})
    probs = pd.read_csv(PROBS_PATH, dtype={"fips": str})

    df = matrix.merge(probs[["fips", "approval_prob"]], on="fips", how="left")

    print("Downloading county boundaries...")
    with urlopen(GEOJSON_URL) as response:
        geojson = json.load(response)

    return df, geojson


def build_hover(df: pd.DataFrame, show_outcome: bool = False) -> pd.Series:
    """Build hover text column."""
    text = (
        df["county"].fillna("") + ", " + df["state"].fillna("")
        + "<br>Approval prob: "
        + (df["approval_prob"] * 100).round(1).astype(str) + "%"
    )
    if show_outcome:
        text = text + "<br>Actual outcome: " + df["binary_outcome"].map(
            {1.0: "Approved", 0.0: "Blocked"}
        ).fillna("Unknown")
    text = (
        text
        + "<br>Facilities: " + df["facility_count"].fillna(0).astype(int).astype(str)
        + "<br>Saturation: " + df["saturation_count"].fillna(0).astype(int).astype(str)
        + "<br>Pushback: " + df["pushback_flag"].fillna(0).astype(int).map({0: "No", 1: "Yes"})
        + "<br>Water stress: "
        + df["water_stress_decile"].fillna(0).astype(int).astype(str) + "/10"
        + "<br>Pop density: "
        + df["population_density"].fillna(0).round(0).astype(int).astype(str) + "/sq mi"
        + "<br>Median income: $"
        + df["median_household_income"].fillna(0).astype(int).apply(lambda x: f"{x:,}")
    )
    return text


def make_map(
    df: pd.DataFrame,
    geojson: dict,
    title: str,
    output_path: Path,
) -> None:
    """Create and save a Plotly choropleth."""
    fig = px.choropleth(
        df,
        geojson=geojson,
        locations="fips",
        color="approval_prob",
        color_continuous_scale=COLOR_SCALE,
        range_color=[0.05, 0.95],
        scope="usa",
        hover_name="hover_text",
        labels={"approval_prob": "Approval Probability"},
        title=title,
    )

    fig.update_layout(
        geo=dict(lakecolor="rgb(255, 255, 255)", showlakes=True),
        coloraxis_colorbar=dict(
            title="P(Approve)",
            tickformat=".0%",
            tickvals=[0.1, 0.25, 0.44, 0.6, 0.8, 0.95],
            ticktext=["10%", "25%", "44%<br>(median)", "60%", "80%", "95%"],
        ),
        margin={"r": 0, "t": 80, "l": 0, "b": 0},
        width=1200,
        height=700,
    )

    fig.update_traces(
        hovertemplate="%{hovertext}<extra></extra>",
        marker_line_width=0.5,
        marker_line_color="white",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path), include_plotlyjs=True)
    print(f"  Saved: {output_path}")


def main() -> None:
    df, geojson = load_data()

    # --- Map 1: 108 labeled training counties ---
    labeled = df[df["binary_outcome"].notna()].copy()
    labeled["hover_text"] = build_hover(labeled, show_outcome=True)
    print(f"\n108 labeled counties ({(labeled.binary_outcome == 1).sum()} approved, "
          f"{(labeled.binary_outcome == 0).sum()} blocked)")

    make_map(
        labeled,
        geojson,
        title=(
            "Data Center Approval Probability — 108 Labeled Training Counties<br>"
            "<sup>Green=high approval, Red=low. Hover shows actual outcome (approved/blocked).</sup>"
        ),
        output_path=OUTPUT_DIR / "map_108_training.html",
    )

    # --- Map 2: All 232 FracTracker counties ---
    all232 = df.copy()
    all232["hover_text"] = build_hover(all232, show_outcome=True)
    print(f"\n232 FracTracker counties ({all232['binary_outcome'].notna().sum()} labeled, "
          f"{all232['binary_outcome'].isna().sum()} unlabeled)")

    make_map(
        all232,
        geojson,
        title=(
            "Data Center Approval Probability — 232 FracTracker Counties<br>"
            "<sup>108 labeled + 124 predicted. Hover shows outcome where known.</sup>"
        ),
        output_path=OUTPUT_DIR / "map_232_fractracker.html",
    )

    print("\nDone. Open in browser:")
    print(f"  file://{(OUTPUT_DIR / 'map_108_training.html').resolve()}")
    print(f"  file://{(OUTPUT_DIR / 'map_232_fractracker.html').resolve()}")


if __name__ == "__main__":
    main()
