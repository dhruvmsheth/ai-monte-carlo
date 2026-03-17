#!/usr/bin/env python3
"""Preprocess simulation data into compact JSON for the interactive website.

Reads from:
  - outputs/simulation/s*/monthly_time_series.csv
  - outputs/simulation/comparative_summary.json
  - data/processed/all_county_approval_probs.csv
  - data/external/counties_geojson.json
  - outputs/simulation/s*/draw_summaries.csv
  - outputs/simulation/s*/county_builds_by_month.csv

Writes to:
  - website/data/timeseries.json     (combined monthly time series, all scenarios)
  - website/data/summary.json        (comparative summary + scenario metadata)
  - website/data/counties.json       (FIPS, lon, lat, approval_prob for map)
  - website/data/distributions.json  (histogram data for Monte Carlo distributions)
  - website/data/county_builds.json  (mean cumulative builds per county per scenario)
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
OUTPUTS = PROJECT / "outputs" / "simulation"
DATA = PROJECT / "data" / "processed"
EXTERNAL = PROJECT / "data" / "external"
DEST = PROJECT / "website" / "data"

SCENARIOS = ["s1", "s2", "s3", "s4", "s5"]
SCENARIO_META = {
    "s1": {"name": "Laissez-Faire", "threshold": None, "firm_borne": False,
            "desc": "No consent required. Firms build wherever they want."},
    "s2": {"name": "Majority (50%)", "threshold": 0.50, "firm_borne": False,
            "desc": "Community must have >50% approval. Firms don't invest in consent."},
    "s3": {"name": "Supermajority (75%)", "threshold": 0.75, "firm_borne": False,
            "desc": "Community must have >75% approval. Firms don't invest in consent."},
    "s4": {"name": "Firm Consent (50%)", "threshold": 0.50, "firm_borne": True,
            "desc": "50% threshold, but firms invest in tax benefits and jobs to win consent."},
    "s5": {"name": "Firm Consent (75%)", "threshold": 0.75, "firm_borne": True,
            "desc": "75% threshold with firm investment. The hardest bar to clear."},
}


def build_timeseries() -> dict:
    """Combine monthly time series from all scenarios."""
    result = {}
    for sid in SCENARIOS:
        path = OUTPUTS / sid / "monthly_time_series.csv"
        rows = []
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "month": int(row["month"]),
                    "year": int(row["year"]),
                    "cal": int(row["calendar_month"]),
                    "built": round(float(row["mean_total_built"]), 2),
                    "built_lo": round(float(row["p2_5_total_built"]), 2),
                    "built_hi": round(float(row["p97_5_total_built"]), 2),
                    "gw": round(float(row["mean_cumulative_gw"]), 2),
                    "gw_lo": round(float(row["p2_5_cumulative_gw"]), 2),
                    "gw_hi": round(float(row["p97_5_cumulative_gw"]), 2),
                    "gini": round(float(row["mean_gini"]), 4),
                    "firm_cost": round(float(row["mean_firm_cost_m"]), 2),
                })
        result[sid] = rows
    return result


def build_summary() -> dict:
    """Load comparative summary + add scenario metadata."""
    path = OUTPUTS / "comparative_summary.json"
    with open(path) as f:
        data = json.load(f)
    # Also read per-scenario aggregate.json (may be more up-to-date)
    for sid in SCENARIOS:
        agg_path = OUTPUTS / sid / "aggregate.json"
        if agg_path.exists():
            with open(agg_path) as f:
                agg = json.load(f)
            data[sid] = agg
    # Add metadata
    for sid, meta in SCENARIO_META.items():
        if sid in data:
            data[sid]["meta"] = meta
    return data


def build_counties() -> list[dict]:
    """Extract county centroids from GeoJSON + merge with approval probs."""
    # Load GeoJSON centroids
    geojson_path = EXTERNAL / "counties_geojson.json"
    with open(geojson_path) as f:
        geojson = json.load(f)

    centroids: dict[str, tuple[float, float]] = {}
    for feat in geojson["features"]:
        fips = feat["id"]
        geom = feat["geometry"]
        coords = geom["coordinates"]
        pts: list[list[float]] = []
        if geom["type"] == "Polygon":
            for ring in coords:
                pts.extend(ring)
        elif geom["type"] == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    pts.extend(ring)
        if pts:
            arr = np.array(pts)
            centroids[fips] = (round(float(arr[:, 0].mean()), 4),
                               round(float(arr[:, 1].mean()), 4))

    # Load approval probs
    probs: dict[str, float] = {}
    prob_path = DATA / "all_county_approval_probs.csv"
    with open(prob_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            probs[row["fips"]] = round(float(row["approval_prob"]), 4)

    # Merge: only include counties in continental US with centroids
    counties = []
    for fips, (lon, lat) in centroids.items():
        if lon < -130 or lon > -60 or lat < 23 or lat > 50:
            continue  # Skip Alaska, Hawaii, territories for map simplicity
        counties.append({
            "f": fips,
            "x": lon,
            "y": lat,
            "p": probs.get(fips, 0.44),  # Default to national median
        })

    return counties


def build_distributions() -> dict:
    """Create histogram data from draw summaries."""
    result = {}
    for sid in SCENARIOS:
        path = OUTPUTS / sid / "draw_summaries.csv"
        vals = {"built": [], "gini": [], "surplus": [], "cost": []}
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                vals["built"].append(float(row["total_built"]))
                vals["gini"].append(float(row["gini_coefficient"]))
                vals["surplus"].append(float(row["community_surplus_m"]))
                vals["cost"].append(float(row["firm_cost_m"]))
        result[sid] = {}
        for key, v in vals.items():
            result[sid][key] = _histogram(v, 40)
    return result


def _histogram(values: list[float], n_bins: int) -> dict:
    mn, mx = min(values), max(values)
    if mn == mx:
        return {"bins": [round(mn, 2)], "counts": [len(values)], "mean": round(mn, 2)}
    width = (mx - mn) / n_bins
    bins = [round(mn + i * width, 2) for i in range(n_bins + 1)]
    counts = [0] * n_bins
    for v in values:
        idx = min(int((v - mn) / width), n_bins - 1)
        counts[idx] += 1
    return {"bins": bins, "counts": counts, "mean": round(np.mean(values), 2)}


def build_county_builds() -> dict:
    """Aggregate county builds across draws for map animation.

    For each scenario, produces a dict of 6-month snapshots:
      { "6": { fips: cumulative_mean_builds, ... }, "12": {...}, ... }
    Only includes counties with > 0 builds.
    """
    result = {}
    for sid in SCENARIOS:
        path = OUTPUTS / sid / "county_builds_by_month.csv"
        print(f"  Processing {sid} county builds...")

        # Accumulate: (fips, month) -> list of build counts across draws
        monthly_builds: dict[tuple[str, int], list[float]] = defaultdict(list)
        draw_months: dict[int, set] = defaultdict(set)

        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                draw_id = int(row["draw_id"])
                month = int(row["month"])
                fips = row["fips"]
                count = int(row["builds"])
                monthly_builds[(fips, month)].append(count)
                draw_months[draw_id].add(month)

        n_draws = len(draw_months)

        # Compute mean builds per county per month
        mean_monthly: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        for (fips, month), counts in monthly_builds.items():
            mean_monthly[fips][month] = sum(counts) / n_draws

        # Create cumulative snapshots at 6-month intervals
        snapshots = {}
        for target_month in range(6, 121, 6):
            snap = {}
            for fips, month_data in mean_monthly.items():
                cumulative = sum(v for m, v in month_data.items() if m <= target_month)
                if cumulative > 0.05:
                    snap[fips] = round(cumulative, 2)
            snapshots[str(target_month)] = snap

        result[sid] = snapshots
    return result


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)

    print("Building time series...")
    ts = build_timeseries()
    with open(DEST / "timeseries.json", "w") as f:
        json.dump(ts, f, separators=(",", ":"))
    print(f"  -> timeseries.json ({(DEST / 'timeseries.json').stat().st_size // 1024}KB)")

    print("Building summary...")
    summary = build_summary()
    with open(DEST / "summary.json", "w") as f:
        json.dump(summary, f, separators=(",", ":"))
    print(f"  -> summary.json ({(DEST / 'summary.json').stat().st_size // 1024}KB)")

    print("Building county data...")
    counties = build_counties()
    with open(DEST / "counties.json", "w") as f:
        json.dump(counties, f, separators=(",", ":"))
    print(f"  -> counties.json ({len(counties)} counties, "
          f"{(DEST / 'counties.json').stat().st_size // 1024}KB)")

    print("Building distributions...")
    dist = build_distributions()
    with open(DEST / "distributions.json", "w") as f:
        json.dump(dist, f, separators=(",", ":"))
    print(f"  -> distributions.json ({(DEST / 'distributions.json').stat().st_size // 1024}KB)")

    print("Building county builds...")
    county_builds = build_county_builds()
    with open(DEST / "county_builds.json", "w") as f:
        json.dump(county_builds, f, separators=(",", ":"))
    print(f"  -> county_builds.json ({(DEST / 'county_builds.json').stat().st_size // 1024}KB)")

    print("\nDone! All website data files written to website/data/")


if __name__ == "__main__":
    main()
