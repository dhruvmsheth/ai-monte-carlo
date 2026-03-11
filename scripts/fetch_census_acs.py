#!/usr/bin/env python3
"""Fetch county-level demographic features from Census ACS 5-Year API.

Fetches: population, median income, unemployment rate, education level,
agricultural employment share. Also downloads Gazetteer for land area
to compute population density.

Output: data/external/census_acs.csv

Usage:
    python scripts/fetch_census_acs.py --api-key YOUR_KEY
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "external" / "census_acs.csv"
GAZETTEER_CACHE = PROJECT_ROOT / "data" / "raw" / "gazetteer_2020.tsv"

# Census ACS 5-Year 2022 (latest stable release)
ACS_BASE = "https://api.census.gov/data/2022/acs/acs5"
ACS_PROFILE_BASE = "https://api.census.gov/data/2022/acs/acs5/profile"

# Variables to fetch from base ACS5 endpoint
ACS_VARS = [
    "B01003_001E",  # Total population
    "B19013_001E",  # Median household income
    "B23025_003E",  # Civilian labor force
    "B23025_005E",  # Unemployed
    "B15003_001E",  # Pop 25+ (education denominator)
    "B15003_022E",  # Bachelor's degree
    "B15003_023E",  # Master's degree
    "B15003_024E",  # Professional degree
    "B15003_025E",  # Doctorate degree
]

# Variables from ACS5 profile endpoint (agriculture employment)
PROFILE_VARS = [
    "DP03_0033E",  # Employed in agriculture/forestry/fishing/hunting/mining
    "DP03_0004E",  # Total civilian employed population 16+
]

# Census Gazetteer for land area
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2020_Gazetteer/2020_Gaz_counties_national.zip"
)

SQ_METERS_PER_SQ_MILE = 2_589_988.11


def fetch_acs_data(api_key: str) -> dict[str, dict]:
    """Fetch ACS variables for all US counties."""
    var_str = ",".join(ACS_VARS)
    url = f"{ACS_BASE}?get=NAME,{var_str}&for=county:*&in=state:*&key={api_key}"
    print(f"Fetching ACS base variables for all counties...")

    req = Request(url, headers={"User-Agent": "DCConsentSim/1.0"})
    with urlopen(req) as resp:
        data = json.loads(resp.read())

    headers = data[0]
    results: dict[str, dict] = {}
    for row in data[1:]:
        record = dict(zip(headers, row))
        fips = record["state"] + record["county"]
        results[fips] = {
            "name": record["NAME"],
            "population": _safe_int(record.get("B01003_001E")),
            "median_income": _safe_int(record.get("B19013_001E")),
            "civilian_labor_force": _safe_int(record.get("B23025_003E")),
            "unemployed": _safe_int(record.get("B23025_005E")),
            "pop_25_plus": _safe_int(record.get("B15003_001E")),
            "bachelors": _safe_int(record.get("B15003_022E")),
            "masters": _safe_int(record.get("B15003_023E")),
            "professional": _safe_int(record.get("B15003_024E")),
            "doctorate": _safe_int(record.get("B15003_025E")),
        }

    print(f"  Fetched {len(results)} counties from ACS base")
    return results


def fetch_profile_data(api_key: str) -> dict[str, dict]:
    """Fetch ACS profile variables (agriculture employment)."""
    var_str = ",".join(PROFILE_VARS)
    url = f"{ACS_PROFILE_BASE}?get=NAME,{var_str}&for=county:*&in=state:*&key={api_key}"
    print(f"Fetching ACS profile variables (agriculture)...")

    req = Request(url, headers={"User-Agent": "DCConsentSim/1.0"})
    with urlopen(req) as resp:
        data = json.loads(resp.read())

    headers = data[0]
    results: dict[str, dict] = {}
    for row in data[1:]:
        record = dict(zip(headers, row))
        fips = record["state"] + record["county"]
        results[fips] = {
            "ag_employment": _safe_int(record.get("DP03_0033E")),
            "total_civilian_employed": _safe_int(record.get("DP03_0004E")),
        }

    print(f"  Fetched {len(results)} counties from ACS profile")
    return results


def fetch_gazetteer() -> dict[str, float]:
    """Download Gazetteer and extract land area per county (sq miles)."""
    if GAZETTEER_CACHE.exists():
        print(f"Using cached Gazetteer: {GAZETTEER_CACHE}")
        with open(GAZETTEER_CACHE) as f:
            return _parse_gazetteer(f.read())

    print("Downloading Census Gazetteer (land area)...")
    req = Request(GAZETTEER_URL, headers={"User-Agent": "DCConsentSim/1.0"})
    with urlopen(req) as resp:
        zip_data = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        # Find the TSV file
        tsv_name = [n for n in zf.namelist() if n.endswith(".txt")][0]
        content = zf.read(tsv_name).decode("latin-1")

    # Cache it
    GAZETTEER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(GAZETTEER_CACHE, "w") as f:
        f.write(content)
    print(f"  Cached to {GAZETTEER_CACHE}")

    return _parse_gazetteer(content)


def _parse_gazetteer(content: str) -> dict[str, float]:
    """Parse Gazetteer TSV → {fips: land_area_sq_miles}."""
    result = {}
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    for row in reader:
        fips = row.get("GEOID", "").strip()
        aland = row.get("ALAND", "").strip()
        if fips and aland:
            try:
                result[fips] = float(aland) / SQ_METERS_PER_SQ_MILE
            except ValueError:
                pass
    print(f"  Parsed {len(result)} counties from Gazetteer")
    return result


def _safe_int(val: str | None) -> int:
    """Convert Census API value to int, handling nulls and negatives."""
    if val is None or val == "" or val == "null":
        return 0
    try:
        v = int(val)
        return max(v, 0)  # Census uses negative values for missing/suppressed
    except (ValueError, TypeError):
        return 0


def build_census_features(
    acs: dict[str, dict],
    profile: dict[str, dict],
    land_area: dict[str, float],
) -> list[dict]:
    """Combine all Census data into feature rows."""
    rows = []
    for fips, data in sorted(acs.items()):
        pop = data["population"]
        area = land_area.get(fips, 0.0)

        # Population density (people per sq mile)
        pop_density = pop / area if area > 0 else 0.0

        # Unemployment rate
        labor_force = data["civilian_labor_force"]
        unemployed = data["unemployed"]
        unemployment_rate = unemployed / labor_force if labor_force > 0 else 0.0

        # Percent college educated (bachelor's+)
        pop_25 = data["pop_25_plus"]
        college = data["bachelors"] + data["masters"] + data["professional"] + data["doctorate"]
        pct_college = college / pop_25 if pop_25 > 0 else 0.0

        # Agriculture employment share
        prof = profile.get(fips, {})
        ag_emp = prof.get("ag_employment", 0)
        total_emp = prof.get("total_civilian_employed", 0)
        ag_share = ag_emp / total_emp if total_emp > 0 else 0.0

        rows.append({
            "fips": fips,
            "population": pop,
            "population_density": round(pop_density, 2),
            "median_household_income": data["median_income"],
            "unemployment_rate": round(unemployment_rate, 4),
            "pct_college_educated": round(pct_college, 4),
            "ag_employment_share": round(ag_share, 4),
        })

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Census ACS features")
    parser.add_argument("--api-key", required=True, help="Census API key")
    args = parser.parse_args()

    acs = fetch_acs_data(args.api_key)
    profile = fetch_profile_data(args.api_key)
    land_area = fetch_gazetteer()

    rows = build_census_features(acs, profile, land_area)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved {len(df)} counties to {OUTPUT_PATH}")
    print(f"Columns: {list(df.columns)}")
    print(f"\nSample stats:")
    for col in ["population_density", "median_household_income", "unemployment_rate",
                 "pct_college_educated", "ag_employment_share"]:
        print(f"  {col}: mean={df[col].mean():.2f}, min={df[col].min():.2f}, max={df[col].max():.2f}")


if __name__ == "__main__":
    main()
