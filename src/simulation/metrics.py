"""Simulation metrics: Gini coefficient, community surplus, firm cost."""

from __future__ import annotations

import numpy as np


def gini_coefficient(counts: np.ndarray | list[int]) -> float:
    """Compute Gini coefficient of geographic concentration.

    Parameters
    ----------
    counts : Array of build counts per county (including zeros).

    Returns
    -------
    Gini coefficient in [0, 1]. 0 = perfectly even, 1 = all in one county.
    Returns 0.0 for empty or all-zero input.
    """
    arr = np.asarray(counts, dtype=float)
    if arr.size == 0 or arr.sum() == 0:
        return 0.0
    # Mean absolute difference formula
    n = arr.size
    arr_sorted = np.sort(arr)
    index = np.arange(1, n + 1)
    return float((2.0 * np.sum(index * arr_sorted) / (n * np.sum(arr_sorted))) - (n + 1) / n)


def community_surplus(
    total_mw_built: float,
    cost_per_gw_million: float = 405.8,
    construction_jobs_per_gw: int = 45367,
    permanent_jobs_per_gw: int = 5322,
) -> dict[str, float]:
    """Compute community economic benefit from built facilities.

    Parameters
    ----------
    total_mw_built : Total MW of facilities built across all counties.
    cost_per_gw_million : Annual tax revenue per GW ($M).
    construction_jobs_per_gw : Construction jobs per GW.
    permanent_jobs_per_gw : Permanent jobs per GW.

    Returns
    -------
    Dict with tax_revenue_annual_m, construction_jobs, permanent_jobs, total_surplus_m.
    """
    gw = total_mw_built / 1000.0
    tax_revenue = gw * cost_per_gw_million
    construction = gw * construction_jobs_per_gw
    permanent = gw * permanent_jobs_per_gw
    # Total surplus = annual tax + 10-year NPV of employment (rough: $100K/job-year, discounted)
    employment_value = (construction * 0.05 + permanent * 0.1) * 10  # simplified 10yr value in $M
    return {
        "tax_revenue_annual_m": tax_revenue,
        "construction_jobs": construction,
        "permanent_jobs": permanent,
        "total_surplus_m": tax_revenue + employment_value,
    }


def aggregate_draw_results(
    draw_results: list[dict],
) -> dict[str, dict[str, float]]:
    """Aggregate per-draw summary metrics across all draws.

    Parameters
    ----------
    draw_results : List of dicts, each containing scalar metrics from one draw.
        Expected keys: total_built, cumulative_gw, gini_coefficient,
        community_surplus_m, firm_cost_m, infeasible_rate.

    Returns
    -------
    Dict of metric_name → {mean, median, p2_5, p97_5, std}.
    """
    if not draw_results:
        return {}

    metrics_keys = draw_results[0].keys()
    agg: dict[str, dict[str, float]] = {}

    for key in metrics_keys:
        values = np.array([d[key] for d in draw_results], dtype=float)
        agg[key] = {
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "p2_5": float(np.percentile(values, 2.5)),
            "p97_5": float(np.percentile(values, 97.5)),
            "std": float(np.std(values)),
        }

    return agg
