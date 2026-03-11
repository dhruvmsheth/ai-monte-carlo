"""Tests for src/interventions/functions.py — intervention curves."""

import math

import pytest

from src.interventions.functions import (
    combined_intervention_delta,
    employment_benefit_delta,
    tax_benefit_delta,
)


class TestTaxBenefitDelta:
    def test_max_at_zero_saturation(self):
        """At n=0, tax benefit equals A (the maximum)."""
        assert tax_benefit_delta(0, A=0.20) == pytest.approx(0.20)

    def test_decays_with_saturation(self):
        """Tax benefit decreases as saturation increases."""
        d0 = tax_benefit_delta(0)
        d5 = tax_benefit_delta(5)
        d20 = tax_benefit_delta(20)
        assert d0 > d5 > d20 > 0

    def test_exponential_decay_formula(self):
        """Verify exact formula: A * exp(-lambda * n)."""
        n, A, lam = 10, 0.20, 0.25
        expected = A * math.exp(-lam * n)
        assert tax_benefit_delta(n, A=A, lambda_=lam) == pytest.approx(expected)

    def test_approaches_zero(self):
        """At very high saturation, benefit is near zero."""
        assert tax_benefit_delta(100, A=0.20, lambda_=0.25) < 0.001

    def test_custom_params(self):
        result = tax_benefit_delta(5, A=0.30, lambda_=0.10)
        expected = 0.30 * math.exp(-0.10 * 5)
        assert result == pytest.approx(expected)


class TestEmploymentBenefitDelta:
    def test_zero_at_zero_saturation(self):
        """At n=0, employment benefit is zero (no facilities yet)."""
        assert employment_benefit_delta(0) == 0.0

    def test_peaks_at_n0(self):
        """Employment benefit peaks exactly at n=n₀."""
        # At n=n0, delta = L * 1 * exp(0) = L
        assert employment_benefit_delta(10, L=0.15, n0=10) == pytest.approx(0.15)

    def test_bell_shape(self):
        """Benefit rises, peaks, then declines — NOT sigmoid."""
        values = [employment_benefit_delta(n, L=0.15, n0=10) for n in range(0, 51)]
        peak_idx = values.index(max(values))
        assert peak_idx == 10  # Peak at n0
        # Verify decline after peak
        assert values[15] < values[10]
        assert values[30] < values[15]

    def test_decline_after_peak(self):
        """The decline after peak represents community fatigue."""
        at_peak = employment_benefit_delta(10, L=0.15, n0=10)
        at_double = employment_benefit_delta(20, L=0.15, n0=10)
        assert at_double < at_peak

    def test_n0_zero_returns_zero(self):
        """Edge case: n0=0 should return 0 to avoid division by zero."""
        assert employment_benefit_delta(5, n0=0) == 0.0

    def test_always_non_negative(self):
        """Employment benefit is always >= 0."""
        for n in range(0, 100):
            assert employment_benefit_delta(n) >= 0.0


class TestCombinedInterventionDelta:
    def test_sum_of_components(self):
        """Combined delta is the sum of tax + employment deltas."""
        n = 5
        tax = tax_benefit_delta(n, A=0.20, lambda_=0.25)
        emp = employment_benefit_delta(n, L=0.15, n0=10)
        combined = combined_intervention_delta(
            n, tax_A=0.20, tax_lambda=0.25, emp_L=0.15, emp_n0=10
        )
        assert combined == pytest.approx(tax + emp)

    def test_tax_only(self):
        combined = combined_intervention_delta(5, tax_enabled=True, emp_enabled=False)
        assert combined == pytest.approx(tax_benefit_delta(5))

    def test_emp_only(self):
        combined = combined_intervention_delta(5, tax_enabled=False, emp_enabled=True)
        assert combined == pytest.approx(employment_benefit_delta(5))

    def test_neither_enabled(self):
        combined = combined_intervention_delta(5, tax_enabled=False, emp_enabled=False)
        assert combined == 0.0
