"""Candidate generation: monthly data center proposals distributed by state and county."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_SHARES_PATH = _PROJECT_ROOT / "data" / "external" / "state_shares.csv"

# 2-digit state FIPS → abbreviation (used for all-county expansion)
STATE_FIPS_TO_ABBR: dict[str, str] = {
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


@dataclass
class Candidate:
    """A single data center proposal for one simulation month."""

    state: str
    county_fips: str
    mw: float


def load_state_shares(path: str | Path | None = None) -> pd.DataFrame:
    """Load state-level facility shares for candidate allocation.

    Returns DataFrame with columns: state, adjusted_share.
    Shares sum to ~1.0.
    """
    p = Path(path) if path else _STATE_SHARES_PATH
    df = pd.read_csv(p)
    # Normalize shares to exactly 1.0
    df["adjusted_share"] = df["adjusted_share"] / df["adjusted_share"].sum()
    return df


def build_state_county_map(
    approval_probs: pd.DataFrame,
    feature_matrix: pd.DataFrame | None = None,
) -> dict[str, list[str]]:
    """Build a mapping of state → list of county FIPS codes.

    Uses the county approval probs DataFrame (which has fips) joined with
    the feature matrix (which has state). Falls back to FIPS prefix if no
    feature matrix is provided.

    Parameters
    ----------
    approval_probs : DataFrame with at least a 'fips' column.
    feature_matrix : DataFrame with 'fips' and 'state' columns (optional).

    Returns
    -------
    dict mapping state abbreviation → list of FIPS codes in that state.
    """
    if feature_matrix is not None and "state" in feature_matrix.columns:
        merged = approval_probs[["fips"]].merge(
            feature_matrix[["fips", "state"]], on="fips", how="left"
        )
        # Fill missing states from FIPS prefix (for counties not in feature matrix)
        missing = merged["state"].isna()
        if missing.any():
            merged.loc[missing, "state"] = (
                merged.loc[missing, "fips"].str[:2].map(STATE_FIPS_TO_ABBR)
            )
    else:
        # Derive state from FIPS prefix (first 2 digits = state FIPS)
        merged = approval_probs[["fips"]].copy()
        merged["state"] = merged["fips"].str[:2].map(STATE_FIPS_TO_ABBR)

    state_county: dict[str, list[str]] = {}
    for _, row in merged.iterrows():
        st = row["state"]
        if pd.isna(st):
            continue
        state_county.setdefault(st, []).append(row["fips"])
    return state_county


def generate_candidates(
    rng: np.random.Generator,
    state_shares: pd.DataFrame,
    state_county_map: dict[str, list[str]],
    monthly_gw: float = 1.5,
    avg_project_mw: float = 300.0,
    pipeline_dropout_rate: float = 0.0,
    county_weights: dict[str, float] | None = None,
) -> list[Candidate]:
    """Generate candidate data center proposals for one simulation month.

    Parameters
    ----------
    rng : Seeded random generator.
    state_shares : DataFrame with 'state' and 'adjusted_share' columns.
    state_county_map : Mapping of state → list of county FIPS codes.
    monthly_gw : National GW additions per month.
    avg_project_mw : Average project size in MW.
    pipeline_dropout_rate : Fraction of candidates that drop out before proposal
        (Greenlink 2025: 40-60% of announced projects never materialize).
    county_weights : Optional FIPS → weight for weighted county selection.
        Counties with existing facilities should have higher weight.

    Returns
    -------
    List of Candidate objects for this month.
    """
    monthly_mw = monthly_gw * 1000.0
    n_candidates = max(1, round(monthly_mw / avg_project_mw))

    # Filter state_shares to only states that have counties in our map
    available_states = set(state_county_map.keys())
    mask = state_shares["state"].isin(available_states)
    filtered = state_shares[mask].copy()

    if filtered.empty:
        return []

    # Re-normalize shares for available states
    shares = filtered["adjusted_share"].values.astype(float)
    shares = shares / shares.sum()
    states = filtered["state"].values

    # Draw states from multinomial
    state_draws = rng.choice(states, size=n_candidates, p=shares)

    candidates = []
    for state in state_draws:
        counties = state_county_map[state]
        if county_weights is not None:
            # Weighted county selection: existing facility counties get higher weight
            weights = np.array([county_weights.get(c, 1.0) for c in counties])
            weights = weights / weights.sum()
            county_fips = rng.choice(counties, p=weights)
        else:
            county_fips = rng.choice(counties)
        candidates.append(Candidate(state=state, county_fips=county_fips, mw=avg_project_mw))

    # Pipeline dropout: each candidate independently drops out
    if pipeline_dropout_rate > 0:
        keep_mask = rng.random(len(candidates)) >= pipeline_dropout_rate
        candidates = [c for c, keep in zip(candidates, keep_mask) if keep]

    return candidates
