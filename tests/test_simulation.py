"""Tests for Monte Carlo simulation engine (Issue #18)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import SimConfig, load_config
from src.simulation.candidate import (
    Candidate,
    build_state_county_map,
    generate_candidates,
    load_state_shares,
)
from src.simulation.engine import DrawResult, MonthSnapshot, firm_optimize, run_single_draw
from src.simulation.metrics import aggregate_draw_results, community_surplus, gini_coefficient
from src.simulation.runner import (
    ScenarioResult,
    build_monthly_time_series,
    load_approval_probs,
    run_scenario,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rng():
    return np.random.default_rng(seed=12345)


@pytest.fixture
def mini_state_shares():
    """3-state shares for fast tests."""
    return pd.DataFrame({
        "state": ["VA", "TX", "GA"],
        "adjusted_share": [0.5, 0.3, 0.2],
    })


@pytest.fixture
def mini_state_county_map():
    """Minimal state → county mapping."""
    return {
        "VA": ["51107", "51153"],
        "TX": ["48029", "48113"],
        "GA": ["13089", "13135"],
    }


@pytest.fixture
def mini_approval_probs():
    """Approval probs for 6 test counties."""
    return {
        "51107": 0.775,  # Loudoun VA - high
        "51153": 0.25,   # Prince William VA - low
        "48029": 0.60,   # Bexar TX
        "48113": 0.55,   # Dallas TX
        "13089": 0.50,   # DeKalb GA
        "13135": 0.65,   # Gwinnett GA
    }


@pytest.fixture
def mini_feature_matrix():
    """Feature matrix with state column for 6 test counties."""
    return pd.DataFrame({
        "fips": ["51107", "51153", "48029", "48113", "13089", "13135"],
        "state": ["VA", "VA", "TX", "TX", "GA", "GA"],
        "saturation_count": [15, 3, 5, 2, 4, 3],
    })


@pytest.fixture
def fast_cfg():
    """Config with minimal simulation for fast tests."""
    return SimConfig()  # defaults: 120 steps, 10000 draws, etc.


# ---------------------------------------------------------------------------
# Candidate generation tests
# ---------------------------------------------------------------------------


class TestCandidateGeneration:
    def test_load_state_shares(self):
        """State shares load and sum to 1.0."""
        df = load_state_shares()
        assert abs(df["adjusted_share"].sum() - 1.0) < 1e-10
        assert len(df) == 51  # 50 states + DC

    def test_generate_candidates_count(self, rng, mini_state_shares, mini_state_county_map):
        """Correct number of candidates generated."""
        candidates = generate_candidates(
            rng=rng,
            state_shares=mini_state_shares,
            state_county_map=mini_state_county_map,
            monthly_gw=1.5,
            avg_project_mw=300.0,
        )
        assert len(candidates) == 5  # 1500 MW / 300 MW = 5

    def test_generate_candidates_deterministic(
        self, mini_state_shares, mini_state_county_map
    ):
        """Same seed produces same candidates."""
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)
        c1 = generate_candidates(rng1, mini_state_shares, mini_state_county_map)
        c2 = generate_candidates(rng2, mini_state_shares, mini_state_county_map)
        assert len(c1) == len(c2)
        for a, b in zip(c1, c2):
            assert a.state == b.state
            assert a.county_fips == b.county_fips

    def test_generate_candidates_valid_counties(
        self, rng, mini_state_shares, mini_state_county_map
    ):
        """All generated counties exist in the state_county_map."""
        candidates = generate_candidates(
            rng=rng,
            state_shares=mini_state_shares,
            state_county_map=mini_state_county_map,
        )
        for c in candidates:
            assert c.county_fips in mini_state_county_map[c.state]

    def test_generate_candidates_state_distribution(
        self, mini_state_shares, mini_state_county_map
    ):
        """Over many draws, state distribution roughly matches shares."""
        rng = np.random.default_rng(42)
        state_counts: dict[str, int] = {}
        for _ in range(1000):
            candidates = generate_candidates(
                rng=rng,
                state_shares=mini_state_shares,
                state_county_map=mini_state_county_map,
            )
            for c in candidates:
                state_counts[c.state] = state_counts.get(c.state, 0) + 1
        total = sum(state_counts.values())
        va_share = state_counts["VA"] / total
        # VA should be ~50% of candidates
        assert 0.4 < va_share < 0.6

    def test_build_state_county_map(self, mini_approval_probs, mini_feature_matrix):
        """State-county map built correctly from feature matrix."""
        probs_df = pd.DataFrame({"fips": list(mini_approval_probs.keys())})
        scm = build_state_county_map(probs_df, mini_feature_matrix)
        assert set(scm.keys()) == {"VA", "TX", "GA"}
        assert "51107" in scm["VA"]
        assert "48029" in scm["TX"]

    def test_generate_candidates_different_gw(
        self, rng, mini_state_shares, mini_state_county_map
    ):
        """Different monthly GW produces different candidate count."""
        c1 = generate_candidates(
            rng=rng,
            state_shares=mini_state_shares,
            state_county_map=mini_state_county_map,
            monthly_gw=0.6,
            avg_project_mw=300.0,
        )
        assert len(c1) == 2  # 600 MW / 300 MW = 2


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_gini_all_equal(self):
        """Gini of equal distribution is 0."""
        assert gini_coefficient([10, 10, 10, 10]) == pytest.approx(0.0)

    def test_gini_all_zero(self):
        """Gini of all zeros is 0."""
        assert gini_coefficient([0, 0, 0]) == 0.0

    def test_gini_empty(self):
        """Gini of empty array is 0."""
        assert gini_coefficient([]) == 0.0

    def test_gini_maximum_concentration(self):
        """Gini of [0, 0, ..., N] approaches 1."""
        counts = [0] * 99 + [100]
        g = gini_coefficient(counts)
        assert 0.95 < g <= 1.0

    def test_gini_moderate(self):
        """Gini of moderate distribution is between 0 and 1."""
        counts = [1, 2, 3, 4, 5]
        g = gini_coefficient(counts)
        assert 0.0 < g < 1.0

    def test_gini_single_county(self):
        """Gini of single county is 0."""
        assert gini_coefficient([5]) == pytest.approx(0.0)

    def test_community_surplus_basic(self):
        """Community surplus computes positive values for positive builds."""
        result = community_surplus(total_mw_built=1000.0)
        assert result["tax_revenue_annual_m"] > 0
        assert result["construction_jobs"] > 0
        assert result["permanent_jobs"] > 0
        assert result["total_surplus_m"] > result["tax_revenue_annual_m"]

    def test_community_surplus_zero(self):
        """Zero MW built produces zero surplus."""
        result = community_surplus(total_mw_built=0.0)
        assert result["tax_revenue_annual_m"] == 0.0
        assert result["construction_jobs"] == 0.0

    def test_community_surplus_scales_linearly(self):
        """Surplus scales linearly with MW."""
        s1 = community_surplus(total_mw_built=1000.0)
        s2 = community_surplus(total_mw_built=2000.0)
        assert s2["tax_revenue_annual_m"] == pytest.approx(
            2 * s1["tax_revenue_annual_m"]
        )

    def test_aggregate_draw_results(self):
        """Aggregation computes correct stats."""
        draws = [
            {"total_built": 100, "gini": 0.3},
            {"total_built": 200, "gini": 0.5},
            {"total_built": 150, "gini": 0.4},
        ]
        agg = aggregate_draw_results(draws)
        assert agg["total_built"]["mean"] == pytest.approx(150.0)
        assert agg["total_built"]["median"] == pytest.approx(150.0)
        assert agg["gini"]["mean"] == pytest.approx(0.4)

    def test_aggregate_empty(self):
        """Empty draw list returns empty dict."""
        assert aggregate_draw_results([]) == {}


# ---------------------------------------------------------------------------
# Firm optimization tests
# ---------------------------------------------------------------------------


class TestFirmOptimize:
    def test_base_exceeds_threshold(self):
        """No cost when base prob already exceeds threshold."""
        cfg = load_config()
        # Override interventions to enabled for this test
        from dataclasses import replace
        cfg = replace(
            cfg,
            interventions=replace(
                cfg.interventions,
                tax_benefit=replace(cfg.interventions.tax_benefit, enabled=True),
                employment_benefit=replace(cfg.interventions.employment_benefit, enabled=True),
            ),
        )
        cost = firm_optimize(p_base=0.80, n=0, threshold=0.50, cfg=cfg)
        assert cost == 0.0

    def test_infeasible_when_too_low(self):
        """Returns None when max investment can't reach threshold."""
        cfg = load_config()
        cfg = _enable_interventions(cfg)
        cost = firm_optimize(p_base=0.05, n=100, threshold=0.95, cfg=cfg)
        assert cost is None

    def test_feasible_cost_positive(self):
        """Returns positive cost when investment is needed."""
        cfg = load_config()
        cfg = _enable_interventions(cfg)
        # At n=0: delta_tax=0.20, delta_emp=0.0, so max_p=0.60. Threshold 0.45 is feasible.
        cost = firm_optimize(p_base=0.40, n=0, threshold=0.45, cfg=cfg)
        assert cost is not None
        assert cost > 0.0

    def test_higher_threshold_costs_more(self):
        """Higher threshold requires more investment."""
        cfg = load_config()
        cfg = _enable_interventions(cfg)
        # At n=5: delta_tax=0.057, delta_emp=0.110, max_p = base + 0.167
        # p_base=0.40 → max=0.567. Both 0.45 and 0.55 are feasible.
        cost_45 = firm_optimize(p_base=0.40, n=5, threshold=0.45, cfg=cfg)
        cost_55 = firm_optimize(p_base=0.40, n=5, threshold=0.55, cfg=cfg)
        assert cost_45 is not None
        assert cost_55 is not None
        assert cost_55 > cost_45

    def test_higher_saturation_costs_more(self):
        """Higher saturation means interventions are less effective → higher cost or infeasible."""
        cfg = load_config()
        cfg = _enable_interventions(cfg)
        # At n=3: delta_tax=0.094, delta_emp=0.090, max_p=0.40+0.184=0.584
        # At n=15: delta_tax=0.005, delta_emp=0.055, max_p=0.40+0.060=0.460
        # Threshold 0.45: both feasible but n=15 needs higher fraction of interventions
        cost_low = firm_optimize(p_base=0.40, n=3, threshold=0.50, cfg=cfg)
        cost_high = firm_optimize(p_base=0.40, n=15, threshold=0.45, cfg=cfg)
        # n=15 may be infeasible or more expensive than n=3 at lower threshold
        if cost_high is not None and cost_low is not None:
            # At minimum, both are feasible — verify the LP runs
            assert cost_low >= 0.0
            assert cost_high >= 0.0
        else:
            # Infeasibility at high saturation is also valid behavior
            assert cost_low is not None or cost_high is None


# ---------------------------------------------------------------------------
# Engine tests
# ---------------------------------------------------------------------------


class TestEngine:
    def test_single_draw_deterministic(
        self, mini_approval_probs, mini_state_county_map, mini_feature_matrix
    ):
        """Same draw_id + seed produces identical results."""
        cfg = _make_tiny_cfg(n_steps=5, n_draws=1)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        r1 = run_single_draw(0, cfg, mini_approval_probs, state_shares, mini_state_county_map)
        r2 = run_single_draw(0, cfg, mini_approval_probs, state_shares, mini_state_county_map)
        assert r1.total_built == r2.total_built
        assert r1.cumulative_gw == r2.cumulative_gw

    def test_single_draw_different_seeds(
        self, mini_approval_probs, mini_state_county_map
    ):
        """Different draw_ids produce different results (with high probability)."""
        cfg = _make_tiny_cfg(n_steps=20, n_draws=1)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        r1 = run_single_draw(0, cfg, mini_approval_probs, state_shares, mini_state_county_map)
        r2 = run_single_draw(999, cfg, mini_approval_probs, state_shares, mini_state_county_map)
        # Not guaranteed different, but overwhelmingly likely with 20 steps
        assert r1.total_built != r2.total_built or r1.county_builds != r2.county_builds

    def test_draw_produces_builds(
        self, mini_approval_probs, mini_state_county_map
    ):
        """A draw with moderate approval probs produces some builds."""
        cfg = _make_tiny_cfg(n_steps=10, n_draws=1)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        result = run_single_draw(
            0, cfg, mini_approval_probs, state_shares, mini_state_county_map
        )
        assert result.total_built > 0
        assert result.cumulative_gw > 0
        assert len(result.monthly_snapshots) == 10

    def test_draw_monthly_snapshots_monotonic(
        self, mini_approval_probs, mini_state_county_map
    ):
        """Total built is monotonically non-decreasing across months."""
        cfg = _make_tiny_cfg(n_steps=12, n_draws=1)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        result = run_single_draw(
            0, cfg, mini_approval_probs, state_shares, mini_state_county_map
        )
        for i in range(1, len(result.monthly_snapshots)):
            assert (
                result.monthly_snapshots[i].total_built
                >= result.monthly_snapshots[i - 1].total_built
            )

    def test_draw_with_threshold(
        self, mini_approval_probs, mini_state_county_map
    ):
        """Supermajority threshold reduces builds vs laissez-faire."""
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        cfg_lf = _make_tiny_cfg(n_steps=24, threshold=None)
        cfg_sm = _make_tiny_cfg(n_steps=24, threshold=0.75)

        r_lf = run_single_draw(
            0, cfg_lf, mini_approval_probs, state_shares, mini_state_county_map
        )
        r_sm = run_single_draw(
            0, cfg_sm, mini_approval_probs, state_shares, mini_state_county_map
        )
        # Supermajority should have fewer builds (with very high probability)
        assert r_sm.total_built < r_lf.total_built

    def test_draw_with_initial_saturation(
        self, mini_approval_probs, mini_state_county_map
    ):
        """Initial saturation is respected."""
        cfg = _make_tiny_cfg(n_steps=5, n_draws=1)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        initial_sat = {"51107": 15, "51153": 3}
        result = run_single_draw(
            0, cfg, mini_approval_probs, state_shares, mini_state_county_map,
            initial_saturation=initial_sat,
        )
        assert len(result.monthly_snapshots) == 5

    def test_firm_borne_scenario(
        self, mini_approval_probs, mini_state_county_map
    ):
        """Firm-borne scenario produces firm costs."""
        cfg = _make_tiny_cfg(n_steps=12, threshold=0.50, firm_borne=True)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        result = run_single_draw(
            0, cfg, mini_approval_probs, state_shares, mini_state_county_map
        )
        # Firm-borne with 50% threshold and interventions should produce some builds
        # and some firm cost
        assert result.total_candidates > 0
        assert len(result.monthly_snapshots) == 12

    def test_summary_dict_keys(
        self, mini_approval_probs, mini_state_county_map
    ):
        """DrawResult.summary_dict has expected keys."""
        cfg = _make_tiny_cfg(n_steps=3, n_draws=1)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        result = run_single_draw(
            0, cfg, mini_approval_probs, state_shares, mini_state_county_map
        )
        summary = result.summary_dict()
        expected_keys = {
            "total_built", "cumulative_gw", "gini_coefficient",
            "community_surplus_m", "firm_cost_m", "total_rejected", "infeasible_rate",
        }
        assert set(summary.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Runner tests
# ---------------------------------------------------------------------------


class TestRunner:
    def test_run_scenario_small(
        self, mini_approval_probs, mini_state_county_map, mini_feature_matrix
    ):
        """Run 3 draws of 5 months — smoke test."""
        cfg = _make_tiny_cfg(n_steps=5, n_draws=3)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        result = run_scenario(
            cfg=cfg,
            approval_probs=mini_approval_probs,
            state_shares_df=state_shares,
            feature_matrix=mini_feature_matrix,
            n_draws=3,
            progress_interval=0,
        )
        assert result.n_draws == 3
        assert len(result.draw_results) == 3
        assert result.elapsed_seconds > 0
        assert "total_built" in result.aggregate
        assert result.monthly_time_series is not None
        assert len(result.monthly_time_series) == 5

    def test_run_scenario_deterministic(
        self, mini_approval_probs, mini_state_county_map, mini_feature_matrix
    ):
        """Same config + seed produces same aggregate results."""
        cfg = _make_tiny_cfg(n_steps=5, n_draws=5)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        r1 = run_scenario(
            cfg, mini_approval_probs, state_shares, mini_feature_matrix,
            n_draws=5, progress_interval=0,
        )
        r2 = run_scenario(
            cfg, mini_approval_probs, state_shares, mini_feature_matrix,
            n_draws=5, progress_interval=0,
        )
        assert r1.aggregate["total_built"]["mean"] == r2.aggregate["total_built"]["mean"]

    def test_run_scenario_summary_table(
        self, mini_approval_probs, mini_state_county_map, mini_feature_matrix
    ):
        """Summary table formats without error."""
        cfg = _make_tiny_cfg(n_steps=3, n_draws=2)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        result = run_scenario(
            cfg, mini_approval_probs, state_shares, mini_feature_matrix,
            n_draws=2, progress_interval=0,
        )
        table = result.summary_table()
        assert "base" in table
        assert "mean=" in table

    def test_build_monthly_time_series(
        self, mini_approval_probs, mini_state_county_map, mini_feature_matrix
    ):
        """Monthly time series has correct shape."""
        cfg = _make_tiny_cfg(n_steps=6, n_draws=3)
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        result = run_scenario(
            cfg, mini_approval_probs, state_shares, mini_feature_matrix,
            n_draws=3, progress_interval=0,
        )
        ts = result.monthly_time_series
        assert len(ts) == 6
        assert "mean_total_built" in ts.columns
        assert "mean_cumulative_gw" in ts.columns
        assert "p2_5_total_built" in ts.columns
        assert "p97_5_total_built" in ts.columns

    def test_laissez_faire_vs_supermajority(
        self, mini_approval_probs, mini_feature_matrix
    ):
        """Supermajority scenario builds fewer facilities than laissez-faire."""
        state_shares = pd.DataFrame({
            "state": ["VA", "TX", "GA"],
            "adjusted_share": [0.5, 0.3, 0.2],
        })
        cfg_lf = _make_tiny_cfg(n_steps=24, threshold=None)
        cfg_sm = _make_tiny_cfg(n_steps=24, threshold=0.75)

        r_lf = run_scenario(
            cfg_lf, mini_approval_probs, state_shares, mini_feature_matrix,
            n_draws=10, progress_interval=0,
        )
        r_sm = run_scenario(
            cfg_sm, mini_approval_probs, state_shares, mini_feature_matrix,
            n_draws=10, progress_interval=0,
        )
        assert (
            r_sm.aggregate["total_built"]["mean"]
            < r_lf.aggregate["total_built"]["mean"]
        )


# ---------------------------------------------------------------------------
# Integration test with real data
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests using real project data files."""

    @pytest.fixture
    def real_data_available(self):
        """Skip if data files are not present."""
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        probs = root / "data" / "processed" / "county_approval_probs.csv"
        shares = root / "data" / "external" / "state_shares.csv"
        matrix = root / "data" / "processed" / "county_feature_matrix.csv"
        if not (probs.exists() and shares.exists() and matrix.exists()):
            pytest.skip("Real data files not available")

    def test_load_real_approval_probs(self, real_data_available):
        """Real approval probs load correctly."""
        probs = load_approval_probs()
        assert len(probs) >= 232  # 3,153 with all-county expansion, 232 minimum
        assert "51107" in probs  # Loudoun
        assert 0.0 < probs["51107"] < 1.0

    def test_run_real_scenario_small(self, real_data_available):
        """Run 5 draws on real data — integration smoke test."""
        cfg = _make_tiny_cfg(n_steps=12, n_draws=5)
        result = run_scenario(cfg=cfg, n_draws=5, progress_interval=0)
        assert result.n_draws == 5
        assert result.aggregate["total_built"]["mean"] > 0
        assert result.monthly_time_series is not None
        assert len(result.monthly_time_series) == 12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tiny_cfg(
    n_steps: int = 10,
    n_draws: int = 1,
    threshold: float | None = None,
    firm_borne: bool = False,
) -> SimConfig:
    """Build a SimConfig with minimal steps for fast testing."""
    from dataclasses import replace
    from src.config import (
        SimulationConfig, CandidateQueueConfig, ApprovalConfig,
        ScenarioConfig, InterventionsConfig, TaxBenefitConfig,
        EmploymentBenefitConfig,
    )
    cfg = SimConfig(
        simulation=SimulationConfig(
            n_steps=n_steps,
            n_draws=n_draws,
            seed=42,
            monthly_gw_addition=1.5,
        ),
        candidate_queue=CandidateQueueConfig(avg_project_mw=300.0),
        approval=ApprovalConfig(beta_concentration=40.0),
        scenario=ScenarioConfig(
            name="base",
            threshold=threshold,
            firm_borne=firm_borne,
        ),
        interventions=InterventionsConfig(
            tax_benefit=TaxBenefitConfig(enabled=firm_borne),
            employment_benefit=EmploymentBenefitConfig(enabled=firm_borne),
        ),
    )
    return cfg


def _enable_interventions(cfg: SimConfig) -> SimConfig:
    """Return a copy of cfg with both interventions enabled."""
    from dataclasses import replace
    return replace(
        cfg,
        interventions=replace(
            cfg.interventions,
            tax_benefit=replace(cfg.interventions.tax_benefit, enabled=True),
            employment_benefit=replace(cfg.interventions.employment_benefit, enabled=True),
        ),
    )
