"""FracTracker ingestion pipeline: load, clean, FIPS-map, classify, aggregate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import addfips
import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_RAW_CSV = _PROJECT_ROOT / "data" / "raw" / "Data_Centers_Database - FracTracker Data Centers.csv"

# Hyperscaler operator name variants → canonical name
_HYPERSCALER_VARIANTS: dict[str, str] = {
    "microsoft": "Microsoft",
    "microsoft corporation": "Microsoft",
    "amazon": "Amazon",
    "amazon data services inc": "Amazon",
    "amazon data services": "Amazon",
    "google": "Google",
    "meta": "Meta",
    "meta platforms": "Meta",
    "apple": "Apple",
    "oracle": "Oracle",
}

# County name corrections for FIPS mapping failures.
# Keys: (county_as_in_csv, state) → (corrected_county, corrected_state)
_COUNTY_FIXES: dict[tuple[str, str], tuple[str, str] | None] = {
    ("Athens-Clark", "GA"): ("Clarke", "GA"),
    ("Carroll and Haralson", "GA"): ("Carroll", "GA"),
    ("Cumberland and Harnett", "NC"): ("Cumberland", "NC"),
    ("Marrietta", "GA"): ("Cobb", "GA"),
    ("Spaulding", "GA"): ("Spalding", "GA"),
    ("St Charles County", "MO"): ("St. Charles", "MO"),
    ("St Lucie", "FL"): ("St. Lucie", "FL"),
    # Data error: Google Red Oak lists WY but lat/long is in Ohio
    ("Lawrence", "WY"): ("Lawrence", "OH"),
}

# Size ranks that count as Tier 1 (>100 MW)
_TIER1_RANKS = {"Hyperscale (100-999 MW)", "Mega campus (>1,000 MW)"}

# Statuses that count as "approved" (facility was built or permitted)
_APPROVED_STATUSES = {"Operating", "Approved/Permitted/Under construction", "Expanding"}

# Statuses that count as "blocked"
_BLOCKED_STATUSES = {"Suspended", "Cancelled"}


# ---------------------------------------------------------------------------
# Loading and cleaning
# ---------------------------------------------------------------------------


def load_fractracker(path: str | Path | None = None) -> pd.DataFrame:
    """Load and clean the FracTracker CSV.

    Returns a cleaned DataFrame with all original columns plus:
    - ``fips``: 5-digit FIPS code (string)
    - ``mw_numeric``: MW as float (NaN where missing/unparseable)
    - ``pushback``: boolean (True if community_pushback == "Yes")
    - ``is_hyperscaler``: boolean
    - ``hyperscaler_name``: canonical name or None
    """
    csv_path = Path(path) if path is not None else _RAW_CSV
    df = pd.read_csv(csv_path, dtype=str)

    # Strip whitespace from all string columns
    for col in df.columns:
        df[col] = df[col].str.strip()

    # Parse MW to numeric
    df["mw_numeric"] = _parse_mw(df["mw"])

    # Normalize pushback to boolean
    df["pushback"] = df["community_pushback"].str.lower().str.strip() == "yes"

    # Identify hyperscaler operators
    df["hyperscaler_name"] = df["operator_name"].map(_match_hyperscaler)
    df["is_hyperscaler"] = df["hyperscaler_name"].notna()

    # Add FIPS codes
    df = add_fips_codes(df)

    return df


def _parse_mw(mw_series: pd.Series) -> pd.Series:
    """Parse the MW column to float, handling '>', commas, and non-numeric values."""
    cleaned = mw_series.str.replace(",", "", regex=False)
    cleaned = cleaned.str.replace(">", "", regex=False)
    cleaned = cleaned.str.strip()
    return pd.to_numeric(cleaned, errors="coerce")


def _match_hyperscaler(operator: Any) -> str | None:
    """Map an operator name to its canonical hyperscaler name, or None."""
    if not isinstance(operator, str) or operator.strip() == "":
        return None
    key = operator.strip().lower()
    return _HYPERSCALER_VARIANTS.get(key)


# ---------------------------------------------------------------------------
# FIPS mapping
# ---------------------------------------------------------------------------


def add_fips_codes(df: pd.DataFrame) -> pd.DataFrame:
    """Add 5-digit FIPS codes to a DataFrame with ``county`` and ``state`` columns.

    Applies known county-name corrections, then uses the ``addfips`` library.
    Rows that still fail get FIPS = None and are logged.
    """
    af = addfips.AddFIPS()
    fips_codes: list[str | None] = []

    for _, row in df.iterrows():
        county = str(row["county"]).strip()
        state = str(row["state"]).strip()

        # Apply known fixes
        fix = _COUNTY_FIXES.get((county, state))
        if fix is not None:
            county, state = fix

        fips = af.get_county_fips(county, state=state)
        fips_codes.append(fips)

    df = df.copy()
    df["fips"] = fips_codes
    return df


def validate_fips(df: pd.DataFrame) -> list[str]:
    """Validate FIPS codes. Returns a list of error messages (empty = OK)."""
    errors: list[str] = []

    null_count = df["fips"].isna().sum()
    if null_count > 0:
        errors.append(f"{null_count} rows have null FIPS codes")

    # Check FIPS is 5 digits
    valid_fips = df["fips"].dropna()
    bad_len = valid_fips[valid_fips.str.len() != 5]
    if len(bad_len) > 0:
        errors.append(f"{len(bad_len)} FIPS codes are not 5 digits")

    # Spot-check known counties
    _KNOWN = {
        ("Loudoun", "VA"): "51107",
        ("Prince William", "VA"): "51153",
        ("Maricopa", "AZ"): "04013",
        ("Bexar", "TX"): "48029",
    }
    for (county, state), expected_fips in _KNOWN.items():
        matches = df[(df["county"] == county) & (df["state"] == state)]
        if len(matches) > 0:
            actual = matches["fips"].iloc[0]
            if actual != expected_fips:
                errors.append(
                    f"FIPS mismatch: {county}, {state} expected {expected_fips} got {actual}"
                )

    return errors


# ---------------------------------------------------------------------------
# Tier classification and county aggregation
# ---------------------------------------------------------------------------


def classify_tiers(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the cleaned FracTracker data into Tier 1 and Tier 2.

    Tier 1: Hyperscale + Mega (>100 MW) — for model training.
    Tier 2: All Operating facilities — for saturation counts.

    Returns (tier1_df, tier2_df).
    """
    tier1 = df[df["sizerank"].isin(_TIER1_RANKS)].copy()
    tier2 = df[df["status"] == "Operating"].copy()
    return tier1, tier2


def _code_county_outcome(group: pd.DataFrame) -> int | None:
    """Determine binary outcome for a county's facilities.

    Returns 1 (approved), 0 (blocked), or None (no clear outcome).
    """
    n_approved = group["status"].isin(_APPROVED_STATUSES).sum()
    n_blocked = group["status"].isin(_BLOCKED_STATUSES).sum()
    n_decided = n_approved + n_blocked

    if n_decided == 0:
        return None  # Only proposed — no outcome yet
    return 1 if n_approved >= n_blocked else 0


def aggregate_to_county(
    tier1: pd.DataFrame,
    tier2: pd.DataFrame,
    all_facilities: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Aggregate facility-level data to county level.

    Parameters
    ----------
    tier1 : Tier 1 facilities (Hyperscale + Mega) — used for features and outcomes.
    tier2 : Tier 2 facilities (all Operating) — used for saturation counts.
    all_facilities : Full cleaned DataFrame (all rows) — used for pushback flags
        so we capture opposition noted on ANY facility, not just Tier 1.
        If None, falls back to using tier1 only for pushback.

    Returns
    -------
    DataFrame with one row per county (keyed by ``fips``), containing:
    - facility_count, total_mw, avg_project_mw
    - saturation_count (from Tier 2)
    - pushback_flag (from ALL facilities), hyperscaler_share (from Tier 1)
    - binary_outcome (1=approved, 0=blocked, NaN=undecided)
    - county, state (first occurrence)
    """
    # Drop rows with missing FIPS
    tier1 = tier1.dropna(subset=["fips"]).copy()
    tier2 = tier2.dropna(subset=["fips"]).copy()

    # --- Saturation counts from Tier 2 ---
    saturation = tier2.groupby("fips").size().rename("saturation_count")

    # --- Pushback from ALL facilities (not just Tier 1) ---
    # This ensures we capture opposition noted on any facility in the county,
    # including the many "Unknown" sizerank entries in Virginia.
    if all_facilities is not None:
        all_clean = all_facilities.dropna(subset=["fips"]).copy()
        pushback = all_clean.groupby("fips")["pushback"].any().astype(int).rename("pushback_flag")
    else:
        pushback = tier1.groupby("fips")["pushback"].any().astype(int).rename("pushback_flag")

    # --- County-level aggregation from Tier 1 ---
    grouped = tier1.groupby("fips")

    # Basic counts
    facility_count = grouped.size().rename("facility_count")
    total_mw = grouped["mw_numeric"].sum().rename("total_mw")

    # Average project MW (only from facilities with known MW)
    avg_mw = grouped["mw_numeric"].mean().rename("avg_project_mw")

    # Hyperscaler share (from Tier 1 only — these are the >100MW facilities
    # where operator identity is most meaningful)
    hyperscaler_share = grouped["is_hyperscaler"].mean().rename("hyperscaler_share")

    # Binary outcome
    outcomes = grouped.apply(_code_county_outcome, include_groups=False).rename("binary_outcome")

    # County/state names (take first)
    names = grouped[["county", "state"]].first()

    # Combine
    county_df = pd.concat(
        [names, facility_count, total_mw, avg_mw, hyperscaler_share, outcomes],
        axis=1,
    )
    county_df.index.name = "fips"

    # Merge saturation from Tier 2
    county_df = county_df.join(saturation, how="left")
    county_df["saturation_count"] = county_df["saturation_count"].fillna(0).astype(int)

    # Merge pushback (from all facilities) — left join keeps only counties in Tier 1
    county_df = county_df.join(pushback, how="left")
    county_df["pushback_flag"] = county_df["pushback_flag"].fillna(0).astype(int)

    # Impute missing avg_project_mw with median of known values
    median_mw = county_df["avg_project_mw"].median()
    county_df["avg_project_mw"] = county_df["avg_project_mw"].fillna(median_mw)

    return county_df.reset_index()


# ---------------------------------------------------------------------------
# State shares for candidate queue
# ---------------------------------------------------------------------------


def compute_state_shares(
    df: pd.DataFrame,
    exploration_pct: float = 0.005,
) -> pd.DataFrame:
    """Compute state-level facility shares for the candidate queue.

    Parameters
    ----------
    df : Full cleaned FracTracker DataFrame (all facilities, not just Tier 1).
    exploration_pct : Fraction of total probability mass reserved for zero-facility
        states, split equally among them.

    Returns
    -------
    DataFrame with columns: state, facility_count, raw_share, adjusted_share.
    """
    counts = df.groupby("state").size().reset_index(name="facility_count")
    total = counts["facility_count"].sum()
    counts["raw_share"] = counts["facility_count"] / total

    # All U.S. states + DC
    all_states = [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    ]

    # Reindex to include all states
    full = pd.DataFrame({"state": all_states})
    full = full.merge(counts, on="state", how="left")
    full["facility_count"] = full["facility_count"].fillna(0).astype(int)
    full["raw_share"] = full["raw_share"].fillna(0.0)

    # Apply exploration term
    zero_states = full[full["facility_count"] == 0]
    n_zero = len(zero_states)

    if n_zero > 0 and exploration_pct > 0:
        per_zero_share = exploration_pct / n_zero
        # Scale down existing shares to make room
        scale = 1.0 - exploration_pct
        full["adjusted_share"] = np.where(
            full["facility_count"] > 0,
            full["raw_share"] * scale,
            per_zero_share,
        )
    else:
        full["adjusted_share"] = full["raw_share"]

    return full.sort_values("adjusted_share", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Convenience: run full pipeline
# ---------------------------------------------------------------------------


def run_ingestion(
    csv_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Run the full FracTracker ingestion pipeline.

    Returns dict with keys: 'raw', 'tier1', 'tier2', 'county', 'state_shares'.
    Optionally writes CSVs to *output_dir*.
    """
    df = load_fractracker(csv_path)
    tier1, tier2 = classify_tiers(df)
    county = aggregate_to_county(tier1, tier2, all_facilities=df)
    state_shares = compute_state_shares(df)

    result = {
        "raw": df,
        "tier1": tier1,
        "tier2": tier2,
        "county": county,
        "state_shares": state_shares,
    }

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        county.to_csv(out / "county_facilities.csv", index=False)

    return result
