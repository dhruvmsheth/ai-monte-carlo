"""Simulation engine: monthly step loop with approval sampling and build/reject logic."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog

from src.config import SimConfig
from src.interventions.functions import (
    combined_intervention_delta,
    compute_intervention_cost,
    employment_benefit_delta,
    tax_benefit_delta,
)
from src.model.protocol import p_to_beta_params
from src.simulation.candidate import Candidate, generate_candidates
from src.simulation.metrics import community_surplus, gini_coefficient
from src.simulation.state import SimulationState


@dataclass
class MonthSnapshot:
    """Recorded metrics for a single simulation month."""

    month: int
    year: int
    calendar_month: int
    total_built: int
    cumulative_gw: float
    monthly_built: int
    monthly_rejected: int
    monthly_infeasible: int
    firm_cost_m: float
    gini: float
    county_builds: dict[str, int] = field(default_factory=dict)


@dataclass
class DrawResult:
    """Complete results from a single Monte Carlo draw."""

    draw_id: int
    monthly_snapshots: list[MonthSnapshot] = field(default_factory=list)
    total_built: int = 0
    cumulative_gw: float = 0.0
    gini_coefficient: float = 0.0
    community_surplus_m: float = 0.0
    firm_cost_m: float = 0.0
    total_rejected: int = 0
    total_infeasible: int = 0
    total_candidates: int = 0
    county_builds: dict[str, int] = field(default_factory=dict)

    def summary_dict(self) -> dict[str, float]:
        """Return scalar summary for aggregation across draws."""
        infeasible_rate = (
            self.total_infeasible / self.total_candidates
            if self.total_candidates > 0
            else 0.0
        )
        return {
            "total_built": self.total_built,
            "cumulative_gw": self.cumulative_gw,
            "gini_coefficient": self.gini_coefficient,
            "community_surplus_m": self.community_surplus_m,
            "firm_cost_m": self.firm_cost_m,
            "total_rejected": self.total_rejected,
            "infeasible_rate": infeasible_rate,
        }


def firm_optimize(
    p_base: float,
    n: int,
    threshold: float,
    cfg: SimConfig,
) -> float | None:
    """Find minimum firm cost to push expected approval above threshold.

    Uses a 2-variable LP: scale factors s_tax, s_jobs ∈ [0, 1] controlling
    how much of each intervention the firm invests in.

    minimize    cost_tax × s_tax + cost_jobs × s_jobs
    subject to  p_base + s_tax × Δp_tax(n) + s_jobs × Δp_jobs(n) >= threshold
                0 <= s_tax <= 1,  0 <= s_jobs <= 1

    Parameters
    ----------
    p_base : County's base approval probability.
    n : Current saturation count.
    threshold : Scenario approval threshold.
    cfg : Full simulation config.

    Returns
    -------
    Total cost in $M, or None if infeasible.
    """
    tax_cfg = cfg.interventions.tax_benefit
    emp_cfg = cfg.interventions.employment_benefit

    # Compute max deltas at full investment (s=1)
    delta_tax = tax_benefit_delta(n, A=tax_cfg.A, lambda_=tax_cfg.lambda_)
    delta_emp = employment_benefit_delta(n, L=emp_cfg.L, n0=emp_cfg.n0)

    # Quick check: even with max investment, can we reach threshold?
    max_p = p_base + delta_tax + delta_emp
    if max_p < threshold:
        return None

    # If base already exceeds threshold, no investment needed
    if p_base >= threshold:
        return 0.0

    # Compute cost per unit of each intervention at this n
    mw = cfg.candidate_queue.avg_project_mw
    gw = mw / 1000.0

    # Tax cost at full scale
    tax_cost_full = gw * tax_cfg.cost_per_gw_million * (delta_tax / max(tax_cfg.A, 1e-9))
    # Employment cost at full scale
    total_jobs = gw * (emp_cfg.construction_jobs_per_gw + emp_cfg.permanent_jobs_per_gw)
    emp_cost_full = total_jobs * 0.1 * (delta_emp / max(emp_cfg.L, 1e-9))

    # LP: minimize [tax_cost_full, emp_cost_full] · [s_tax, s_jobs]
    # subject to: delta_tax * s_tax + delta_emp * s_jobs >= threshold - p_base
    # i.e., -delta_tax * s_tax - delta_emp * s_jobs <= -(threshold - p_base)
    gap = threshold - p_base

    c = [tax_cost_full, emp_cost_full]
    A_ub = [[-delta_tax, -delta_emp]]
    b_ub = [-gap]
    bounds = [(0, 1), (0, 1)]

    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

    if result.success:
        return float(result.fun)
    return None


def _try_approve(
    fips: str,
    mw: float,
    rng: np.random.Generator,
    approval_probs: dict[str, float],
    saturation: dict[str, int],
    cfg: SimConfig,
) -> tuple[bool, float]:
    """Try to approve a facility in a given county.

    Returns (built, firm_cost). Does not mutate saturation.
    """
    n = saturation.get(fips, 0)
    p_base = approval_probs.get(fips, 0.44)

    tax_cfg = cfg.interventions.tax_benefit
    emp_cfg = cfg.interventions.employment_benefit
    threshold = cfg.scenario.threshold
    firm_borne = cfg.scenario.firm_borne
    kappa = cfg.approval.beta_concentration

    delta_p = 0.0
    if tax_cfg.enabled:
        delta_p += tax_benefit_delta(n, A=tax_cfg.A, lambda_=tax_cfg.lambda_)
    if emp_cfg.enabled:
        delta_p += employment_benefit_delta(n, L=emp_cfg.L, n0=emp_cfg.n0)

    p_adjusted = float(np.clip(p_base + delta_p, 0.05, 0.95))
    alpha, beta = p_to_beta_params(p_adjusted, kappa)
    approval_draw = rng.beta(alpha, beta)

    if threshold is None:
        return (approval_draw > 0.5, 0.0)
    elif firm_borne:
        cost = firm_optimize(p_base, n, threshold, cfg)
        if cost is not None:
            return (approval_draw > threshold, cost if approval_draw > threshold else 0.0)
        return (False, 0.0)  # infeasible
    else:
        return (approval_draw > threshold, 0.0)


def run_single_draw(
    draw_id: int,
    cfg: SimConfig,
    approval_probs: dict[str, float],
    state_shares_df: "pd.DataFrame",
    state_county_map: dict[str, list[str]],
    initial_saturation: dict[str, int] | None = None,
    county_weights: dict[str, float] | None = None,
) -> DrawResult:
    """Execute one complete Monte Carlo draw (120 months).

    Parameters
    ----------
    draw_id : Draw index (used for deterministic seeding).
    cfg : Merged simulation config.
    approval_probs : Dict of FIPS → base approval probability.
    state_shares_df : State shares DataFrame for candidate generation.
    state_county_map : State → list of county FIPS.
    initial_saturation : Optional initial saturation counts per FIPS.
    county_weights : Optional FIPS → weight for weighted county selection.

    Returns
    -------
    DrawResult with monthly snapshots and summary metrics.
    """
    import pandas as pd

    # Deterministic RNG: draw_seed = master_seed + draw_id
    draw_seed = cfg.simulation.seed + draw_id
    rng = np.random.default_rng(draw_seed)

    sim_cfg = cfg.simulation
    scenario = cfg.scenario
    threshold = scenario.threshold
    firm_borne = scenario.firm_borne

    geo_sub_prob = sim_cfg.geographic_substitution_prob

    # Initialize per-county saturation tracking
    saturation: dict[str, int] = {}
    if initial_saturation:
        saturation.update(initial_saturation)

    result = DrawResult(draw_id=draw_id)
    total_firm_cost = 0.0

    for step in range(sim_cfg.n_steps):
        # Calendar month/year
        cal_month = ((sim_cfg.start_month - 1 + step) % 12) + 1
        cal_year = sim_cfg.start_year + (sim_cfg.start_month - 1 + step) // 12

        # Generate candidates for this month (with pipeline dropout)
        candidates = generate_candidates(
            rng=rng,
            state_shares=state_shares_df,
            state_county_map=state_county_map,
            monthly_gw=sim_cfg.monthly_gw_addition,
            avg_project_mw=cfg.candidate_queue.avg_project_mw,
            pipeline_dropout_rate=cfg.candidate_queue.pipeline_dropout_rate,
            county_weights=county_weights,
        )

        monthly_built = 0
        monthly_rejected = 0
        monthly_infeasible = 0

        for cand in candidates:
            result.total_candidates += 1
            fips = cand.county_fips

            built, cand_firm_cost = _try_approve(
                fips, cand.mw, rng, approval_probs, saturation, cfg,
            )

            # Geographic substitution: if blocked, try another county in same state
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
                    built, cand_firm_cost = _try_approve(
                        alt_fips, cand.mw, rng, approval_probs, saturation, cfg,
                    )
                    if built:
                        fips = alt_fips  # update to the substituted county

            if built:
                n = saturation.get(fips, 0)
                saturation[fips] = n + 1
                result.total_built += 1
                result.cumulative_gw += cand.mw / 1000.0
                result.county_builds[fips] = result.county_builds.get(fips, 0) + 1
                total_firm_cost += cand_firm_cost
                monthly_built += 1
            elif threshold is not None:
                if firm_borne:
                    n = saturation.get(fips, 0)
                    p_base = approval_probs.get(fips, 0.44)
                    cost = firm_optimize(p_base, n, threshold, cfg)
                    if cost is None:
                        monthly_infeasible += 1
                    else:
                        monthly_rejected += 1
                else:
                    monthly_rejected += 1

        # Record month snapshot
        all_county_fips = list(approval_probs.keys())
        build_counts = np.array(
            [result.county_builds.get(f, 0) for f in all_county_fips]
        )

        snapshot = MonthSnapshot(
            month=step + 1,
            year=cal_year,
            calendar_month=cal_month,
            total_built=result.total_built,
            cumulative_gw=result.cumulative_gw,
            monthly_built=monthly_built,
            monthly_rejected=monthly_rejected,
            monthly_infeasible=monthly_infeasible,
            firm_cost_m=total_firm_cost,
            gini=gini_coefficient(build_counts),
            county_builds=dict(result.county_builds),
        )
        result.monthly_snapshots.append(snapshot)

    # Final metrics
    all_county_fips = list(approval_probs.keys())
    final_counts = np.array(
        [result.county_builds.get(f, 0) for f in all_county_fips]
    )
    result.gini_coefficient = gini_coefficient(final_counts)
    result.firm_cost_m = total_firm_cost
    result.total_rejected = sum(s.monthly_rejected for s in result.monthly_snapshots)
    result.total_infeasible = sum(s.monthly_infeasible for s in result.monthly_snapshots)

    # Community surplus
    tax_cfg = cfg.interventions.tax_benefit
    emp_cfg = cfg.interventions.employment_benefit
    surplus = community_surplus(
        total_mw_built=result.cumulative_gw * 1000.0,
        cost_per_gw_million=tax_cfg.cost_per_gw_million,
        construction_jobs_per_gw=emp_cfg.construction_jobs_per_gw,
        permanent_jobs_per_gw=emp_cfg.permanent_jobs_per_gw,
    )
    result.community_surplus_m = surplus["total_surplus_m"]

    return result
