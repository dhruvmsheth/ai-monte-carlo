"""Simulation runner: orchestrate N Monte Carlo draws for a scenario."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from src.config import SimConfig, load_config
from src.simulation.candidate import build_state_county_map, load_state_shares
from src.simulation.engine import DrawResult, run_single_draw
from src.simulation.metrics import aggregate_draw_results

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_APPROVAL_PROBS_PATH = _PROJECT_ROOT / "data" / "processed" / "county_approval_probs.csv"
_ALL_APPROVAL_PROBS_PATH = _PROJECT_ROOT / "data" / "processed" / "all_county_approval_probs.csv"
_FEATURE_MATRIX_PATH = _PROJECT_ROOT / "data" / "processed" / "county_feature_matrix.csv"


@dataclass
class ScenarioResult:
    """Aggregated results from running N draws of a scenario."""

    scenario_name: str
    n_draws: int
    elapsed_seconds: float = 0.0
    draw_results: list[DrawResult] = field(default_factory=list)
    aggregate: dict[str, dict[str, float]] = field(default_factory=dict)
    monthly_time_series: pd.DataFrame | None = None

    def summary_table(self) -> str:
        """Format aggregate results as a readable string."""
        lines = [f"Scenario: {self.scenario_name} ({self.n_draws} draws)"]
        lines.append(f"Elapsed: {self.elapsed_seconds:.1f}s")
        lines.append("-" * 60)
        for metric, stats in self.aggregate.items():
            lines.append(
                f"  {metric:25s}  mean={stats['mean']:10.2f}  "
                f"median={stats['median']:10.2f}  "
                f"95%CI=[{stats['p2_5']:.2f}, {stats['p97_5']:.2f}]"
            )
        return "\n".join(lines)


def load_approval_probs(
    path: str | Path | None = None,
    use_all_counties: bool = True,
) -> dict[str, float]:
    """Load county approval probabilities as a FIPS → prob dict.

    Parameters
    ----------
    path : Path to CSV. Uses default if None.
    use_all_counties : If True, load all 3,153 US counties (default).
        If False, load only 232 FracTracker counties.

    Returns
    -------
    Dict mapping FIPS code → calibrated approval probability.
    """
    if path is not None:
        p = Path(path)
    elif use_all_counties and _ALL_APPROVAL_PROBS_PATH.exists():
        p = _ALL_APPROVAL_PROBS_PATH
    else:
        p = _APPROVAL_PROBS_PATH
    df = pd.read_csv(p, dtype={"fips": str})
    return dict(zip(df["fips"], df["approval_prob"]))


def load_initial_saturation(feature_matrix_path: str | Path | None = None) -> dict[str, int]:
    """Load initial saturation counts from the feature matrix.

    These represent existing facilities in each county at simulation start.

    Parameters
    ----------
    feature_matrix_path : Path to county_feature_matrix.csv.

    Returns
    -------
    Dict mapping FIPS → initial saturation count.
    """
    p = Path(feature_matrix_path) if feature_matrix_path else _FEATURE_MATRIX_PATH
    df = pd.read_csv(p, dtype={"fips": str})
    if "saturation_count" in df.columns:
        return dict(zip(df["fips"], df["saturation_count"].fillna(0).astype(int)))
    return {}


def build_monthly_time_series(draw_results: list[DrawResult]) -> pd.DataFrame:
    """Build a DataFrame of monthly metrics averaged across draws.

    Returns DataFrame with columns: month, year, calendar_month,
    mean_total_built, mean_cumulative_gw, mean_gini, mean_firm_cost_m,
    plus p2_5/p97_5 bands for total_built and cumulative_gw.
    """
    if not draw_results or not draw_results[0].monthly_snapshots:
        return pd.DataFrame()

    n_months = len(draw_results[0].monthly_snapshots)
    n_draws = len(draw_results)

    records = []
    for m in range(n_months):
        built_arr = np.array([dr.monthly_snapshots[m].total_built for dr in draw_results])
        gw_arr = np.array([dr.monthly_snapshots[m].cumulative_gw for dr in draw_results])
        gini_arr = np.array([dr.monthly_snapshots[m].gini for dr in draw_results])
        cost_arr = np.array([dr.monthly_snapshots[m].firm_cost_m for dr in draw_results])

        snap = draw_results[0].monthly_snapshots[m]
        records.append({
            "month": snap.month,
            "year": snap.year,
            "calendar_month": snap.calendar_month,
            "mean_total_built": float(np.mean(built_arr)),
            "p2_5_total_built": float(np.percentile(built_arr, 2.5)),
            "p97_5_total_built": float(np.percentile(built_arr, 97.5)),
            "mean_cumulative_gw": float(np.mean(gw_arr)),
            "p2_5_cumulative_gw": float(np.percentile(gw_arr, 2.5)),
            "p97_5_cumulative_gw": float(np.percentile(gw_arr, 97.5)),
            "mean_gini": float(np.mean(gini_arr)),
            "mean_firm_cost_m": float(np.mean(cost_arr)),
        })

    return pd.DataFrame(records)


def run_scenario(
    cfg: SimConfig,
    approval_probs: dict[str, float] | None = None,
    state_shares_df: pd.DataFrame | None = None,
    feature_matrix: pd.DataFrame | None = None,
    n_draws: int | None = None,
    progress_interval: int = 100,
    on_draw_complete: Callable[[int, int, "DrawResult"], None] | None = None,
) -> ScenarioResult:
    """Run N Monte Carlo draws for a single scenario.

    Parameters
    ----------
    cfg : Merged scenario config.
    approval_probs : FIPS → prob dict. Loaded from default path if None.
    state_shares_df : State shares DataFrame. Loaded from default path if None.
    feature_matrix : Feature matrix DataFrame for state-county mapping.
    n_draws : Override for cfg.simulation.n_draws.
    progress_interval : Print progress every N draws (0 to disable).
    on_draw_complete : Optional callback(draw_idx, total_draws, draw_result).

    Returns
    -------
    ScenarioResult with per-draw results and aggregate statistics.
    """
    # Load data if not provided
    if approval_probs is None:
        approval_probs = load_approval_probs()
    if state_shares_df is None:
        state_shares_df = load_state_shares()
    if feature_matrix is None:
        feature_matrix = pd.read_csv(_FEATURE_MATRIX_PATH, dtype={"fips": str})

    state_county_map = build_state_county_map(
        pd.DataFrame({"fips": list(approval_probs.keys())}),
        feature_matrix,
    )

    initial_saturation = {}
    if "saturation_count" in feature_matrix.columns:
        initial_saturation = dict(
            zip(
                feature_matrix["fips"],
                feature_matrix["saturation_count"].fillna(0).astype(int),
            )
        )

    # Build county weights: existing facility counties get higher selection weight
    existing_weight = cfg.candidate_queue.existing_facility_weight
    existing_fips = set(feature_matrix["fips"].dropna())
    county_weights: dict[str, float] = {}
    for fips in approval_probs:
        county_weights[fips] = existing_weight if fips in existing_fips else 1.0

    draws = n_draws if n_draws is not None else cfg.simulation.n_draws

    result = ScenarioResult(
        scenario_name=cfg.scenario.name,
        n_draws=draws,
    )

    t0 = time.time()

    for i in range(draws):
        draw = run_single_draw(
            draw_id=i,
            cfg=cfg,
            approval_probs=approval_probs,
            state_shares_df=state_shares_df,
            state_county_map=state_county_map,
            initial_saturation=initial_saturation,
            county_weights=county_weights,
        )
        result.draw_results.append(draw)

        if on_draw_complete is not None:
            on_draw_complete(i, draws, draw)

        if progress_interval > 0 and (i + 1) % progress_interval == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            print(f"  Draw {i + 1}/{draws} ({rate:.1f} draws/s, {elapsed:.1f}s elapsed)")

    result.elapsed_seconds = time.time() - t0

    # Aggregate
    summaries = [dr.summary_dict() for dr in result.draw_results]
    result.aggregate = aggregate_draw_results(summaries)
    result.monthly_time_series = build_monthly_time_series(result.draw_results)

    return result
