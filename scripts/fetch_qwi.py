#!/usr/bin/env python3
"""Fetch county-level data center employment from Census QWI API.

Queries NAICS 518210 (Data Processing, Hosting and Related Services) for all
50 states + DC, one state at a time. Falls back to 4-digit NAICS 5182 if
518210 yields fewer than 30 counties with data.

Output: data/external/qwi_employment.csv
Cache:  data/raw/qwi/<state_fips>.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_KEY = "6c573a3e6b2e520391a1c4b731e20a7bda894bb2"
BASE_URL = "https://api.census.gov/data/timeseries/qwi/sa"

# All 50 states + DC FIPS codes (excludes territories)
STATE_FIPS = [
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12",
    "13", "15", "16", "17", "18", "19", "20", "21", "22", "23",
    "24", "25", "26", "27", "28", "29", "30", "31", "32", "33",
    "34", "35", "36", "37", "38", "39", "40", "41", "42", "44",
    "45", "46", "47", "48", "49", "50", "51", "53", "54", "55",
    "56",
]

YEARS = "2020,2021,2022,2023,2024"
QUARTERS = "1,2,3,4"
REQUEST_DELAY = 0.5  # seconds between API calls
MAX_RETRIES = 2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "qwi"
OUTPUT_PATH = PROJECT_ROOT / "data" / "external" / "qwi_employment.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_state(
    state_fips: str,
    industry: str = "518210",
    *,
    use_cache: bool = True,
) -> list[list[str]] | None:
    """Fetch QWI employment data for one state. Returns parsed JSON rows or None."""
    cache_file = RAW_DIR / f"{state_fips}_{industry}.json"

    if use_cache and cache_file.exists():
        with open(cache_file) as f:
            data = json.load(f)
        return data

    params = {
        "get": "Emp",
        "for": "county:*",
        "in": f"state:{state_fips}",
        "year": YEARS,
        "quarter": QUARTERS,
        "ownercode": "A05",
        "seasonadj": "U",
        "industry": industry,
        "key": API_KEY,
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=60)
            if resp.status_code == 204:
                # No content — state has no data for this NAICS
                cache_file.write_text("[]")
                return []
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
                    print(f"  [WARN] State {state_fips}: invalid JSON response")
                    return None
                # Cache raw response
                with open(cache_file, "w") as f:
                    json.dump(data, f)
                return data
            else:
                print(
                    f"  [WARN] State {state_fips} attempt {attempt+1}: "
                    f"HTTP {resp.status_code} — {resp.text[:200]}"
                )
        except requests.RequestException as e:
            print(f"  [WARN] State {state_fips} attempt {attempt+1}: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(2)

    return None


def parse_state_data(raw: list[list[str]]) -> pd.DataFrame:
    """Parse raw QWI JSON rows into a DataFrame with columns:
    fips, year, quarter, emp.
    """
    if not raw or len(raw) < 2:
        return pd.DataFrame(columns=["fips", "year", "quarter", "emp"])

    header = [h.lower() for h in raw[0]]
    rows = raw[1:]
    df = pd.DataFrame(rows, columns=header)

    # Build 5-digit FIPS
    df["fips"] = df["state"] + df["county"]

    # Parse employment — suppressed values come through as None/null/empty
    df["emp"] = pd.to_numeric(df["emp"], errors="coerce")

    # Parse year/quarter
    df["year"] = df["year"].astype(int)
    df["quarter"] = df["quarter"].astype(int)

    return df[["fips", "year", "quarter", "emp"]].copy()


def compute_employment_features(df: pd.DataFrame) -> pd.DataFrame:
    """From long-format (fips, year, quarter, emp) compute per-county:
    - dc_employment: latest available quarter's Emp
    - dc_employment_growth: (latest - earliest) / earliest over ~5 years
    """
    if df.empty:
        return pd.DataFrame(columns=["fips", "dc_employment", "dc_employment_growth"])

    # Drop suppressed rows
    df = df.dropna(subset=["emp"]).copy()
    if df.empty:
        return pd.DataFrame(columns=["fips", "dc_employment", "dc_employment_growth"])

    # Sort to identify earliest / latest per county
    df["period"] = df["year"] * 10 + df["quarter"]
    df = df.sort_values(["fips", "period"])

    records: list[dict[str, Any]] = []
    for fips, grp in df.groupby("fips"):
        latest = grp.iloc[-1]
        earliest = grp.iloc[0]
        emp_latest = int(latest["emp"])
        emp_earliest = int(earliest["emp"])

        if emp_earliest > 0:
            growth = (emp_latest - emp_earliest) / emp_earliest
        else:
            growth = float("nan")

        records.append({
            "fips": fips,
            "dc_employment": emp_latest,
            "dc_employment_growth": round(growth, 4) if pd.notna(growth) else growth,
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Try NAICS 518210
    # ------------------------------------------------------------------
    print("=== Fetching QWI data (NAICS 518210) ===")
    all_frames: list[pd.DataFrame] = []
    errors: list[str] = []

    for i, st in enumerate(STATE_FIPS):
        print(f"  [{i+1:2d}/{len(STATE_FIPS)}] State {st} ...", end=" ", flush=True)
        raw = fetch_state(st, industry="518210")
        if raw is None:
            errors.append(st)
            print("ERROR")
        elif len(raw) < 2:
            print("no data")
        else:
            parsed = parse_state_data(raw)
            valid = parsed.dropna(subset=["emp"])
            print(f"{len(valid)} obs, {valid['fips'].nunique()} counties")
            all_frames.append(parsed)
        time.sleep(REQUEST_DELAY)

    if errors:
        print(f"\n[WARN] Failed states: {errors}")

    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=["fips", "year", "quarter", "emp"])

    valid_counties = combined.dropna(subset=["emp"])["fips"].nunique()
    print(f"\nNAICS 518210: {valid_counties} counties with unsuppressed data")

    # ------------------------------------------------------------------
    # Step 2: Fallback to 4-digit NAICS 5182 if too few counties
    # ------------------------------------------------------------------
    if valid_counties < 30:
        print("\n=== Falling back to NAICS 5182 ===")
        all_frames = []
        errors = []

        for i, st in enumerate(STATE_FIPS):
            print(f"  [{i+1:2d}/{len(STATE_FIPS)}] State {st} ...", end=" ", flush=True)
            raw = fetch_state(st, industry="5182")
            if raw is None:
                errors.append(st)
                print("ERROR")
            elif len(raw) < 2:
                print("no data")
            else:
                parsed = parse_state_data(raw)
                valid = parsed.dropna(subset=["emp"])
                print(f"{len(valid)} obs, {valid['fips'].nunique()} counties")
                all_frames.append(parsed)
            time.sleep(REQUEST_DELAY)

        if all_frames:
            combined = pd.concat(all_frames, ignore_index=True)
        else:
            combined = pd.DataFrame(columns=["fips", "year", "quarter", "emp"])

        valid_counties = combined.dropna(subset=["emp"])["fips"].nunique()
        print(f"\nNAICS 5182: {valid_counties} counties with unsuppressed data")

    # ------------------------------------------------------------------
    # Step 3: Compute features and save
    # ------------------------------------------------------------------
    result = compute_employment_features(combined)
    print(f"\nFinal: {len(result)} counties with employment data")

    # Fill missing counties with 0 employment
    result["dc_employment"] = result["dc_employment"].fillna(0).astype(int)

    # Sort by FIPS
    result = result.sort_values("fips").reset_index(drop=True)

    # Ensure fips is zero-padded 5-digit string
    result["fips"] = result["fips"].str.zfill(5)

    result.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved to {OUTPUT_PATH}")
    print(f"  Counties with employment > 0: {(result['dc_employment'] > 0).sum()}")
    print(f"  Counties with growth data: {result['dc_employment_growth'].notna().sum()}")

    # Quick summary
    if not result.empty and (result["dc_employment"] > 0).any():
        top = result.nlargest(10, "dc_employment")
        print("\nTop 10 counties by DC employment:")
        for _, row in top.iterrows():
            print(f"  {row['fips']}: {row['dc_employment']:,} employees, growth={row['dc_employment_growth']}")


if __name__ == "__main__":
    main()
