#!/usr/bin/env python3
"""Train the XGBoost approval model and output calibrated county probabilities.

Usage:
    python scripts/train_model.py [--output data/processed/county_approval_probs.csv]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.model.xgboost_model import XGBoostApprovalModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX = PROJECT_ROOT / "data" / "processed" / "county_feature_matrix.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "county_approval_probs.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Train XGBoost approval model")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    # Load config and feature matrix
    cfg = load_config()
    df = pd.read_csv(args.matrix, dtype={"fips": str})
    print(f"Loaded feature matrix: {len(df)} counties, {df['binary_outcome'].notna().sum()} labeled")

    # Train
    model = XGBoostApprovalModel(
        xgb_config=cfg.model.xgboost,
        calibration_config=cfg.calibration,
    )
    train_metrics = model.train(df)
    print(f"\n=== Training Results ===")
    print(f"  Training set: {train_metrics['n_train']} counties "
          f"({train_metrics['n_approved']} approved, {train_metrics['n_blocked']} blocked)")
    print(f"  Scale pos weight: {train_metrics['scale_pos_weight']}")
    print(f"  5-fold CV AUC: {train_metrics['cv_auc_mean']:.3f} ± {train_metrics['cv_auc_std']:.3f}")

    # Feature importances
    importances = model.feature_importances()
    print(f"\n=== Feature Importances (gain) ===")
    for feat, imp in sorted(importances.items(), key=lambda x: -x[1]):
        bar = "█" * int(imp * 50)
        print(f"  {feat:25s} {imp:.4f} {bar}")

    # Calibrate
    cal_meta = model.calibrate()
    print(f"\n=== Calibration ===")
    print(f"  Median shift: {cal_meta['median_shift']:.4f}")
    print(f"  FIPS overrides: {cal_meta['n_overrides']}")
    print(f"  Calibrated p range: [{cal_meta['p_min']:.3f}, {cal_meta['p_max']:.3f}]")
    print(f"  Calibrated p mean: {cal_meta['p_mean']:.3f}")

    # Spot-check anchor counties
    for name, fips, expected in [
        ("Loudoun", "51107", 0.775),
        ("Prince William", "51153", 0.25),
    ]:
        p = model.predict_proba(fips)
        print(f"  {name} ({fips}): p={p:.3f} (target={expected})")

    # Save
    model.save_probabilities(args.output)
    print(f"\nSaved {len(model.predict_all())} county probabilities to {args.output}")


if __name__ == "__main__":
    main()
