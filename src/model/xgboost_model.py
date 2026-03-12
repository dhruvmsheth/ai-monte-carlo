"""XGBoost approval probability model.

Trains on ~108 labeled counties from the FracTracker feature matrix to predict
binary approval outcome. Produces calibrated probability output + feature
importances for interpretability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from src.config import CalibrationConfig, XGBoostConfig
from src.model.calibration import (
    apply_state_shrinkage,
    calibrate_county_probabilities,
    fit_calibration,
)
from src.model.protocol import p_to_beta_params

# Feature columns used for training (order matters for feature importance)
# Structural features only — dynamic features (saturation_count, facility_count,
# total_mw) are handled by intervention functions during simulation, not here.
FEATURE_COLS: list[str] = [
    "avg_project_mw",
    "hyperscaler_share",
    "pushback_flag",
    "state_incentive_score",
    "dc_employment",
    "dc_employment_growth",
    "water_stress_decile",
    "partisan_lean_r",
    "population",
    "population_density",
    "median_household_income",
    "unemployment_rate",
    "pct_college_educated",
    "ag_employment_share",
    "electricity_price",
]


class XGBoostApprovalModel:
    """XGBoost-based county approval probability model.

    Trains on labeled counties, calibrates to anchor points, and provides
    Beta-parameterized probabilities for simulation sampling.
    """

    def __init__(
        self,
        xgb_config: XGBoostConfig | None = None,
        calibration_config: CalibrationConfig | None = None,
    ) -> None:
        self._xgb_config = xgb_config or XGBoostConfig()
        self._cal_config = calibration_config or CalibrationConfig()
        self._model = None  # Set after train()
        self._calibration = None  # Set after calibrate()
        self._calibrated_probs: dict[str, float] = {}
        self._raw_probs: dict[str, float] = {}
        self._cv_scores: dict[str, float] = {}
        self._feature_cols = list(FEATURE_COLS)
        self._fips_to_state: dict[str, str] = {}
        self._state_train_counts: dict[str, int] = {}

    def train(
        self,
        feature_matrix: pd.DataFrame,
        feature_cols: list[str] | None = None,
    ) -> dict[str, Any]:
        """Train XGBoost on labeled counties.

        Parameters
        ----------
        feature_matrix : DataFrame with FEATURE_COLS + 'binary_outcome' + 'fips'.
        feature_cols : Override default feature columns.

        Returns
        -------
        Dict with training metrics: cv_auc_mean, cv_auc_std, n_train, n_approved, n_blocked.
        """
        import xgboost as xgb

        if feature_cols is not None:
            self._feature_cols = list(feature_cols)

        # Filter to labeled counties
        labeled = feature_matrix[feature_matrix["binary_outcome"].notna()].copy()
        X = labeled[self._feature_cols].values
        y = labeled["binary_outcome"].values.astype(int)

        n_approved = int(y.sum())
        n_blocked = len(y) - n_approved
        scale_pos_weight = n_blocked / max(n_approved, 1)

        cfg = self._xgb_config
        self._model = xgb.XGBClassifier(
            max_depth=cfg.max_depth,
            n_estimators=cfg.n_estimators,
            learning_rate=cfg.learning_rate,
            min_child_weight=cfg.min_child_weight,
            subsample=cfg.subsample,
            colsample_bytree=cfg.colsample_bytree,
            reg_alpha=cfg.reg_alpha,
            reg_lambda=cfg.reg_lambda,
            scale_pos_weight=scale_pos_weight,
            objective="binary:logistic",
            eval_metric="logloss",
            use_label_encoder=False,
            random_state=42,
            verbosity=0,
        )

        # 5-fold stratified cross-validation for AUC
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import train_test_split

        print(f"  [1/3] Cross-validation ({cfg.cv_folds}-fold, {cfg.n_estimators} trees each)")
        skf = StratifiedKFold(n_splits=cfg.cv_folds, shuffle=True, random_state=42)
        cv_auc = []
        for i, (train_idx, val_idx) in enumerate(skf.split(X, y), 1):
            fold_model = xgb.XGBClassifier(**self._model.get_params())
            fold_model.fit(X[train_idx], y[train_idx], verbose=False)
            fold_auc = roc_auc_score(y[val_idx], fold_model.predict_proba(X[val_idx])[:, 1])
            cv_auc.append(fold_auc)
            print(f"    Fold {i}/{cfg.cv_folds}: AUC={fold_auc:.3f}", flush=True)
        cv_auc = np.array(cv_auc)
        self._cv_scores = {
            "cv_auc_mean": float(np.mean(cv_auc)),
            "cv_auc_std": float(np.std(cv_auc)),
            "cv_auc_folds": cv_auc.tolist(),
        }
        print(f"    Mean AUC: {np.mean(cv_auc):.3f} ± {np.std(cv_auc):.3f}")

        # Train with early stopping (80/20 split)
        print(f"  [2/3] Training with early stopping...", end=" ", flush=True)
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=42
        )
        self._model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        print("done")

        # Refit on ALL labeled data for final model
        print("  [3/3] Final refit on all labeled data...", end=" ", flush=True)
        self._model.fit(X, y, verbose=False)
        print("done")

        # Store raw predictions for all counties (labeled + unlabeled)
        X_all = feature_matrix[self._feature_cols].values
        raw_probs = self._model.predict_proba(X_all)[:, 1]
        self._raw_probs = dict(zip(feature_matrix["fips"].values, raw_probs.tolist()))

        # Store state info for post-calibration shrinkage
        if "state" in feature_matrix.columns:
            self._fips_to_state = dict(
                zip(feature_matrix["fips"].values, feature_matrix["state"].fillna("").values)
            )
            self._state_train_counts = (
                labeled.groupby("state")["binary_outcome"].count().to_dict()
            )

        return {
            "n_train": len(y),
            "n_approved": n_approved,
            "n_blocked": n_blocked,
            "scale_pos_weight": round(scale_pos_weight, 3),
            **self._cv_scores,
        }

    def calibrate(
        self,
        anchors: list[dict[str, Any]] | None = None,
        clip_min: float | None = None,
        clip_max: float | None = None,
    ) -> dict[str, float]:
        """Calibrate raw probabilities to anchor points.

        Parameters
        ----------
        anchors : Override config anchors. Each dict needs 'target_p' and
            optionally 'fips' or 'type'.
        clip_min, clip_max : Override config clips.

        Returns
        -------
        Dict of calibration metadata (slope, intercept, etc).
        """
        if not self._raw_probs:
            raise RuntimeError("Must call train() before calibrate()")

        if anchors is None:
            anchors = [
                {"name": a.name, "target_p": a.target_p, "type": a.type, "fips": a.fips}
                for a in self._cal_config.anchors
            ]
        cmin = clip_min if clip_min is not None else self._cal_config.clip_min
        cmax = clip_max if clip_max is not None else self._cal_config.clip_max

        self._calibration = fit_calibration(self._raw_probs, anchors, cmin, cmax)
        self._calibrated_probs = calibrate_county_probabilities(
            self._raw_probs, anchors, cmin, cmax
        )

        # Apply state-level shrinkage to reduce extrapolation artifacts
        k = self._cal_config.state_shrinkage_k
        if k > 0 and self._fips_to_state:
            self._calibrated_probs = apply_state_shrinkage(
                self._calibrated_probs,
                self._fips_to_state,
                self._state_train_counts,
                k=k,
                clip_min=cmin,
                clip_max=cmax,
            )

        return {
            "median_shift": self._calibration.median_shift,
            "n_overrides": len(self._calibration.fips_overrides),
            "n_counties": len(self._calibrated_probs),
            "p_min": min(self._calibrated_probs.values()),
            "p_max": max(self._calibrated_probs.values()),
            "p_mean": float(np.mean(list(self._calibrated_probs.values()))),
        }

    def predict_proba(self, fips: str) -> float:
        """Return calibrated approval probability for a county."""
        if self._calibrated_probs:
            return self._calibrated_probs.get(fips, 0.44)
        if self._raw_probs:
            return self._raw_probs.get(fips, 0.44)
        return 0.44  # National median fallback

    def get_beta_params(self, fips: str, kappa: float = 40.0) -> tuple[float, float]:
        """Return Beta(α, β) parameters for sampling approval draws."""
        p = self.predict_proba(fips)
        return p_to_beta_params(p, kappa)

    def feature_names(self) -> list[str]:
        """Return ordered list of feature names."""
        return list(self._feature_cols)

    def feature_importances(self) -> dict[str, float]:
        """Return feature name → importance score (gain-based)."""
        if self._model is None:
            return {}
        importances = self._model.feature_importances_
        return dict(zip(self._feature_cols, importances.tolist()))

    def predict_all(self, fips_list: list[str] | None = None) -> dict[str, float]:
        """Return calibrated probabilities for all (or specified) FIPS codes."""
        if fips_list is not None:
            return {fips: self.predict_proba(fips) for fips in fips_list}
        return dict(self._calibrated_probs) if self._calibrated_probs else dict(self._raw_probs)

    def save_probabilities(self, output_path: str | Path) -> None:
        """Save county approval probabilities to CSV."""
        probs = self._calibrated_probs if self._calibrated_probs else self._raw_probs
        if not probs:
            raise RuntimeError("No probabilities to save. Run train() first.")

        rows = []
        for fips, p in sorted(probs.items()):
            alpha, beta = p_to_beta_params(p, kappa=40.0)
            rows.append(
                {
                    "fips": fips,
                    "approval_prob": round(p, 4),
                    "beta_alpha": round(alpha, 2),
                    "beta_beta": round(beta, 2),
                }
            )

        df = pd.DataFrame(rows)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)

    def cv_scores(self) -> dict[str, float]:
        """Return cross-validation scores from training."""
        return dict(self._cv_scores)
