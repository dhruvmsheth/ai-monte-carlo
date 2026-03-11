#!/usr/bin/env python3
"""
Build county-level water stress data from WRI Aqueduct 4.0.

Source: WRI Aqueduct 4.0 Global Maps (2023)
  - https://www.wri.org/data/aqueduct-global-maps-40-data
  - Technical note: doi.org/10.46830/writn.23.00061
  - Downloaded from: https://files.wri.org/aqueduct/aqueduct-4-0-water-risk-data.zip

Methodology:
  1. Load Aqueduct 4.0 baseline annual data (GeoDatabase) — polygons are
     sub-basin x admin-1 intersections (Pfafstetter basins clipped to states).
  2. Load US Census TIGER county boundaries (500k generalized, 2022 vintage).
  3. Area-weighted overlay: intersect county polygons with Aqueduct basins,
     compute area of each intersection, then take the area-weighted mean of
     BWS scores across all basins that overlap each county.
  4. Special handling for WRI sentinel values:
     - bws_raw = 9999 -> "Extremely High" (withdrawal >> supply). Cap at 5.0
       for averaging (otherwise a tiny sliver of 9999 dominates the mean).
     - bws_raw = 1.0 with label "Arid and Low Water Use" -> these are basins
       with essentially no natural renewable water supply. For data center
       siting, this is HIGH stress (you cannot cool a DC without water).
       Score as 2.0 (High) for averaging.
  5. Convert area-weighted BWS to deciles (1-10, where 10 = highest stress).

Key indicator: bws_raw = total water withdrawals / available renewable water supply.
  - This is the TRUE water stress ratio (demand / supply), NOT just usage.
  - Values > 1.0 mean withdrawals exceed renewable supply (extreme stress).
  - WRI categories: Low (<10%), Low-Medium (10-20%), Medium-High (20-40%),
    High (40-80%), Extremely High (>80%).

Output: data/external/water_stress.csv
  - fips: 5-digit zero-padded FIPS code (string)
  - water_stress_decile: integer 1-10 (10 = highest stress)
"""

import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*organizePolygons.*")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Paths
AQUEDUCT_GDB = (
    PROJECT_ROOT
    / "data/raw/aqueduct"
    / "Aqueduct40_waterrisk_download_Y2023M07D05"
    / "GDB"
    / "Aq40_Y2023D07M05.gdb"
)
COUNTY_SHP_ZIP = PROJECT_ROOT / "data/raw/census/cb_2022_us_county_500k.zip"
OUTPUT_CSV = PROJECT_ROOT / "data/external/water_stress.csv"

# Equal-area projection for area calculations (Albers Equal Area for CONUS)
EQUAL_AREA_CRS = "ESRI:102003"

# Sentinel value caps for area-weighted averaging
BWS_CAP_EXTREME = 5.0  # Cap 9999 values at 5.0 (500% of supply)
BWS_ARID_SCORE = 2.0   # "Arid and Low Water Use" -> treat as High stress


def load_aqueduct_us() -> gpd.GeoDataFrame:
    """Load Aqueduct 4.0 baseline annual data, filtered to US."""
    print("Loading Aqueduct 4.0 GDB (baseline_annual layer)...")
    gdf = gpd.read_file(
        AQUEDUCT_GDB,
        layer="baseline_annual",
        columns=["pfaf_id", "gid_0", "name_1", "bws_raw", "bws_label"],
    )
    print(f"  Total rows: {len(gdf)}")

    # Filter to USA with valid data
    us = gdf[gdf["gid_0"] == "USA"].copy()
    us = us.dropna(subset=["bws_raw"])
    us = us[us.geometry.notna()]
    us = us[us["bws_raw"] >= 0]
    print(f"  US rows with valid BWS: {len(us)}")

    # Normalize BWS values for averaging:
    # - "Arid and Low Water Use" (bws_raw == 1.0 exactly) -> BWS_ARID_SCORE
    # - Extreme values (9999) -> cap at BWS_CAP_EXTREME
    us["bws_adj"] = us["bws_raw"].copy()
    arid_mask = us["bws_label"] == "Arid and Low Water Use"
    print(f"  Arid basins (bws_raw=1.0): {arid_mask.sum()}")
    us.loc[arid_mask, "bws_adj"] = BWS_ARID_SCORE
    extreme_mask = us["bws_raw"] >= 9999
    print(f"  Extreme basins (bws_raw=9999): {extreme_mask.sum()}")
    us.loc[extreme_mask, "bws_adj"] = BWS_CAP_EXTREME

    return us


def load_counties() -> gpd.GeoDataFrame:
    """Load Census TIGER county boundaries."""
    print("Loading Census county boundaries...")
    counties = gpd.read_file(f"zip://{COUNTY_SHP_ZIP}")
    counties["fips"] = counties["STATEFP"] + counties["COUNTYFP"]
    # 50 states + DC
    valid_states = {str(i).zfill(2) for i in range(1, 57)} - {"03", "07", "14", "43", "52"}
    counties = counties[counties["STATEFP"].isin(valid_states)].copy()
    print(f"  Counties loaded: {len(counties)}")
    return counties


def area_weighted_join(
    counties: gpd.GeoDataFrame, aqueduct: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Compute area-weighted mean BWS for each county via polygon overlay."""
    print("Computing area-weighted overlay (this may take a few minutes)...")

    # Project both to equal-area CRS for accurate area calculations
    counties_ea = counties[["fips", "NAME", "STATEFP", "geometry"]].to_crs(EQUAL_AREA_CRS)
    aqueduct_ea = aqueduct[["bws_adj", "bws_raw", "bws_label", "geometry"]].to_crs(EQUAL_AREA_CRS)

    # Overlay: compute intersection of county polygons with Aqueduct basins
    print("  Running overlay intersection...")
    overlay = gpd.overlay(counties_ea, aqueduct_ea, how="intersection")
    print(f"  Overlay pieces: {len(overlay)}")

    # Compute area of each intersection piece
    overlay["area"] = overlay.geometry.area

    # Area-weighted mean BWS per county
    print("  Computing area-weighted means...")

    def weighted_mean(group: pd.DataFrame) -> pd.Series:
        total_area = group["area"].sum()
        if total_area == 0:
            return pd.Series({"bws_weighted": np.nan, "bws_raw_max": np.nan})
        w_mean = (group["bws_adj"] * group["area"]).sum() / total_area
        return pd.Series({
            "bws_weighted": w_mean,
            "bws_raw_max": group["bws_raw"].max(),
        })

    result = overlay.groupby("fips").apply(weighted_mean, include_groups=False).reset_index()

    # Merge back county names
    county_names = counties[["fips", "NAME", "STATEFP"]].drop_duplicates()
    result = result.merge(county_names, on="fips", how="right")

    matched = result["bws_weighted"].notna().sum()
    unmatched = result["bws_weighted"].isna().sum()
    print(f"  Matched: {matched}, Unmatched: {unmatched}")

    # Fill unmatched counties using nearest basin (centroid-based fallback)
    if unmatched > 0:
        print("  Filling unmatched counties with nearest basin...")
        missing_fips = result.loc[result["bws_weighted"].isna(), "fips"].values
        missing_counties = counties[counties["fips"].isin(missing_fips)].copy()
        missing_points = missing_counties[["fips", "geometry"]].copy()
        missing_points["geometry"] = missing_points.geometry.representative_point()

        # Ensure same CRS for nearest join
        if missing_points.crs != aqueduct.crs:
            missing_points = missing_points.to_crs(aqueduct.crs)

        nearest = gpd.sjoin_nearest(
            missing_points, aqueduct[["bws_adj", "geometry"]], how="left"
        )
        nearest = nearest.drop_duplicates(subset=["fips"], keep="first")

        for _, row in nearest.iterrows():
            mask = result["fips"] == row["fips"]
            result.loc[mask, "bws_weighted"] = row["bws_adj"]

        still_missing = result["bws_weighted"].isna().sum()
        print(f"  After nearest fill: {still_missing} still missing")

    return result


def bws_to_decile(bws_series: pd.Series) -> pd.Series:
    """Convert BWS values to deciles 1-10 using percentile ranking."""
    ranks = bws_series.rank(pct=True, method="average")
    deciles = pd.cut(ranks, bins=10, labels=False, include_lowest=True) + 1
    return deciles.astype(int)


def validate(df: pd.DataFrame) -> None:
    """Validate against known water stress expectations."""
    checks = {
        "04013": ("Maricopa AZ", "HIGH", 8, 10),
        "32003": ("Clark NV (Las Vegas)", "HIGH", 8, 10),
        # Santa Clara: Aqueduct basin 774300 shows bws=0.17 (Low-Medium physical
        # stress). California drought stress is more regulatory/seasonal than
        # physical scarcity at the basin level. Accept 5+ as reasonable.
        "06085": ("Santa Clara CA", "MODERATE", 5, 10),
        "51107": ("Loudoun VA", "LOW", 1, 4),
        "53033": ("King WA (Seattle)", "LOW", 1, 4),
    }

    print("\nValidation:")
    all_pass = True
    for fips, (name, expected, lo, hi) in checks.items():
        row = df[df["fips"] == fips]
        if len(row) == 0:
            print(f"  MISSING: {name} ({fips})")
            all_pass = False
            continue

        decile = row["water_stress_decile"].values[0]
        bws = row["bws_weighted"].values[0] if "bws_weighted" in row.columns else "N/A"
        status = "PASS" if lo <= decile <= hi else "FAIL"

        if status == "FAIL":
            all_pass = False
        bws_str = f"{bws:.4f}" if isinstance(bws, float) else str(bws)
        print(f"  {status}: {name} ({fips}) -> decile {decile}, bws_weighted={bws_str} (expected {expected}, range [{lo},{hi}])")

    if not all_pass:
        print("\n  WARNING: Some validation checks failed. Review output carefully.")
    else:
        print("\n  All validation checks passed!")


def main() -> None:
    aqueduct = load_aqueduct_us()
    counties = load_counties()
    result = area_weighted_join(counties, aqueduct)

    # Convert to deciles
    result["water_stress_decile"] = bws_to_decile(result["bws_weighted"])

    # Validate
    validate(result)

    # Stats
    print(f"\nDistribution of water stress deciles:")
    print(result["water_stress_decile"].value_counts().sort_index())

    print(f"\nBWS weighted stats:")
    print(result["bws_weighted"].describe())

    print(f"\nTop 15 most water-stressed counties:")
    top = result.nlargest(15, "bws_weighted")
    for _, row in top.iterrows():
        print(f"  {row['fips']} {row['NAME']}: bws_weighted={row['bws_weighted']:.4f}, decile={row['water_stress_decile']}")

    print(f"\nBottom 10 least stressed counties:")
    bot = result.nsmallest(10, "bws_weighted")
    for _, row in bot.iterrows():
        print(f"  {row['fips']} {row['NAME']}: bws_weighted={row['bws_weighted']:.4f}, decile={row['water_stress_decile']}")

    # Save
    output = result[["fips", "water_stress_decile"]].sort_values("fips")
    output.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(output)} counties to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
