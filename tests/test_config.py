"""Tests for src/config.py — loading, merging, validation, serialization."""

import json
from pathlib import Path

import pytest
import yaml

from src.config import (
    ConfigError,
    SimConfig,
    _deep_merge,
    _dict_to_simconfig,
    _validate,
    load_config,
    serialize_run_metadata,
)

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "configs" / "scenarios"
_BASE_YAML = SCENARIOS_DIR.parent / "base.yaml"


def _load_base_dict() -> dict:
    with open(_BASE_YAML) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Deep merge
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_flat_override(self):
        base = {"a": 1, "b": 2}
        overlay = {"b": 99}
        assert _deep_merge(base, overlay) == {"a": 1, "b": 99}

    def test_nested_override(self):
        base = {"x": {"a": 1, "b": 2}, "y": 3}
        overlay = {"x": {"b": 99}}
        assert _deep_merge(base, overlay) == {"x": {"a": 1, "b": 99}, "y": 3}

    def test_new_key(self):
        base = {"a": 1}
        overlay = {"b": 2}
        assert _deep_merge(base, overlay) == {"a": 1, "b": 2}

    def test_does_not_mutate_base(self):
        base = {"x": {"a": 1}}
        overlay = {"x": {"b": 2}}
        _deep_merge(base, overlay)
        assert base == {"x": {"a": 1}}


# ---------------------------------------------------------------------------
# Loading base config
# ---------------------------------------------------------------------------


class TestLoadBase:
    def test_returns_simconfig(self):
        cfg = load_config()
        assert isinstance(cfg, SimConfig)

    def test_base_values(self):
        cfg = load_config()
        assert cfg.simulation.n_steps == 120
        assert cfg.simulation.n_draws == 10000
        assert cfg.simulation.seed == 42
        assert cfg.scenario.name == "base"
        assert cfg.scenario.threshold is None
        assert cfg.scenario.firm_borne is False

    def test_calibration_anchors(self):
        cfg = load_config()
        assert len(cfg.calibration.anchors) == 3
        loudoun = cfg.calibration.anchors[1]
        assert loudoun.fips == "51107"
        assert loudoun.target_p == 0.775

    def test_interventions_disabled_by_default(self):
        cfg = load_config()
        assert cfg.interventions.tax_benefit.enabled is False
        assert cfg.interventions.employment_benefit.enabled is False

    def test_metrics_track_list(self):
        cfg = load_config()
        assert "total_built" in cfg.metrics.track
        assert "gini_coefficient" in cfg.metrics.track


# ---------------------------------------------------------------------------
# Scenario overlay merging
# ---------------------------------------------------------------------------


class TestScenarioOverlay:
    def test_s4_firm_consent_50(self):
        cfg = load_config(SCENARIOS_DIR / "s4_firm_consent_50.yaml")
        assert cfg.scenario.name == "firm_consent_50"
        assert cfg.scenario.threshold == 0.50
        assert cfg.scenario.firm_borne is True
        assert cfg.interventions.tax_benefit.enabled is True
        assert cfg.interventions.employment_benefit.enabled is True

    def test_overlay_preserves_base_values(self):
        cfg = load_config(SCENARIOS_DIR / "s4_firm_consent_50.yaml")
        # These should still come from base.yaml
        assert cfg.simulation.n_steps == 120
        assert cfg.simulation.seed == 42
        assert cfg.approval.provider == "placeholder"

    def test_s1_laissez_faire(self):
        cfg = load_config(SCENARIOS_DIR / "s1_laissez_faire.yaml")
        assert cfg.scenario.threshold is None
        assert cfg.scenario.firm_borne is False

    def test_all_scenario_files_load(self):
        """Every YAML in configs/scenarios/ must load without error."""
        for yaml_file in sorted(SCENARIOS_DIR.glob("*.yaml")):
            cfg = load_config(yaml_file)
            assert isinstance(cfg, SimConfig), f"Failed to load {yaml_file.name}"

    def test_sensitivity_variants_load(self):
        """Sensitivity YAMLs (if any exist) must also load."""
        sensitivity_dir = SCENARIOS_DIR / "sensitivity"
        if sensitivity_dir.exists():
            for yaml_file in sorted(sensitivity_dir.glob("*.yaml")):
                cfg = load_config(yaml_file)
                assert isinstance(cfg, SimConfig), f"Failed to load {yaml_file.name}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invalid_threshold_zero(self):
        """Threshold of 0 should be rejected (must be in (0, 1])."""
        d = _load_base_dict()
        d["scenario"]["threshold"] = 0.0
        with pytest.raises(ConfigError, match="threshold"):
            _validate(_dict_to_simconfig(d))

    def test_invalid_threshold_over_one(self):
        d = _load_base_dict()
        d["scenario"]["threshold"] = 1.5
        with pytest.raises(ConfigError, match="threshold"):
            _validate(_dict_to_simconfig(d))

    def test_invalid_n_draws_zero(self):
        d = _load_base_dict()
        d["simulation"]["n_draws"] = 0
        with pytest.raises(ConfigError, match="n_draws"):
            _validate(_dict_to_simconfig(d))

    def test_invalid_n_steps_negative(self):
        d = _load_base_dict()
        d["simulation"]["n_steps"] = -1
        with pytest.raises(ConfigError, match="n_steps"):
            _validate(_dict_to_simconfig(d))

    def test_threshold_one_is_valid(self):
        """Threshold of exactly 1.0 should be allowed."""
        d = _load_base_dict()
        d["scenario"]["threshold"] = 1.0
        _validate(_dict_to_simconfig(d))  # Should not raise


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_round_trip(self, tmp_path: Path):
        cfg = load_config()
        out = tmp_path / "meta.json"
        serialize_run_metadata(cfg, seed=42, output_path=out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["config"]["simulation"]["n_steps"] == 120
        assert data["config"]["scenario"]["name"] == "base"
        assert data["runtime"]["seed"] == 42
        assert "timestamp" in data["runtime"]

    def test_creates_parent_dirs(self, tmp_path: Path):
        out = tmp_path / "subdir" / "deep" / "meta.json"
        cfg = load_config()
        serialize_run_metadata(cfg, seed=99, output_path=out)
        assert out.exists()
