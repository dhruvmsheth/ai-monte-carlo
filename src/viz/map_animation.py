"""Map visualization helpers for GIF rendering.

Provides centroid extraction, spatial clustering, and frame rendering
for the animated data center growth maps. Does NOT run simulations —
all data comes from saved MC results.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

GEOJSON_URL = (
    "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_GEOJSON_CACHE = _PROJECT_ROOT / "data" / "external" / "counties_geojson.json"

SCENARIO_LABELS: dict[str, str] = {
    "s1": "S1 \u2014 Laissez-faire (no threshold)",
    "s2": "S2 \u2014 Majority consent (50%)",
    "s3": "S3 \u2014 Supermajority consent (75%)",
    "s4": "S4 \u2014 Firm-borne consent (50%)",
    "s5": "S5 \u2014 Firm-borne consent (75%)",
}

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

BG_COLOR = "#0d1117"
APPROVAL_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "approval",
    ["#67000d", "#d32f2f", "#ef6c00", "#fdd835", "#8bc34a", "#2e7d32", "#1b5e20"],
    N=256,
)
BUILD_COLOR = "#00e5ff"


def load_geojson() -> dict:
    """Load county GeoJSON, caching locally after first download."""
    if _GEOJSON_CACHE.exists():
        with open(_GEOJSON_CACHE) as f:
            return json.load(f)
    print("  Downloading county boundaries (one-time)...")
    with urlopen(GEOJSON_URL) as response:
        data = json.load(response)
    _GEOJSON_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(_GEOJSON_CACHE, "w") as f:
        json.dump(data, f)
    return data


def extract_centroids(geojson: dict) -> dict[str, tuple[float, float]]:
    """Extract (lon, lat) centroids from GeoJSON features."""
    centroids = {}
    for feat in geojson["features"]:
        fips = feat["id"]
        geom = feat["geometry"]
        coords = geom["coordinates"]
        all_pts: list[list[float]] = []
        if geom["type"] == "Polygon":
            for ring in coords:
                all_pts.extend(ring)
        elif geom["type"] == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    all_pts.extend(ring)
        if all_pts:
            arr = np.array(all_pts)
            centroids[fips] = (float(arr[:, 0].mean()), float(arr[:, 1].mean()))
    return centroids


def cluster_builds(
    county_builds: dict[str, float],
    centroids: dict[str, tuple[float, float]],
    distance_threshold: float = 0.8,
) -> list[dict]:
    """Cluster nearby built counties into single circles.

    Parameters
    ----------
    county_builds : FIPS -> build count (can be fractional for means).
    centroids : FIPS -> (lon, lat).
    distance_threshold : Max distance in degrees to merge (~50 miles).

    Returns
    -------
    List of dicts with keys: lon, lat, total_builds.
    """
    fips_list = [f for f in county_builds if f in centroids and county_builds[f] > 0.01]
    if not fips_list:
        return []

    if len(fips_list) == 1:
        f = fips_list[0]
        lon, lat = centroids[f]
        return [{"lon": lon, "lat": lat, "total_builds": county_builds[f]}]

    coords = np.array([centroids[f] for f in fips_list])
    builds = np.array([county_builds[f] for f in fips_list])

    Z = linkage(coords, method="average")
    labels = fcluster(Z, t=distance_threshold, criterion="distance")

    clusters = []
    for cid in np.unique(labels):
        mask = labels == cid
        cluster_total = builds[mask].sum()
        w = builds[mask] / builds[mask].sum()
        clon = (coords[mask, 0] * w).sum()
        clat = (coords[mask, 1] * w).sum()
        clusters.append({
            "lon": float(clon),
            "lat": float(clat),
            "total_builds": float(cluster_total),
        })

    return clusters


def render_frame(
    ax: plt.Axes,
    centroids: dict[str, tuple[float, float]],
    all_probs: dict[str, float],
    clusters: list[dict],
    scenario_label: str,
    time_label: str,
    stats_label: str,
    max_builds: float,
) -> None:
    """Render one map frame onto the given axes.

    - All county centroids colored by approval probability (low opacity background)
    - Clustered build circles (cyan, high opacity, sized by total build count)
    """
    ax.clear()
    ax.set_facecolor(BG_COLOR)

    # Background: all county centroids colored by approval probability
    bg_lons, bg_lats, bg_probs = [], [], []
    for fips, (lon, lat) in centroids.items():
        bg_lons.append(lon)
        bg_lats.append(lat)
        bg_probs.append(all_probs.get(fips, 0.44))
    ax.scatter(
        bg_lons, bg_lats,
        s=3, c=bg_probs, cmap=APPROVAL_CMAP,
        vmin=0.05, vmax=0.95,
        alpha=0.5, linewidths=0,
    )

    # Build circles: clustered, cyan, sized by total builds
    if clusters:
        c_lons = [c["lon"] for c in clusters]
        c_lats = [c["lat"] for c in clusters]
        c_builds = np.array([c["total_builds"] for c in clusters])
        sizes = 25 + 200 * np.sqrt(c_builds / max(max_builds, 1))
        ax.scatter(
            c_lons, c_lats,
            s=sizes,
            c=BUILD_COLOR,
            alpha=0.85,
            edgecolors="white",
            linewidths=0.4,
            zorder=10,
        )

    ax.set_xlim(-128, -65)
    ax.set_ylim(24, 50)
    ax.set_aspect(1.3)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.set_title(
        f"{scenario_label}\n{time_label}  \u00b7  {stats_label}",
        fontsize=14,
        fontweight="bold",
        color="white",
        pad=10,
    )
