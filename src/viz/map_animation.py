"""Animated map GIF: US counties colored by approval probability + build overlay."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.config import SimConfig
from src.simulation.candidate import generate_candidates

GEOJSON_URL = (
    "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_GEOJSON_CACHE = _PROJECT_ROOT / "data" / "external" / "counties_geojson.json"

SCENARIO_LABELS: dict[str, str] = {
    "s1": "S1 — Laissez-faire (no threshold)",
    "s2": "S2 — Majority consent (50%)",
    "s3": "S3 — Supermajority consent (75%)",
    "s4": "S4 — Firm-borne consent (50%)",
    "s5": "S5 — Firm-borne consent (75%)",
}

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


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


def run_showcase_draw(
    cfg: SimConfig,
    approval_probs: dict[str, float],
    state_shares_df: pd.DataFrame,
    state_county_map: dict[str, list[str]],
    initial_saturation: dict[str, int] | None = None,
    county_weights: dict[str, float] | None = None,
) -> list[dict]:
    """Run one detailed simulation draw, recording per-month county builds.

    Uses the main engine's _try_approve for consistency with MC draws.

    Returns a list of 120 monthly snapshots, each a dict with:
        month, year, calendar_month, county_builds, total_built, cumulative_gw
    """
    from src.simulation.engine import _try_approve

    rng = np.random.default_rng(cfg.simulation.seed)

    sim_cfg = cfg.simulation
    geo_sub_prob = sim_cfg.geographic_substitution_prob

    saturation: dict[str, int] = dict(initial_saturation) if initial_saturation else {}
    county_builds: dict[str, int] = {}
    total_built = 0
    cumulative_gw = 0.0
    snapshots = []

    for step in range(sim_cfg.n_steps):
        cal_month = ((sim_cfg.start_month - 1 + step) % 12) + 1
        cal_year = sim_cfg.start_year + (sim_cfg.start_month - 1 + step) // 12

        candidates = generate_candidates(
            rng=rng,
            state_shares=state_shares_df,
            state_county_map=state_county_map,
            monthly_gw=sim_cfg.monthly_gw_addition,
            avg_project_mw=cfg.candidate_queue.avg_project_mw,
            pipeline_dropout_rate=cfg.candidate_queue.pipeline_dropout_rate,
            county_weights=county_weights,
        )

        for cand in candidates:
            fips = cand.county_fips
            built, _ = _try_approve(fips, cand.mw, rng, approval_probs, saturation, cfg)

            # Geographic substitution
            if not built and geo_sub_prob > 0 and rng.random() < geo_sub_prob:
                same_state = state_county_map.get(cand.state, [])
                alternatives = [c for c in same_state if c != fips]
                if alternatives:
                    if county_weights is not None:
                        w = np.array([county_weights.get(c, 1.0) for c in alternatives])
                        w = w / w.sum()
                        alt_fips = rng.choice(alternatives, p=w)
                    else:
                        alt_fips = rng.choice(alternatives)
                    built, _ = _try_approve(
                        alt_fips, cand.mw, rng, approval_probs, saturation, cfg,
                    )
                    if built:
                        fips = alt_fips

            if built:
                saturation[fips] = saturation.get(fips, 0) + 1
                county_builds[fips] = county_builds.get(fips, 0) + 1
                total_built += 1
                cumulative_gw += cand.mw / 1000.0

        snapshots.append({
            "month": step + 1,
            "year": cal_year,
            "calendar_month": cal_month,
            "county_builds": dict(county_builds),
            "total_built": total_built,
            "cumulative_gw": cumulative_gw,
        })

    return snapshots


def render_frame(
    geojson: dict,
    all_probs_df: pd.DataFrame,
    county_builds: dict[str, int],
    scenario_label: str,
    time_label: str,
    stats_label: str,
    max_builds: int,
) -> go.Figure:
    """Render one map frame: all counties by approval prob, builds overlaid.

    all_probs_df must have columns: fips, approval_prob
    """
    df = all_probs_df.copy()
    df["builds"] = df["fips"].map(county_builds).fillna(0).astype(int)
    df["has_builds"] = (df["builds"] > 0).astype(int)

    # Color = approval probability for all counties
    # Opacity boost for counties with builds
    fig = go.Figure()

    # Layer 1: all counties colored by approval probability
    fig.add_trace(go.Choropleth(
        geojson=geojson,
        locations=df["fips"],
        z=df["approval_prob"],
        colorscale=[
            [0.0, "#67000d"],
            [0.15, "#d32f2f"],
            [0.30, "#ef6c00"],
            [0.44, "#fdd835"],
            [0.60, "#8bc34a"],
            [0.80, "#2e7d32"],
            [1.0, "#1b5e20"],
        ],
        zmin=0.05,
        zmax=0.95,
        locationmode="geojson-id",
        marker_line_width=0.2,
        marker_line_color="rgba(80,80,80,0.3)",
        hovertemplate="%{text}<extra></extra>",
        text=[
            f"FIPS: {r.fips}<br>"
            f"Approval: {r.approval_prob:.0%}<br>"
            f"Facilities built: {r.builds}"
            for _, r in df.iterrows()
        ],
        colorbar=dict(
            title=dict(
                text="Approval<br>Probability",
                font=dict(color="white", size=11),
            ),
            tickformat=".0%",
            tickvals=[0.1, 0.25, 0.44, 0.6, 0.8],
            ticktext=["10%", "25%", "44%", "60%", "80%"],
            tickfont=dict(color="white", size=9),
            bgcolor="rgba(0,0,0,0)",
            len=0.5,
            y=0.5,
            x=0.92,
        ),
    ))

    # Layer 2: build markers — circles sized by build count
    built_df = df[df["builds"] > 0].copy()
    if not built_df.empty:
        # We need lat/lon for scatter markers — use FIPS centroid approximation
        # Since we don't have centroids, overlay as a second choropleth with border highlight
        fig.add_trace(go.Choropleth(
            geojson=geojson,
            locations=built_df["fips"],
            z=built_df["builds"],
            colorscale=[
                [0.0, "rgba(255,255,255,0)"],
                [0.01, "rgba(0,229,255,0.4)"],
                [0.2, "rgba(0,229,255,0.6)"],
                [0.5, "rgba(0,176,255,0.7)"],
                [1.0, "rgba(41,98,255,0.85)"],
            ],
            zmin=0,
            zmax=max(max_builds, 1),
            locationmode="geojson-id",
            marker_line_width=1.5,
            marker_line_color="cyan",
            showscale=False,
            hoverinfo="skip",
        ))

    fig.update_layout(
        geo=dict(
            scope="usa",
            bgcolor="#0d1117",
            lakecolor="#0d1117",
            landcolor="#1a1a2e",
            showlakes=True,
            showframe=False,
        ),
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        title=dict(
            text=(
                f"<b>{scenario_label}</b><br>"
                f"<span style='font-size:14px;color:#aaaaaa'>"
                f"{time_label}  ·  {stats_label}</span>"
            ),
            font=dict(color="white", size=18),
            x=0.5,
            xanchor="center",
        ),
        margin=dict(l=10, r=10, t=80, b=10),
        width=1200,
        height=700,
    )

    return fig


def generate_scenario_gif(
    scenario_key: str,
    cfg: SimConfig,
    sim_approval_probs: dict[str, float],
    all_approval_probs_df: pd.DataFrame,
    state_shares_df: pd.DataFrame,
    state_county_map: dict[str, list[str]],
    initial_saturation: dict[str, int],
    output_dir: str | Path = "outputs/animation",
    frame_every_n_months: int = 6,
    gif_duration_ms: int = 300,
    county_weights: dict[str, float] | None = None,
) -> Path:
    """Generate animated GIF for one scenario.

    Parameters
    ----------
    scenario_key : e.g. "s1"
    cfg : Merged scenario config.
    sim_approval_probs : FIPS → prob (for simulation).
    all_approval_probs_df : 3,153 county DataFrame with fips, approval_prob (for map).
    state_shares_df : State shares for candidate generation.
    state_county_map : State → county FIPS list.
    initial_saturation : FIPS → initial saturation count.
    output_dir : Where to save the GIF.
    frame_every_n_months : Render a frame every N months.
    gif_duration_ms : Duration per frame in the GIF.
    county_weights : Optional FIPS → weight for weighted county selection.

    Returns
    -------
    Path to the generated GIF.
    """
    from PIL import Image
    import shutil

    output_dir = Path(output_dir)
    frames_dir = output_dir / f"_{scenario_key}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    geojson = load_geojson()

    scenario_label = SCENARIO_LABELS.get(scenario_key, cfg.scenario.name)

    print(f"  Running showcase draw...")
    snapshots = run_showcase_draw(
        cfg=cfg,
        approval_probs=sim_approval_probs,
        state_shares_df=state_shares_df,
        state_county_map=state_county_map,
        initial_saturation=initial_saturation,
        county_weights=county_weights,
    )

    # Max builds for consistent scale
    final_builds = snapshots[-1]["county_builds"]
    max_builds = max(final_builds.values()) if final_builds else 1
    max_builds = max(max_builds, 3)

    # Select frame indices
    indices = list(range(0, len(snapshots), frame_every_n_months))
    if (len(snapshots) - 1) not in indices:
        indices.append(len(snapshots) - 1)

    print(f"  Rendering {len(indices)} frames...")
    frame_paths = []
    for i, idx in enumerate(indices):
        snap = snapshots[idx]
        month_name = MONTH_NAMES[snap["calendar_month"] - 1]
        time_label = f"{month_name} {snap['year']}"
        stats_label = f"{snap['total_built']} facilities  ·  {snap['cumulative_gw']:.1f} GW"

        fig = render_frame(
            geojson=geojson,
            all_probs_df=all_approval_probs_df,
            county_builds=snap["county_builds"],
            scenario_label=scenario_label,
            time_label=time_label,
            stats_label=stats_label,
            max_builds=max_builds,
        )

        fp = frames_dir / f"frame_{idx:04d}.png"
        fig.write_image(str(fp), scale=2)
        frame_paths.append(fp)

        if (i + 1) % 5 == 0 or i == len(indices) - 1:
            print(f"    Frame {i + 1}/{len(indices)} done")

    # Assemble GIF
    gif_path = output_dir / f"{scenario_key}_evolution.gif"
    frames = [Image.open(fp).convert("RGB") for fp in frame_paths]

    durations = [gif_duration_ms] * len(frames)
    if len(durations) > 1:
        durations[-1] = gif_duration_ms * 5

    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )

    shutil.rmtree(frames_dir)

    size_kb = gif_path.stat().st_size / 1024
    print(f"  Saved: {gif_path} ({len(frames)} frames, {size_kb:.0f} KB)")
    return gif_path
