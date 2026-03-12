#!/usr/bin/env python3
"""Build approval probabilities for ALL US counties (not just FracTracker ones).

For counties not in FracTracker, sets facility features to 0 (greenfield) and
uses external features (water stress, partisan lean, state incentives, QWI).
Then trains XGBoost on labeled counties and predicts for all 3,144.

Output: data/processed/all_county_approval_probs.csv
        outputs/figures/full_approval_map.html
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
import plotly.express as px

from src.config import XGBoostConfig, load_config
from src.model.xgboost_model import FEATURE_COLS, XGBoostApprovalModel

# Use None to load config from base.yaml (full training config)
FAST_XGB_CONFIG = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"
MATRIX_PATH = PROJECT_ROOT / "data" / "processed" / "county_feature_matrix.csv"

GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"


def build_all_county_features() -> pd.DataFrame:
    """Build feature matrix for all US counties."""
    # Load existing FracTracker feature matrix
    ft = pd.read_csv(MATRIX_PATH, dtype={"fips": str})

    # Load external datasets (cover ~3000+ counties)
    ws = pd.read_csv(EXTERNAL_DIR / "water_stress.csv", dtype={"fips": str})
    pl = pd.read_csv(EXTERNAL_DIR / "partisan_lean.csv", dtype={"fips": str})
    qwi = pd.read_csv(EXTERNAL_DIR / "qwi_employment.csv", dtype={"fips": str})
    si = pd.read_csv(EXTERNAL_DIR / "state_incentives.csv")

    # Build a master FIPS list from water stress + partisan lean (broadest coverage)
    all_fips = set(ws["fips"].dropna()) | set(pl["fips"].dropna())
    # Add FracTracker counties
    all_fips |= set(ft["fips"].dropna())
    all_fips = sorted(all_fips)

    print(f"Total unique counties: {len(all_fips)}")

    # Start with all counties
    df = pd.DataFrame({"fips": all_fips})

    # Derive state abbreviation from FIPS (first 2 digits)
    state_fips_to_abbr = _build_state_fips_map()
    df["state_fips"] = df["fips"].str[:2]
    df["state"] = df["state_fips"].map(state_fips_to_abbr)

    # Merge FracTracker facility features (most counties will be NaN → 0)
    ft_cols = ["fips", "county", "facility_count", "total_mw", "avg_project_mw",
               "hyperscaler_share", "saturation_count", "pushback_flag",
               "binary_outcome"]
    df = df.merge(ft[ft_cols], on="fips", how="left")

    # Fill greenfield defaults for non-FracTracker counties
    df["facility_count"] = df["facility_count"].fillna(0).astype(int)
    df["total_mw"] = df["total_mw"].fillna(0.0)
    df["avg_project_mw"] = df["avg_project_mw"].fillna(300.0)  # Median project size
    df["hyperscaler_share"] = df["hyperscaler_share"].fillna(0.0)
    df["saturation_count"] = df["saturation_count"].fillna(0).astype(int)
    df["pushback_flag"] = df["pushback_flag"].fillna(0).astype(int)

    # Merge external features
    df = df.merge(ws[["fips", "water_stress_decile"]], on="fips", how="left")
    df["water_stress_decile"] = df["water_stress_decile"].fillna(5)  # Median

    df = df.merge(pl[["fips", "partisan_lean_r"]], on="fips", how="left")
    df["partisan_lean_r"] = df["partisan_lean_r"].fillna(0.5)  # Neutral

    # QWI employment (dc_employment + dc_employment_growth)
    qwi_cols = [c for c in ["fips", "dc_employment", "dc_employment_growth"] if c in qwi.columns]
    if "fips" in qwi_cols:
        qwi_sub = qwi[qwi_cols].drop_duplicates(subset=["fips"])
        df = df.merge(qwi_sub, on="fips", how="left")
    if "dc_employment" not in df.columns:
        df["dc_employment"] = 0
    df["dc_employment"] = df["dc_employment"].fillna(0).astype(int)
    if "dc_employment_growth" not in df.columns:
        df["dc_employment_growth"] = 0.0
    df["dc_employment_growth"] = df["dc_employment_growth"].fillna(0.0)

    # Census ACS demographics
    acs_path = EXTERNAL_DIR / "census_acs.csv"
    if acs_path.exists():
        acs = pd.read_csv(acs_path, dtype={"fips": str})
        acs_cols = ["fips", "population", "population_density",
                    "median_household_income", "unemployment_rate",
                    "pct_college_educated", "ag_employment_share"]
        acs_cols = [c for c in acs_cols if c in acs.columns]
        df = df.merge(acs[acs_cols], on="fips", how="left")
    for col, default in [("population", 30000), ("population_density", 100.0),
                         ("median_household_income", 55000),
                         ("unemployment_rate", 5.0),
                         ("pct_college_educated", 0.20),
                         ("ag_employment_share", 0.05)]:
        if col not in df.columns:
            df[col] = default
        df[col] = df[col].fillna(default)

    # EIA electricity prices (state-level)
    elec_path = EXTERNAL_DIR / "electricity_price.csv"
    if elec_path.exists():
        elec = pd.read_csv(elec_path)
        elec_map = dict(zip(elec["state"], elec["electricity_price_cents_kwh"]))
        df["electricity_price"] = df["state"].map(elec_map).fillna(12.0)
    else:
        df["electricity_price"] = 12.0

    # State incentive scores
    if "state" in df.columns:
        score_map = dict(zip(si["state"], si["incentive_score"]))
        df["state_incentive_score"] = df["state"].map(score_map).fillna(0.5)
    else:
        df["state_incentive_score"] = 0.5

    # Engineered features (must match src/data/features.py)
    df["log_population"] = np.log1p(df["population"].fillna(0))
    df["log_income"] = np.log1p(df["median_household_income"].fillna(0))
    df["log_dc_employment"] = np.log1p(df["dc_employment"].fillna(0))
    df["water_stress_x_density"] = (
        df["water_stress_decile"].fillna(5) * df["population_density"].fillna(0) / 1000.0
    )

    df = df.drop(columns=["state_fips"], errors="ignore")
    print(f"Features built: {len(df)} counties, {df['binary_outcome'].notna().sum()} labeled")
    return df


def _build_state_fips_map() -> dict[str, str]:
    """Map 2-digit state FIPS → abbreviation."""
    return {
        "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
        "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
        "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
        "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
        "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
        "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
        "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
        "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
        "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
        "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
        "56": "WY",
    }


def main() -> None:
    # Build features for all counties
    df = build_all_county_features()

    # Train XGBoost on labeled counties, predict for all (full config from base.yaml)
    cfg = load_config()
    model = XGBoostApprovalModel(
        xgb_config=FAST_XGB_CONFIG or cfg.model.xgboost,
        calibration_config=cfg.calibration,
    )
    metrics = model.train(df)
    print(f"\nCV AUC: {metrics['cv_auc_mean']:.3f} ± {metrics['cv_auc_std']:.3f}")

    # Feature importances
    imp = model.feature_importances()
    print("\nFeature importances:")
    for k, v in sorted(imp.items(), key=lambda x: -x[1]):
        print(f"  {k:25s}: {v:.4f}")

    # Calibrate
    cal_meta = model.calibrate()
    print(f"\nCalibrated: {cal_meta['n_counties']} counties, "
          f"range [{cal_meta['p_min']:.3f}, {cal_meta['p_max']:.3f}], "
          f"mean={cal_meta['p_mean']:.3f}")

    # Save probabilities
    out_path = PROJECT_ROOT / "data" / "processed" / "all_county_approval_probs.csv"
    model.save_probabilities(out_path)
    print(f"Saved to {out_path}")

    # Build interactive map
    print("\nBuilding interactive map...")
    probs = pd.read_csv(out_path, dtype={"fips": str})
    # Merge county/state names
    probs = probs.merge(df[["fips", "county", "state", "facility_count",
                            "saturation_count", "pushback_flag",
                            "water_stress_decile", "partisan_lean_r"]],
                        on="fips", how="left")

    # Get county name from FIPS where missing
    probs["label"] = probs.apply(
        lambda r: f"{r['county']}, {r['state']}" if pd.notna(r.get("county")) else f"FIPS {r['fips']}",
        axis=1,
    )

    probs["hover_text"] = (
        probs["label"]
        + "<br>Approval: " + (probs["approval_prob"] * 100).round(1).astype(str) + "%"
        + "<br>Facilities: " + probs["facility_count"].fillna(0).astype(int).astype(str)
        + "<br>Saturation: " + probs["saturation_count"].fillna(0).astype(int).astype(str)
        + "<br>Pushback: " + probs["pushback_flag"].fillna(0).astype(int).map({0: "No", 1: "Yes"})
        + "<br>Water stress: " + probs["water_stress_decile"].fillna(5).astype(int).astype(str) + "/10"
        + "<br>Partisan lean (R): " + (probs["partisan_lean_r"].fillna(0.5) * 100).round(1).astype(str) + "%"
    )

    print("Downloading county GeoJSON...")
    with urlopen(GEOJSON_URL) as response:
        counties_geojson = json.load(response)

    fig = px.choropleth(
        probs,
        geojson=counties_geojson,
        locations="fips",
        color="approval_prob",
        color_continuous_scale=[
            [0.0, "#d73027"],
            [0.25, "#fc8d59"],
            [0.44, "#fee08b"],
            [0.6, "#d9ef8b"],
            [0.8, "#91cf60"],
            [1.0, "#1a9850"],
        ],
        range_color=[0.05, 0.95],
        scope="usa",
        hover_name="hover_text",
        labels={"approval_prob": "Approval Probability"},
        title=(
            "Data Center Approval Probability — All U.S. Counties<br>"
            "<sup>XGBoost model trained on 108 labeled counties, "
            "predicted for 3,144. National median=44% (Heatmap/Embold 2025)</sup>"
        ),
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
        marker_line_width=0.3,
        marker_line_color="rgba(100,100,100,0.3)",
    )

    map_path = PROJECT_ROOT / "outputs" / "figures" / "full_approval_map.html"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(map_path), include_plotlyjs=True)
    print(f"\nMap saved to {map_path}")
    print(f"Open: file://{map_path.resolve()}")


if __name__ == "__main__":
    main()
