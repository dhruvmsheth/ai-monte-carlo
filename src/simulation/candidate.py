"""Candidate generation: monthly data center proposals distributed by state and county."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_SHARES_PATH = _PROJECT_ROOT / "data" / "external" / "state_shares.csv"


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
    else:
        # Derive state from FIPS prefix (first 2 digits = state FIPS)
        # This is a fallback — less precise since we need state abbreviations
        # for matching with state_shares
        merged = approval_probs[["fips"]].copy()
        merged["state"] = merged["fips"].str[:2]

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
) -> list[Candidate]:
    """Generate candidate data center proposals for one simulation month.

    Parameters
    ----------
    rng : Seeded random generator.
    state_shares : DataFrame with 'state' and 'adjusted_share' columns.
    state_county_map : Mapping of state → list of county FIPS codes.
    monthly_gw : National GW additions per month.
    avg_project_mw : Average project size in MW.

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
        # Phase 1: uniform county selection within state
        county_fips = rng.choice(counties)
        candidates.append(Candidate(state=state, county_fips=county_fips, mw=avg_project_mw))

    return candidates
