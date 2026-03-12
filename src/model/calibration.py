"""Calibration: percentile-rank mapping of raw model scores to approval probabilities.

The raw XGBoost output is not directly interpretable as an approval probability.
We calibrate it via:
1. Rank all counties by raw score → percentile [0, 1]
2. Map percentile to target range using the median anchor (shift) and clip bounds (spread)
3. Override specific FIPS-based anchor counties with their known probabilities

This approach is robust even when the model assigns similar raw scores to counties
that should have very different approval rates (e.g., Loudoun vs Prince William —
both high-saturation VA counties, but opposite outcomes).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats


@dataclass
class CalibrationResult:
    """Result of calibrating raw scores to anchor points."""

    median_shift: float  # How much to shift the median of percentile-mapped scores
    clip_min: float
    clip_max: float
    fips_overrides: dict[str, float] = field(default_factory=dict)

    def transform(self, raw_scores: np.ndarray) -> np.ndarray:
        """Map raw scores to calibrated probabilities via percentile rank."""
        n = len(raw_scores)
        if n == 0:
            return raw_scores

        # Compute percentile rank (0 to 1)
        ranks = stats.rankdata(raw_scores, method="average") / n

        # Map ranks to [clip_min, clip_max] range, centered on median target
        spread = self.clip_max - self.clip_min
        calibrated = self.clip_min + ranks * spread

        # Apply median shift to hit the target median
        calibrated = calibrated + self.median_shift

        return np.clip(calibrated, self.clip_min, self.clip_max)

    def transform_single(self, raw_score: float) -> float:
        """Calibrate a single raw score (approximate — uses the score directly)."""
        # For single scores, apply a simple linear transform
        calibrated = raw_score + self.median_shift
        return float(np.clip(calibrated, self.clip_min, self.clip_max))


def fit_calibration(
    raw_scores: dict[str, float],
    anchors: list[dict[str, float | str]],
    clip_min: float = 0.05,
    clip_max: float = 0.95,
) -> CalibrationResult:
    """Fit a percentile-rank calibration with FIPS overrides.

    Parameters
    ----------
    raw_scores : Dict mapping FIPS → raw model probability.
    anchors : List of anchor dicts, each with keys:
        - 'name': identifier
        - 'target_p': desired calibrated probability
        - 'fips' (optional): specific county FIPS code
        - 'type' (optional): 'median' to use as the median target
    clip_min, clip_max : Bounds for calibrated probabilities.

    Returns
    -------
    CalibrationResult with shift, bounds, and FIPS overrides.
    """
    # Find median target from anchors
    median_target = 0.44  # Default from Heatmap/Embold survey
    fips_overrides: dict[str, float] = {}

    for anchor in anchors:
        target_p = float(anchor["target_p"])
        if anchor.get("type") == "median":
            median_target = target_p
        elif anchor.get("fips") is not None:
            fips_overrides[str(anchor["fips"])] = np.clip(target_p, clip_min, clip_max)

    # The percentile-rank approach maps ranks to [clip_min, clip_max].
    # The median rank is ~0.5, so the median calibrated value is:
    #   clip_min + 0.5 * (clip_max - clip_min) = (clip_min + clip_max) / 2
    # We shift by: median_target - (clip_min + clip_max) / 2
    natural_median = (clip_min + clip_max) / 2.0
    median_shift = median_target - natural_median

    return CalibrationResult(
        median_shift=median_shift,
        clip_min=clip_min,
        clip_max=clip_max,
        fips_overrides=fips_overrides,
    )


def calibrate_county_probabilities(
    raw_scores: dict[str, float],
    anchors: list[dict[str, float | str]],
    clip_min: float = 0.05,
    clip_max: float = 0.95,
) -> dict[str, float]:
    """Calibrate all county raw scores and return FIPS → calibrated p mapping.

    Uses percentile-rank mapping for the bulk of counties, then applies
    FIPS-specific overrides for anchor counties with known ground truth.

    Parameters
    ----------
    raw_scores : FIPS → raw probability from model.
    anchors : Calibration anchor points (from config).
    clip_min, clip_max : Probability bounds.

    Returns
    -------
    Dict of FIPS → calibrated probability.
    """
    cal = fit_calibration(raw_scores, anchors, clip_min, clip_max)

    fips_list = list(raw_scores.keys())
    raw_array = np.array(list(raw_scores.values()))
    calibrated_array = cal.transform(raw_array)

    result = dict(zip(fips_list, calibrated_array.tolist()))

    # Apply FIPS-specific overrides
    for fips, target_p in cal.fips_overrides.items():
        if fips in result:
            result[fips] = target_p

    return result


def apply_state_shrinkage(
    calibrated: dict[str, float],
    fips_to_state: dict[str, str],
    state_train_counts: dict[str, int],
    k: int = 5,
    national_median: float = 0.44,
    clip_min: float = 0.05,
    clip_max: float = 0.95,
) -> dict[str, float]:
    """Shrink calibrated county probabilities toward the national median.

    Counties in states with few training samples get pulled more toward
    the national median, reducing extrapolation artifacts. Counties in
    well-represented states (like TX with 23 samples) keep most of their
    model-derived probability.

    Parameters
    ----------
    calibrated : FIPS → calibrated probability.
    fips_to_state : FIPS → 2-letter state abbreviation.
    state_train_counts : State abbreviation → number of labeled training counties.
    k : Shrinkage pseudocount. Higher = more shrinkage toward national_median.
    national_median : Target to shrink toward (default 0.44 from Heatmap/Embold).
    clip_min, clip_max : Probability bounds.

    Returns
    -------
    Dict of FIPS → shrinkage-adjusted probability.
    """
    result = {}
    for fips, p in calibrated.items():
        state = fips_to_state.get(fips)
        n = state_train_counts.get(state, 0) if state else 0
        w = n / (n + k)  # Weight for model prediction (0 = all prior, 1 = all model)
        shrunk = w * p + (1 - w) * national_median
        result[fips] = float(np.clip(shrunk, clip_min, clip_max))
    return result
