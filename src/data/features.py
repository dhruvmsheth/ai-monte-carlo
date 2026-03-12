"""External data enrichment: water stress, partisan lean, state incentives, opposition.

Loads real external datasets (USGS water stress, MIT Election Lab partisan lean,
Good Jobs First state incentives, Bryce/DataCenterWatch opposition) and merges
them into the county feature matrix. Census QWI employment is a placeholder
until API access is configured.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_EXTERNAL_DIR = _PROJECT_ROOT / "data" / "external"


# ---------------------------------------------------------------------------
# External data loaders
# ---------------------------------------------------------------------------


def load_state_incentives(path: str | Path | None = None) -> pd.DataFrame:
    """Load state-level incentive scores from Good Jobs First research.

    Expected CSV columns: state, incentive_score, has_dc_tax_exemption,
    transparency_score, source_notes.
    Returns DataFrame or empty DataFrame if file missing.
    """
    if path is None:
        path = _EXTERNAL_DIR / "state_incentives.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["state", "incentive_score"])
    return pd.read_csv(path)


def load_water_stress(path: str | Path | None = None) -> pd.DataFrame:
    """Load county-level water stress data (USGS 2015 per-capita withdrawal).

    Expected CSV columns: fips, water_stress_decile (1–10).
    """
    if path is None:
        path = _EXTERNAL_DIR / "water_stress.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["fips", "water_stress_decile"])
    return pd.read_csv(path, dtype={"fips": str})


def load_partisan_lean(path: str | Path | None = None) -> pd.DataFrame:
    """Load county-level partisan lean (2024 presidential % Republican).

    Source: tonmcg/US_County_Level_Election_Results_08-24 (MIT Election Lab).
    Expected CSV columns: fips, partisan_lean_r (float 0–1).
    """
    if path is None:
        path = _EXTERNAL_DIR / "partisan_lean.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["fips", "partisan_lean_r"])
    return pd.read_csv(path, dtype={"fips": str})


def load_opposition_data(path: str | Path | None = None) -> pd.DataFrame:
    """Load supplementary opposition data (Bryce + Data Center Watch + news).

    Expected CSV columns: fips, county, state, opposition_type, source.
    """
    if path is None:
        path = _EXTERNAL_DIR / "opposition.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["fips", "county", "state", "opposition_type", "source"])
    return pd.read_csv(path, dtype={"fips": str})


def load_qwi_employment(path: str | Path | None = None) -> pd.DataFrame:
    """Load county-level DC employment from Census QWI (NAICS 5182).

    Source: Census Bureau Quarterly Workforce Indicators API.
    Expected CSV columns: fips, dc_employment, dc_employment_growth.
    """
    if path is None:
        path = _EXTERNAL_DIR / "qwi_employment.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["fips", "dc_employment", "dc_employment_growth"])
    return pd.read_csv(path, dtype={"fips": str})


def load_census_acs(path: str | Path | None = None) -> pd.DataFrame:
    """Load county-level Census ACS demographic features.

    Source: Census ACS 5-Year 2022 + Gazetteer (land area).
    Columns: fips, population, population_density, median_household_income,
    unemployment_rate, pct_college_educated, ag_employment_share.
    """
    if path is None:
        path = _EXTERNAL_DIR / "census_acs.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "fips",
                "population",
                "population_density",
                "median_household_income",
                "unemployment_rate",
                "pct_college_educated",
                "ag_employment_share",
            ]
        )
    return pd.read_csv(path, dtype={"fips": str})


def load_electricity_price(path: str | Path | None = None) -> pd.DataFrame:
    """Load state-level average retail electricity prices.

    Source: EIA Electric Power Monthly 2023.
    Columns: state, state_fips, electricity_price_cents_kwh.
    """
    if path is None:
        path = _EXTERNAL_DIR / "electricity_price.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["state", "state_fips", "electricity_price_cents_kwh"])
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Feature enrichment
# ---------------------------------------------------------------------------


def enrich_county_features(
    county_df: pd.DataFrame,
    state_incentives_path: str | Path | None = None,
) -> pd.DataFrame:
    """Add external features to the county aggregation from ingest.py.

    Loads state incentive scores from CSV (Good Jobs First research).
    Initializes placeholder columns for features loaded separately.
    """
    df = county_df.copy()

    # State incentive generosity — from researched CSV
    si = load_state_incentives(state_incentives_path)
    if len(si) > 0:
        score_map = dict(zip(si["state"], si["incentive_score"]))
        df["state_incentive_score"] = df["state"].map(score_map).fillna(0.50)
    else:
        df["state_incentive_score"] = 0.50

    # Placeholders for features loaded via merge_external_features
    if "water_stress_decile" not in df.columns:
        df["water_stress_decile"] = np.nan
    if "partisan_lean_r" not in df.columns:
        df["partisan_lean_r"] = np.nan
    if "dc_employment" not in df.columns:
        df["dc_employment"] = 0
    if "dc_employment_growth" not in df.columns:
        df["dc_employment_growth"] = 0.0

    return df


# ---------------------------------------------------------------------------
# Merge external features
# ---------------------------------------------------------------------------


def merge_external_features(
    county_df: pd.DataFrame,
    water_stress: pd.DataFrame | None = None,
    partisan_lean: pd.DataFrame | None = None,
    opposition: pd.DataFrame | None = None,
    qwi_employment: pd.DataFrame | None = None,
    census_acs: pd.DataFrame | None = None,
    electricity_price: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge all external feature sources into the county DataFrame.

    Any feature source that is None or empty is skipped (existing values preserved).
    """
    df = county_df.copy()

    # Water stress
    if water_stress is not None and len(water_stress) > 0:
        ws = water_stress[["fips", "water_stress_decile"]].drop_duplicates(subset=["fips"])
        df = df.merge(ws, on="fips", how="left", suffixes=("_old", ""))
        if "water_stress_decile_old" in df.columns:
            df["water_stress_decile"] = df["water_stress_decile"].fillna(
                df["water_stress_decile_old"]
            )
            df = df.drop(columns=["water_stress_decile_old"])

    # Partisan lean
    if partisan_lean is not None and len(partisan_lean) > 0:
        pl = partisan_lean[["fips", "partisan_lean_r"]].drop_duplicates(subset=["fips"])
        df = df.merge(pl, on="fips", how="left", suffixes=("_old", ""))
        if "partisan_lean_r_old" in df.columns:
            df["partisan_lean_r"] = df["partisan_lean_r"].fillna(df["partisan_lean_r_old"])
            df = df.drop(columns=["partisan_lean_r_old"])

    # Opposition (additive merge with existing pushback_flag)
    if opposition is not None and len(opposition) > 0:
        opp_fips = set(opposition["fips"].dropna().unique())
        df["pushback_flag"] = df.apply(
            lambda row: 1 if row.get("pushback_flag", 0) == 1 or row["fips"] in opp_fips else 0,
            axis=1,
        )

    # QWI employment
    if qwi_employment is not None and len(qwi_employment) > 0:
        qwi_cols = ["fips", "dc_employment"]
        if "dc_employment_growth" in qwi_employment.columns:
            qwi_cols.append("dc_employment_growth")
        qwi = qwi_employment[qwi_cols].drop_duplicates(subset=["fips"])
        qwi = qwi.rename(
            columns={
                "dc_employment": "dc_employment_new",
                "dc_employment_growth": "dc_employment_growth_new",
            }
        )
        df = df.merge(qwi, on="fips", how="left")
        df["dc_employment"] = df["dc_employment_new"].fillna(df["dc_employment"]).fillna(0)
        df["dc_employment"] = df["dc_employment"].astype(int)
        df = df.drop(columns=["dc_employment_new"])
        if "dc_employment_growth_new" in df.columns:
            df["dc_employment_growth"] = (
                df["dc_employment_growth_new"]
                .fillna(df.get("dc_employment_growth", 0.0))
                .fillna(0.0)
            )
            df = df.drop(columns=["dc_employment_growth_new"])

    # Census ACS demographic features
    if census_acs is not None and len(census_acs) > 0:
        acs_cols = [
            "fips",
            "population",
            "population_density",
            "median_household_income",
            "unemployment_rate",
            "pct_college_educated",
            "ag_employment_share",
        ]
        acs = census_acs[[c for c in acs_cols if c in census_acs.columns]].drop_duplicates(
            subset=["fips"]
        )
        df = df.merge(acs, on="fips", how="left")
        df["population"] = df["population"].fillna(0).astype(int)
        df["population_density"] = df["population_density"].fillna(0.0)
        df["median_household_income"] = df["median_household_income"].fillna(0).astype(int)
        df["unemployment_rate"] = df["unemployment_rate"].fillna(0.05)
        df["pct_college_educated"] = df["pct_college_educated"].fillna(0.23)
        df["ag_employment_share"] = df["ag_employment_share"].fillna(0.06)

    # State-level electricity price
    if electricity_price is not None and len(electricity_price) > 0:
        price_map = dict(
            zip(electricity_price["state"], electricity_price["electricity_price_cents_kwh"])
        )
        df["electricity_price"] = df["state"].map(price_map).fillna(15.3)

    return df


# ---------------------------------------------------------------------------
# Build complete feature matrix
# ---------------------------------------------------------------------------


def build_feature_matrix(
    county_df: pd.DataFrame,
    water_stress_path: str | Path | None = None,
    partisan_lean_path: str | Path | None = None,
    opposition_path: str | Path | None = None,
    qwi_employment_path: str | Path | None = None,
    state_incentives_path: str | Path | None = None,
    census_acs_path: str | Path | None = None,
    electricity_price_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Build the complete county feature matrix.

    Orchestrates: enrich (state incentives) → load externals → merge → save.
    """
    df = enrich_county_features(county_df, state_incentives_path)

    water_stress = load_water_stress(water_stress_path)
    partisan_lean = load_partisan_lean(partisan_lean_path)
    opposition = load_opposition_data(opposition_path)
    qwi_employment = load_qwi_employment(qwi_employment_path)
    census_acs = load_census_acs(census_acs_path)
    electricity_price = load_electricity_price(electricity_price_path)

    df = merge_external_features(
        df,
        water_stress,
        partisan_lean,
        opposition,
        qwi_employment,
        census_acs,
        electricity_price,
    )

    # Engineered features: log transforms for skewed distributions + interaction
    df["log_population"] = np.log1p(df["population"].fillna(0))
    df["log_income"] = np.log1p(df["median_household_income"].fillna(0))
    df["log_dc_employment"] = np.log1p(df["dc_employment"].fillna(0))
    df["water_stress_x_density"] = (
        df["water_stress_decile"].fillna(5) * df["population_density"].fillna(0) / 1000.0
    )

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)

    return df
