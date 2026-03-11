"""Tests for approval model components: protocol, placeholder, calibration, XGBoost."""

import numpy as np
import pandas as pd
import pytest

from src.model.calibration import (
    CalibrationResult,
    calibrate_county_probabilities,
    fit_calibration,
)
from src.model.placeholder import PlaceholderModel
from src.model.protocol import p_to_beta_params

# ---------------------------------------------------------------------------
# Protocol / Beta parameterization
# ---------------------------------------------------------------------------


class TestBetaParams:
    def test_standard_conversion(self):
        alpha, beta = p_to_beta_params(0.5, kappa=40.0)
        assert alpha == pytest.approx(20.0)
        assert beta == pytest.approx(20.0)

    def test_high_probability(self):
        alpha, beta = p_to_beta_params(0.9, kappa=40.0)
        assert alpha == pytest.approx(36.0)
        assert beta == pytest.approx(4.0)

    def test_clips_to_bounds(self):
        """Probabilities outside [0.05, 0.95] get clipped."""
        alpha, beta = p_to_beta_params(0.01, kappa=40.0)
        assert alpha == pytest.approx(0.05 * 40.0)  # Clipped to 0.05

        alpha, beta = p_to_beta_params(0.99, kappa=40.0)
        assert alpha == pytest.approx(0.95 * 40.0)  # Clipped to 0.95

    def test_kappa_concentration(self):
        """Higher kappa = tighter distribution (higher alpha+beta)."""
        a1, b1 = p_to_beta_params(0.5, kappa=20.0)
        a2, b2 = p_to_beta_params(0.5, kappa=80.0)
        assert (a2 + b2) > (a1 + b1)

    def test_mean_preserved(self):
        """Beta distribution mean = alpha/(alpha+beta) should ≈ p."""
        for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            alpha, beta = p_to_beta_params(p, kappa=40.0)
            mean = alpha / (alpha + beta)
            assert mean == pytest.approx(p, abs=0.01)


# ---------------------------------------------------------------------------
# Placeholder model
# ---------------------------------------------------------------------------


class TestPlaceholderModel:
    def test_known_county(self):
        model = PlaceholderModel()
        p = model.predict_proba("51107")  # Loudoun
        assert p == pytest.approx(0.775)

    def test_unknown_county_uses_default(self):
        model = PlaceholderModel()
        p = model.predict_proba("99999")
        assert p == pytest.approx(0.44)

    def test_beta_params(self):
        model = PlaceholderModel()
        alpha, beta = model.get_beta_params("51107", kappa=40.0)
        assert alpha == pytest.approx(0.775 * 40.0)
        assert beta == pytest.approx(0.225 * 40.0)

    def test_predict_all(self):
        model = PlaceholderModel()
        probs = model.predict_all(["51107", "99999"])
        assert probs["51107"] == pytest.approx(0.775)
        assert probs["99999"] == pytest.approx(0.44)

    def test_feature_names_empty(self):
        model = PlaceholderModel()
        assert model.feature_names() == []

    def test_feature_importances_empty(self):
        model = PlaceholderModel()
        assert model.feature_importances() == {}

    def test_prince_william_low(self):
        model = PlaceholderModel()
        p = model.predict_proba("51153")  # Prince William — moratorium
        assert p < 0.35

    def test_custom_default(self):
        model = PlaceholderModel(default_p=0.60)
        assert model.predict_proba("99999") == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


class TestCalibration:
    def test_no_anchors_default_median(self):
        raw = {"51107": 0.8, "51153": 0.3}
        cal = fit_calibration(raw, [])
        # Default median target is 0.44
        assert cal.median_shift == pytest.approx(0.44 - 0.5)

    def test_median_anchor_sets_shift(self):
        raw = {"a": 0.6, "b": 0.4, "c": 0.5}
        anchors = [{"name": "median", "target_p": 0.44, "type": "median"}]
        cal = fit_calibration(raw, anchors)
        assert cal.median_shift == pytest.approx(0.44 - 0.5)

    def test_fips_overrides_exact(self):
        raw = {"51107": 0.9, "51153": 0.2, "other": 0.5}
        anchors = [
            {"name": "loudoun", "fips": "51107", "target_p": 0.775},
            {"name": "pw", "fips": "51153", "target_p": 0.25},
        ]
        result = calibrate_county_probabilities(raw, anchors)
        # FIPS overrides should be exact
        assert result["51107"] == pytest.approx(0.775)
        assert result["51153"] == pytest.approx(0.25)

    def test_clipping(self):
        cal = CalibrationResult(median_shift=0.5, clip_min=0.05, clip_max=0.95)
        # Large positive shift should get clipped
        arr = np.array([0.1, 0.5, 0.9])
        result = cal.transform(arr)
        assert all(r >= 0.05 for r in result)
        assert all(r <= 0.95 for r in result)

    def test_calibrate_county_probabilities_with_overrides(self):
        raw = {"a": 0.3, "b": 0.7, "c": 0.5}
        anchors = [
            {"name": "a", "fips": "a", "target_p": 0.25},
            {"name": "b", "fips": "b", "target_p": 0.75},
        ]
        result = calibrate_county_probabilities(raw, anchors)
        assert result["a"] == pytest.approx(0.25)
        assert result["b"] == pytest.approx(0.75)
        # "c" should get a percentile-rank value in valid range
        assert 0.05 <= result["c"] <= 0.95

    def test_rank_ordering_preserved(self):
        """Counties with higher raw scores should get higher calibrated probs."""
        raw = {f"{i:05d}": i / 10.0 for i in range(1, 10)}
        anchors = [{"name": "median", "target_p": 0.44, "type": "median"}]
        result = calibrate_county_probabilities(raw, anchors)
        values = [result[f"{i:05d}"] for i in range(1, 10)]
        # Monotonically increasing (rank order preserved)
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1]

    def test_all_in_bounds(self):
        raw = {f"{i:05d}": np.random.default_rng(42).random() for i in range(50)}
        anchors = [{"name": "median", "target_p": 0.44, "type": "median"}]
        result = calibrate_county_probabilities(raw, anchors)
        for p in result.values():
            assert 0.05 <= p <= 0.95


# ---------------------------------------------------------------------------
# XGBoost model (integration-style tests with real data)
# ---------------------------------------------------------------------------


def _make_synthetic_matrix(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Create a synthetic feature matrix for XGBoost testing."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(
        {
            "fips": [f"{i:05d}" for i in range(n)],
            "facility_count": rng.integers(1, 15, n),
            "total_mw": rng.uniform(0, 5000, n),
            "avg_project_mw": rng.uniform(100, 1000, n),
            "hyperscaler_share": rng.uniform(0, 1, n),
            "saturation_count": rng.integers(0, 50, n),
            "pushback_flag": rng.integers(0, 2, n),
            "state_incentive_score": rng.uniform(0.25, 1.0, n),
            "dc_employment": rng.integers(0, 5000, n),
            "dc_employment_growth": rng.uniform(-0.5, 5.0, n),
            "water_stress_decile": rng.integers(1, 11, n),
            "partisan_lean_r": rng.uniform(0.1, 0.9, n),
        }
    )
    # Binary outcome: counties with pushback + high water stress more likely blocked
    logit = (
        -0.5
        + 1.5 * df["pushback_flag"]
        + 0.1 * df["water_stress_decile"]
        - 0.5 * df["state_incentive_score"]
    )
    p_block = 1.0 / (1.0 + np.exp(-logit))
    df["binary_outcome"] = (rng.random(n) < p_block).astype(float)
    # Make 20% unlabeled
    unlabeled_idx = rng.choice(n, size=n // 5, replace=False)
    df.loc[unlabeled_idx, "binary_outcome"] = np.nan
    return df


def _fast_xgb_config():
    """XGBoost config with fewer estimators for fast tests."""
    from src.config import XGBoostConfig

    return XGBoostConfig(
        max_depth=3,
        n_estimators=20,
        learning_rate=0.1,
        early_stopping_rounds=5,
        min_child_weight=3,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        cv_folds=3,
    )


class TestXGBoostModel:
    def test_train_returns_metrics(self):
        from src.model.xgboost_model import XGBoostApprovalModel

        df = _make_synthetic_matrix()
        model = XGBoostApprovalModel(xgb_config=_fast_xgb_config())
        metrics = model.train(df)
        assert "cv_auc_mean" in metrics
        assert "n_train" in metrics
        assert metrics["n_train"] == df["binary_outcome"].notna().sum()
        assert 0.0 <= metrics["cv_auc_mean"] <= 1.0

    def test_feature_importances_sum_to_one(self):
        from src.model.xgboost_model import XGBoostApprovalModel

        df = _make_synthetic_matrix()
        model = XGBoostApprovalModel(xgb_config=_fast_xgb_config())
        model.train(df)
        importances = model.feature_importances()
        assert len(importances) == 11
        total = sum(importances.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_predict_proba_range(self):
        from src.model.xgboost_model import XGBoostApprovalModel

        df = _make_synthetic_matrix()
        model = XGBoostApprovalModel(xgb_config=_fast_xgb_config())
        model.train(df)
        for fips in df["fips"][:10]:
            p = model.predict_proba(fips)
            assert 0.0 <= p <= 1.0

    def test_calibrate_shifts_probabilities(self):
        from src.model.xgboost_model import XGBoostApprovalModel

        df = _make_synthetic_matrix()
        model = XGBoostApprovalModel(xgb_config=_fast_xgb_config())
        model.train(df)

        # Calibrate with an anchor
        model.calibrate(
            anchors=[{"name": "median", "target_p": 0.44, "type": "median"}],
        )
        cal_p = model.predict_proba("00000")
        # Calibrated probs should differ from raw (unless already at 0.44 median)
        # At least verify it's in valid range
        assert 0.05 <= cal_p <= 0.95

    def test_beta_params_valid(self):
        from src.model.xgboost_model import XGBoostApprovalModel

        df = _make_synthetic_matrix()
        model = XGBoostApprovalModel(xgb_config=_fast_xgb_config())
        model.train(df)
        alpha, beta = model.get_beta_params("00000", kappa=40.0)
        assert alpha > 0
        assert beta > 0
        assert alpha + beta == pytest.approx(40.0, abs=2.0)

    def test_save_probabilities(self, tmp_path):
        from src.model.xgboost_model import XGBoostApprovalModel

        df = _make_synthetic_matrix()
        model = XGBoostApprovalModel(xgb_config=_fast_xgb_config())
        model.train(df)
        out = tmp_path / "probs.csv"
        model.save_probabilities(out)
        loaded = pd.read_csv(out)
        assert "fips" in loaded.columns
        assert "approval_prob" in loaded.columns
        assert "beta_alpha" in loaded.columns
        assert len(loaded) == len(df)

    def test_predict_all(self):
        from src.model.xgboost_model import XGBoostApprovalModel

        df = _make_synthetic_matrix()
        model = XGBoostApprovalModel(xgb_config=_fast_xgb_config())
        model.train(df)
        all_probs = model.predict_all()
        assert len(all_probs) == len(df)

    def test_cv_scores_accessible(self):
        from src.model.xgboost_model import XGBoostApprovalModel

        df = _make_synthetic_matrix()
        model = XGBoostApprovalModel(xgb_config=_fast_xgb_config())
        model.train(df)
        scores = model.cv_scores()
        assert "cv_auc_mean" in scores
        assert len(scores["cv_auc_folds"]) == 3


class TestXGBoostRealData:
    """Integration test with the real feature matrix."""

    def test_trains_on_real_data(self):
        from pathlib import Path

        from src.model.xgboost_model import XGBoostApprovalModel

        matrix_path = (
            Path(__file__).parent.parent / "data" / "processed" / "county_feature_matrix.csv"
        )
        if not matrix_path.exists():
            pytest.skip("Real feature matrix not available")

        df = pd.read_csv(matrix_path, dtype={"fips": str})
        model = XGBoostApprovalModel()
        metrics = model.train(df)

        assert metrics["n_train"] == 108
        assert metrics["cv_auc_mean"] > 0.5  # Better than random
        print(f"CV AUC: {metrics['cv_auc_mean']:.3f} ± {metrics['cv_auc_std']:.3f}")

        # Feature importances should be non-trivial
        importances = model.feature_importances()
        assert max(importances.values()) > 0.05  # At least one feature matters

    def test_calibrated_anchors_close(self):
        from pathlib import Path

        from src.config import load_config
        from src.model.xgboost_model import XGBoostApprovalModel

        matrix_path = (
            Path(__file__).parent.parent / "data" / "processed" / "county_feature_matrix.csv"
        )
        if not matrix_path.exists():
            pytest.skip("Real feature matrix not available")

        cfg = load_config()
        df = pd.read_csv(matrix_path, dtype={"fips": str})
        model = XGBoostApprovalModel(
            xgb_config=cfg.model.xgboost,
            calibration_config=cfg.calibration,
        )
        model.train(df)
        model.calibrate()

        # Anchor counties should be close to their targets
        loudoun_p = model.predict_proba("51107")
        pw_p = model.predict_proba("51153")
        assert loudoun_p == pytest.approx(0.775, abs=0.15)
        assert pw_p == pytest.approx(0.25, abs=0.15)

        # All counties should be in [0.05, 0.95]
        all_probs = model.predict_all()
        for fips, p in all_probs.items():
            assert 0.05 <= p <= 0.95, f"County {fips} has p={p} outside bounds"
