#!/usr/bin/env python
"""Rebuild the complete data pipeline from raw sources.

Runs three steps:
  1. FracTracker ingestion → county feature matrix (232 counties)
  2. XGBoost training + calibration → county approval probabilities (232 counties)
  3. All-county extrapolation → approval probabilities for all 3,153 US counties

All external data (Census ACS, QWI, water stress, etc.) is pre-fetched and
committed in data/external/. This script does NOT re-fetch external data.

Usage:
    PYTHONPATH=. python scripts/rebuild_data.py
    PYTHONPATH=. python scripts/rebuild_data.py --skip-train   # Skip XGBoost (use cached probs)
    PYTHONPATH=. python scripts/rebuild_data.py --fast          # Fast XGBoost config (50 trees, 3-fold)
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def step1_build_feature_matrix() -> None:
    """Build county feature matrix from FracTracker + external data."""
    print("\n=== Step 1: Building county feature matrix ===")
    from src.data.ingest import run_ingestion
    from src.data.features import build_feature_matrix

    result = run_ingestion()
    out = PROCESSED_DIR / "county_feature_matrix.csv"
    build_feature_matrix(result["county"], output_path=str(out))
    print(f"  Saved: {out}")


def step2_train_model(fast: bool = False) -> None:
    """Train XGBoost and save calibrated approval probabilities."""
    print("\n=== Step 2: Training XGBoost approval model ===")
    import pandas as pd
    from src.config import load_config, XGBoostConfig
    from src.model.xgboost_model import XGBoostApprovalModel

    cfg = load_config()
    matrix = pd.read_csv(PROCESSED_DIR / "county_feature_matrix.csv", dtype={"fips": str})

    xgb_cfg = cfg.model.xgboost
    if fast:
        print("  Using fast config (50 trees, 3-fold CV)")
        xgb_cfg = XGBoostConfig(
            max_depth=3, n_estimators=50, learning_rate=0.1,
            early_stopping_rounds=10, min_child_weight=5,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.5, reg_lambda=1.0, cv_folds=3,
        )

    model = XGBoostApprovalModel(xgb_config=xgb_cfg, calibration_config=cfg.calibration)
    metrics = model.train(matrix)
    print(f"  CV AUC: {metrics['cv_auc_mean']:.3f} ± {metrics['cv_auc_std']:.3f}")

    cal = model.calibrate()
    print(f"  Calibrated: {cal['n_counties']} counties, "
          f"range [{cal['p_min']:.3f}, {cal['p_max']:.3f}], mean={cal['p_mean']:.3f}")

    out = PROCESSED_DIR / "county_approval_probs.csv"
    model.save_probabilities(out)
    print(f"  Saved: {out}")


def step3_build_all_county_probs(fast: bool = False) -> None:
    """Extrapolate approval probabilities to all 3,153 US counties."""
    print("\n=== Step 3: Extrapolating to all US counties ===")
    # Reuse the build_full_county_map logic
    from scripts.build_full_county_map import build_all_county_features
    from src.config import load_config, XGBoostConfig
    from src.model.xgboost_model import XGBoostApprovalModel

    cfg = load_config()
    df = build_all_county_features()

    xgb_cfg = cfg.model.xgboost
    if fast:
        xgb_cfg = XGBoostConfig(
            max_depth=3, n_estimators=50, learning_rate=0.1,
            early_stopping_rounds=10, min_child_weight=5,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.5, reg_lambda=1.0, cv_folds=3,
        )

    model = XGBoostApprovalModel(xgb_config=xgb_cfg, calibration_config=cfg.calibration)
    model.train(df)
    model.calibrate()

    out = PROCESSED_DIR / "all_county_approval_probs.csv"
    model.save_probabilities(out)
    print(f"  Saved: {out} ({len(df)} counties)")


def main():
    parser = argparse.ArgumentParser(description="Rebuild complete data pipeline")
    parser.add_argument("--skip-train", action="store_true",
                        help="Skip XGBoost training (use cached probabilities)")
    parser.add_argument("--fast", action="store_true",
                        help="Use fast XGBoost config (50 trees, 3-fold CV)")
    args = parser.parse_args()

    t0 = time.time()

    step1_build_feature_matrix()

    if not args.skip_train:
        step2_train_model(fast=args.fast)
        step3_build_all_county_probs(fast=args.fast)
    else:
        print("\n=== Skipping XGBoost training (--skip-train) ===")
        print(f"  Using cached: {PROCESSED_DIR / 'county_approval_probs.csv'}")
        print(f"  Using cached: {PROCESSED_DIR / 'all_county_approval_probs.csv'}")

    elapsed = time.time() - t0
    print(f"\n{'='*50}")
    print(f"  Pipeline complete in {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"{'='*50}")
    print(f"\nOutputs:")
    print(f"  {PROCESSED_DIR / 'county_feature_matrix.csv'}")
    if not args.skip_train:
        print(f"  {PROCESSED_DIR / 'county_approval_probs.csv'}")
        print(f"  {PROCESSED_DIR / 'all_county_approval_probs.csv'}")


if __name__ == "__main__":
    main()
