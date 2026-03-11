"""External data enrichment: water stress, partisan lean, state incentives.

Phase 1 uses placeholder/manual data for features that require external APIs.
Each function follows the same pattern: takes county FIPS codes, returns a Series
indexed by FIPS with the feature values.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_EXTERNAL_DIR = _PROJECT_ROOT / "data" / "external"


# ---------------------------------------------------------------------------
# State incentive generosity (manual, from Good Jobs First + desk research)
# ---------------------------------------------------------------------------

# State-level data center incentive scores (0–1 scale).
# 1.0 = most generous incentive regime. Based on:
#   - Good Jobs First "Cloudy Data, Costly Deals" (2025)
#   - Presence of explicit DC tax exemptions
#   - State-level moratoriums or restrictions
# This is a Phase 1 manual extraction; can be refined with Subsidy Tracker data.
_STATE_INCENTIVE_SCORES: dict[str, float] = {
    "VA": 0.90,  # Most generous: sales/use tax exemption, largest concentration
    "GA": 0.85,  # Sales tax exemption, aggressive recruitment
    "TX": 0.80,  # Ch. 313 (expired) / Ch. 403, property tax abatements
    "OH": 0.75,  # Tax incentive programs, Data Center Act
    "IN": 0.75,  # Personal property tax exemptions
    "NV": 0.75,  # Tax abatements for qualifying facilities
    "NC": 0.70,  # JDIG grants, property tax incentives
    "SC": 0.70,  # Fee-in-lieu, property tax abatements
    "IA": 0.65,  # Sales tax exemption for DC equipment
    "IL": 0.65,  # Enterprise zones, tax credits
    "MS": 0.65,  # Sales tax exemption, free land programs
    "TN": 0.65,  # Tax incentive programs
    "AZ": 0.60,  # Tax incentives but growing opposition
    "WA": 0.60,  # Sales tax deferral
    "OR": 0.55,  # Enterprise zones but water concerns
    "PA": 0.55,  # KOZ/KOEZ tax abatements (inconsistent across counties)
    "MI": 0.50,  # Some incentives but less aggressive
    "NY": 0.40,  # High taxes, some incentives in upstate regions
    "CA": 0.30,  # Stringent regulations, limited incentives
    "NJ": 0.30,  # Limited tax incentives, high operating costs
    "CT": 0.25,  # Few incentives, some moratoriums
}


def get_state_incentive_scores(fips_series: pd.Series) -> pd.Series:
    """Map county FIPS to state-level incentive generosity score.

    Parameters
    ----------
    fips_series : Series of 5-digit FIPS codes.

    Returns
    -------
    Series of float scores (0–1). States not in the manual table get 0.5 (neutral).
    """
    # Extract state abbreviation from county DataFrame or use FIPS prefix
    # We need state info — caller should pass state column alongside
    raise NotImplementedError("Use enrich_county_features() which has state info")


def _fips_to_state_score(state: str) -> float:
    """Look up incentive score for a state abbreviation."""
    return _STATE_INCENTIVE_SCORES.get(state, 0.50)


# ---------------------------------------------------------------------------
# Feature matrix assembly
# ---------------------------------------------------------------------------


def enrich_county_features(county_df: pd.DataFrame) -> pd.DataFrame:
    """Add external features to the county aggregation from ingest.py.

    Currently adds:
    - state_incentive_score: from manual table
    - water_stress_decile: placeholder (uniform random or zeros until Aqueduct data)
    - partisan_lean_r: placeholder (0.5 until election data loaded)
    - dc_employment: placeholder (0 until QWI data loaded)

    Parameters
    ----------
    county_df : Output of ``aggregate_to_county()`` with columns including
        ``fips``, ``state``.

    Returns
    -------
    DataFrame with additional feature columns.
    """
    df = county_df.copy()

    # State incentive generosity
    df["state_incentive_score"] = df["state"].map(_fips_to_state_score)

    # Placeholders for features requiring external data
    # These get replaced when real data is loaded via load_* functions
    if "water_stress_decile" not in df.columns:
        df["water_stress_decile"] = np.nan
    if "partisan_lean_r" not in df.columns:
        df["partisan_lean_r"] = np.nan
    if "dc_employment" not in df.columns:
        df["dc_employment"] = 0

    return df


# ---------------------------------------------------------------------------
# External data loaders (called when data files are available)
# ---------------------------------------------------------------------------


def load_water_stress(path: str | Path | None = None) -> pd.DataFrame:
    """Load county-level water stress data.

    Expected CSV columns: fips, water_stress_decile (1–10).
    If no file exists, returns empty DataFrame.
    """
    if path is None:
        path = _EXTERNAL_DIR / "water_stress.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["fips", "water_stress_decile"])
    return pd.read_csv(path, dtype={"fips": str})


def load_partisan_lean(path: str | Path | None = None) -> pd.DataFrame:
    """Load county-level partisan lean data.

    Expected CSV columns: fips, partisan_lean_r (float 0–1, fraction Republican).
    If no file exists, returns empty DataFrame.
    """
    if path is None:
        path = _EXTERNAL_DIR / "partisan_lean.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["fips", "partisan_lean_r"])
    return pd.read_csv(path, dtype={"fips": str})


def load_opposition_data(path: str | Path | None = None) -> pd.DataFrame:
    """Load supplementary opposition data (Bryce + Data Center Watch).

    Expected CSV columns: fips, county, state, opposition_type, source.
    If no file exists, returns empty DataFrame.
    """
    if path is None:
        path = _EXTERNAL_DIR / "opposition.csv"
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["fips", "county", "state", "opposition_type", "source"])
    return pd.read_csv(path, dtype={"fips": str})


def merge_external_features(
    county_df: pd.DataFrame,
    water_stress: pd.DataFrame | None = None,
    partisan_lean: pd.DataFrame | None = None,
    opposition: pd.DataFrame | None = None,
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

    return df


def build_feature_matrix(
    county_df: pd.DataFrame,
    water_stress_path: str | Path | None = None,
    partisan_lean_path: str | Path | None = None,
    opposition_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Build the complete county feature matrix.

    Orchestrates: enrich → load externals → merge → save.
    """
    df = enrich_county_features(county_df)

    water_stress = load_water_stress(water_stress_path)
    partisan_lean = load_partisan_lean(partisan_lean_path)
    opposition = load_opposition_data(opposition_path)

    df = merge_external_features(df, water_stress, partisan_lean, opposition)

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)

    return df
