"""Approval model protocol — shared interface for placeholder and XGBoost models.

Both models implement the same interface so the simulation doesn't care which
is active. The config's `approval.provider` selects the implementation.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


class ApprovalModel(Protocol):
    """Protocol for county approval probability models."""

    def predict_proba(self, fips: str) -> float:
        """Return calibrated approval probability p ∈ [0.05, 0.95] for a county."""
        ...

    def get_beta_params(self, fips: str, kappa: float = 40.0) -> tuple[float, float]:
        """Return Beta(α, β) parameters for sampling approval draws.

        α = p × κ, β = (1 − p) × κ where p = predict_proba(fips).
        """
        ...

    def feature_names(self) -> list[str]:
        """Return ordered list of feature names used by the model."""
        ...

    def feature_importances(self) -> dict[str, float]:
        """Return feature name → importance score mapping."""
        ...


def p_to_beta_params(p: float, kappa: float = 40.0) -> tuple[float, float]:
    """Convert calibrated probability to Beta(α, β) parameters.

    Parameters
    ----------
    p : Calibrated approval probability, clipped to [0.05, 0.95].
    kappa : Concentration parameter (higher = tighter distribution).

    Returns
    -------
    (alpha, beta) tuple for np.random.Generator.beta(alpha, beta).
    """
    p = np.clip(p, 0.05, 0.95)
    alpha = p * kappa
    beta = (1.0 - p) * kappa
    return float(alpha), float(beta)
