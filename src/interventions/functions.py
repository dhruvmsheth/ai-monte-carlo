"""Intervention functions: tax benefit (exponential decay) and employment benefit (bell curve).

These modify a county's approval probability based on its current saturation count.
Only active in firm-borne consent scenarios (s4, s5).
"""

from __future__ import annotations

import math


def tax_benefit_delta(
    n: int,
    A: float = 0.20,
    lambda_: float = 0.25,
) -> float:
    """Compute tax-benefit approval boost: Δp = A × exp(−λ × n).

    First facilities bring big fiscal boost to the county; the effect decays
    exponentially as the county saturates.

    Parameters
    ----------
    n : Current number of facilities in the county (saturation count).
    A : Maximum approval boost at n=0.
    lambda_ : Exponential decay rate.

    Returns
    -------
    Δp — the additive boost to approval probability.
    """
    return A * math.exp(-lambda_ * n)


def employment_benefit_delta(
    n: int,
    L: float = 0.15,
    n0: int = 10,
) -> float:
    """Compute employment-benefit approval boost: Δp = L × (n/n₀) × exp(1 − n/n₀).

    Bell-shaped curve that rises with initial facilities, peaks at n=n₀, then
    *declines* as the local labor pool is exhausted and community fatigue sets in.
    This is NOT sigmoid — the decline is the key insight.

    Parameters
    ----------
    n : Current number of facilities in the county.
    L : Peak approval boost (at n=n₀).
    n0 : Saturation count at which employment benefit peaks.

    Returns
    -------
    Δp — the additive boost to approval probability.
    """
    if n0 <= 0:
        return 0.0
    if n == 0:
        return 0.0
    ratio = n / n0
    return L * ratio * math.exp(1.0 - ratio)


def combined_intervention_delta(
    n: int,
    tax_A: float = 0.20,
    tax_lambda: float = 0.25,
    emp_L: float = 0.15,
    emp_n0: int = 10,
    tax_enabled: bool = True,
    emp_enabled: bool = True,
) -> float:
    """Compute total intervention Δp from both tax and employment benefits.

    Parameters
    ----------
    n : Current saturation count.
    tax_A, tax_lambda : Tax benefit parameters.
    emp_L, emp_n0 : Employment benefit parameters.
    tax_enabled, emp_enabled : Whether each intervention is active.

    Returns
    -------
    Total Δp (sum of both interventions, or whichever are enabled).
    """
    delta = 0.0
    if tax_enabled:
        delta += tax_benefit_delta(n, A=tax_A, lambda_=tax_lambda)
    if emp_enabled:
        delta += employment_benefit_delta(n, L=emp_L, n0=emp_n0)
    return delta


def compute_intervention_cost(
    mw: float,
    tax_A: float = 0.20,
    tax_lambda: float = 0.25,
    emp_L: float = 0.15,
    emp_n0: int = 10,
    cost_per_gw_million: float = 405.8,
    construction_jobs_per_gw: int = 45367,
    permanent_jobs_per_gw: int = 5322,
    n: int = 0,
) -> float:
    """Estimate the firm's consent investment cost for a facility.

    Combines annual tax revenue forgone (community benefit) with employment
    program costs, scaled by the facility's MW capacity.

    Parameters
    ----------
    mw : Facility capacity in MW.
    n : Current saturation count (affects intervention effectiveness).
    Other params : From config.

    Returns
    -------
    Cost in $M.
    """
    gw = mw / 1000.0
    # Tax component: scaled by how much the tax intervention boosts approval
    tax_delta = tax_benefit_delta(n, A=tax_A, lambda_=tax_lambda)
    tax_cost = gw * cost_per_gw_million * (tax_delta / max(tax_A, 1e-9))

    # Employment component: proportional to jobs created
    emp_delta = employment_benefit_delta(n, L=emp_L, n0=emp_n0)
    total_jobs = gw * (construction_jobs_per_gw + permanent_jobs_per_gw)
    # Rough cost: $100K per job-year equivalent, scaled by intervention effectiveness
    emp_cost = total_jobs * 0.1 * (emp_delta / max(emp_L, 1e-9))

    return tax_cost + emp_cost
