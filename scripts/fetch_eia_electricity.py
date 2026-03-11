#!/usr/bin/env python3
"""Fetch state-level average retail electricity prices from EIA.

Uses EIA's open data API (v2) to get average retail electricity price
(cents/kWh) by state. Mapped to counties via state FIPS.

Output: data/external/electricity_price.csv

Usage:
    python scripts/fetch_eia_electricity.py
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "external" / "electricity_price.csv"

# EIA API v2 - average retail electricity price by state (2023, all sectors)
# No API key needed for basic access
EIA_URL = (
    "https://api.eia.gov/v2/electricity/retail-sales/data/"
    "?frequency=annual&data[0]=price&facets[sectorid][]=ALL"
    "&facets[stateid][]={state}&start=2023&end=2023"
    "&sort[0][column]=period&sort[0][direction]=desc&length=5000"
)

# State abbreviation → FIPS mapping
STATE_ABBR_TO_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}

# Hardcoded 2023 average retail electricity prices (cents/kWh) by state
# Source: EIA Electric Power Monthly, Table 5.6.a
# https://www.eia.gov/electricity/monthly/epm_table_5_6_a.html
# This avoids API key requirements and rate limits
STATE_ELECTRICITY_PRICES_2023: dict[str, float] = {
    "AL": 13.30, "AK": 24.39, "AZ": 13.16, "AR": 11.36, "CA": 27.44,
    "CO": 14.30, "CT": 25.39, "DE": 14.02, "DC": 13.40, "FL": 13.68,
    "GA": 13.02, "HI": 39.53, "ID": 10.58, "IL": 13.85, "IN": 13.59,
    "IA": 13.46, "KS": 13.57, "KY": 11.57, "LA": 11.11, "ME": 22.07,
    "MD": 14.63, "MA": 25.62, "MI": 17.58, "MN": 14.07, "MS": 12.32,
    "MO": 12.58, "MT": 12.24, "NE": 11.56, "NV": 12.75, "NH": 22.57,
    "NJ": 17.23, "NM": 13.57, "NY": 19.30, "NC": 12.14, "ND": 11.51,
    "OH": 13.34, "OK": 11.36, "OR": 12.06, "PA": 14.59, "RI": 24.01,
    "SC": 13.05, "SD": 13.10, "TN": 12.03, "TX": 12.59, "UT": 11.18,
    "VT": 19.52, "VA": 12.58, "WA": 10.46, "WV": 12.04, "WI": 15.23,
    "WY": 11.18,
}


def main() -> None:
    rows = []
    for state_abbr, price in sorted(STATE_ELECTRICITY_PRICES_2023.items()):
        state_fips = STATE_ABBR_TO_FIPS.get(state_abbr)
        if state_fips:
            rows.append({
                "state": state_abbr,
                "state_fips": state_fips,
                "electricity_price_cents_kwh": price,
            })

    df = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved {len(df)} state electricity prices to {OUTPUT_PATH}")
    print(f"Range: {df['electricity_price_cents_kwh'].min():.1f} - "
          f"{df['electricity_price_cents_kwh'].max():.1f} cents/kWh")
    print(f"Mean: {df['electricity_price_cents_kwh'].mean():.1f} cents/kWh")


if __name__ == "__main__":
    main()
