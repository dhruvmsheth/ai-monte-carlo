"""Tests for scenario YAML files — loading, merging, and sensitivity coefficient verification."""

from pathlib import Path

import pytest

from src.config import SimConfig, load_config

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "configs" / "scenarios"
SENSITIVITY_DIR = SCENARIOS_DIR / "sensitivity"

# Collect all scenario YAML paths for parameterized testing
_ALL_SCENARIO_YAMLS = sorted(SCENARIOS_DIR.glob("*.yaml"))
_ALL_SENSITIVITY_YAMLS = sorted(SENSITIVITY_DIR.glob("*.yaml")) if SENSITIVITY_DIR.exists() else []


# ---------------------------------------------------------------------------
# Parameterized: every scenario YAML loads and merges without error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "yaml_path",
    _ALL_SCENARIO_YAMLS + _ALL_SENSITIVITY_YAMLS,
    ids=lambda p: p.stem,
)
def test_scenario_loads_and_validates(yaml_path: Path):
    cfg = load_config(yaml_path)
    assert isinstance(cfg, SimConfig)
    assert cfg.scenario.name != "base", f"{yaml_path.stem} should override scenario.name"


# ---------------------------------------------------------------------------
# Sensitivity variants: ±30% of base intervention coefficients
# ---------------------------------------------------------------------------

# Base values from configs/base.yaml
_BASE_A = 0.20
_BASE_LAMBDA = 0.25
_BASE_L = 0.15


@pytest.mark.parametrize(
    "filename, direction",
    [
        ("s4_high.yaml", "high"),
        ("s4_low.yaml", "low"),
        ("s5_high.yaml", "high"),
        ("s5_low.yaml", "low"),
    ],
)
def test_sensitivity_coefficients(filename: str, direction: str):
    """Sensitivity overlays apply ±30% to intervention coefficients."""
    cfg = load_config(SENSITIVITY_DIR / filename)

    factor = 1.3 if direction == "high" else 0.7
    expected_a = _BASE_A * factor
    expected_lambda = _BASE_LAMBDA * factor
    expected_l = _BASE_L * factor

    assert cfg.interventions.tax_benefit.A == pytest.approx(expected_a, abs=1e-6)
    assert cfg.interventions.tax_benefit.lambda_ == pytest.approx(expected_lambda, abs=1e-6)
    assert cfg.interventions.employment_benefit.L == pytest.approx(expected_l, abs=1e-6)


# ---------------------------------------------------------------------------
# Scenario-specific invariants
# ---------------------------------------------------------------------------


class TestScenarioInvariants:
    def test_laissez_faire_no_threshold(self):
        cfg = load_config(SCENARIOS_DIR / "s1_laissez_faire.yaml")
        assert cfg.scenario.threshold is None
        assert cfg.scenario.firm_borne is False

    def test_majority_thresholds(self):
        s2 = load_config(SCENARIOS_DIR / "s2_majority_50.yaml")
        s3 = load_config(SCENARIOS_DIR / "s3_supermajority_75.yaml")
        assert s2.scenario.threshold == 0.50
        assert s3.scenario.threshold == 0.75
        assert s2.scenario.firm_borne is False
        assert s3.scenario.firm_borne is False

    def test_firm_borne_scenarios_enable_interventions(self):
        for name in ("s4_firm_consent_50.yaml", "s5_firm_consent_75.yaml"):
            cfg = load_config(SCENARIOS_DIR / name)
            assert cfg.scenario.firm_borne is True
            assert cfg.interventions.tax_benefit.enabled is True
            assert cfg.interventions.employment_benefit.enabled is True

    def test_non_firm_scenarios_disable_interventions(self):
        for name in (
            "s1_laissez_faire.yaml",
            "s2_majority_50.yaml",
            "s3_supermajority_75.yaml",
        ):
            cfg = load_config(SCENARIOS_DIR / name)
            assert cfg.interventions.tax_benefit.enabled is False
            assert cfg.interventions.employment_benefit.enabled is False
