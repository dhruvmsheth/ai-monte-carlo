#!/usr/bin/env python3
"""Generate an interactive county-level approval probability map.

Produces an HTML file with a Plotly choropleth showing calibrated approval
probabilities for all 232 counties in the dataset. Hover shows county details.

Usage:
    python scripts/interactive_map.py [--output outputs/figures/approval_map.html]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import urlopen

import pandas as pd
import plotly.express as px

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROBS_PATH = PROJECT_ROOT / "data" / "processed" / "county_approval_probs.csv"
MATRIX_PATH = PROJECT_ROOT / "data" / "processed" / "county_feature_matrix.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "figures" / "approval_map.html"

# US Census county GeoJSON (simplified)
GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate approval probability map")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    # Load data
    probs = pd.read_csv(PROBS_PATH, dtype={"fips": str})
    matrix = pd.read_csv(MATRIX_PATH, dtype={"fips": str})

    # Merge for hover info
    df = probs.merge(
        matrix[["fips", "county", "state", "facility_count", "saturation_count",
                "pushback_flag", "water_stress_decile", "partisan_lean_r"]],
        on="fips",
        how="left",
    )

    # Format hover text
    df["hover_text"] = (
        df["county"] + ", " + df["state"]
        + "<br>Approval prob: " + (df["approval_prob"] * 100).round(1).astype(str) + "%"
        + "<br>Facilities: " + df["facility_count"].astype(str)
        + "<br>Saturation: " + df["saturation_count"].astype(str)
        + "<br>Pushback: " + df["pushback_flag"].map({0: "No", 1: "Yes"}).fillna("Unknown")
        + "<br>Water stress: " + df["water_stress_decile"].astype(str) + "/10"
        + "<br>Partisan lean (R): " + (df["partisan_lean_r"] * 100).round(1).astype(str) + "%"
    )

    # Download county GeoJSON
    print("Downloading county boundaries...")
    with urlopen(GEOJSON_URL) as response:
        counties_geojson = json.load(response)

    # Create choropleth
    fig = px.choropleth(
        df,
        geojson=counties_geojson,
        locations="fips",
        color="approval_prob",
        color_continuous_scale=[
            [0.0, "#d73027"],    # Red — low approval
            [0.25, "#fc8d59"],   # Orange
            [0.44, "#fee08b"],   # Yellow — national median
            [0.6, "#d9ef8b"],    # Light green
            [0.8, "#91cf60"],    # Green
            [1.0, "#1a9850"],    # Dark green — high approval
        ],
        range_color=[0.05, 0.95],
        scope="usa",
        hover_name="hover_text",
        labels={"approval_prob": "Approval Probability"},
        title="Data Center Approval Probability by County<br>"
              "<sup>XGBoost model (CV AUC=0.70) calibrated to Heatmap/Embold 2025 survey (national median=44%)</sup>",
    )

    fig.update_layout(
        geo=dict(
            lakecolor="rgb(255, 255, 255)",
            showlakes=True,
        ),
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

    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(args.output), include_plotlyjs=True)
    print(f"Map saved to {args.output}")
    print(f"Open in browser: file://{args.output.resolve()}")


if __name__ == "__main__":
    main()
