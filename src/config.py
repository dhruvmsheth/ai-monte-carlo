"""Configuration system: YAML loading, deep merge, validation, serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BASE_CONFIG_PATH = _PROJECT_ROOT / "configs" / "base.yaml"


# ---------------------------------------------------------------------------
# Dataclasses mirroring configs/base.yaml
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulationConfig:
    n_steps: int = 120
    n_draws: int = 10000
    start_year: int = 2026
    start_month: int = 1
    seed: int = 42
    monthly_gw_addition: float = 1.5
    geographic_substitution_prob: float = 0.5


@dataclass(frozen=True)
class CandidateQueueConfig:
    allocation: str = "eia_share"
    avg_project_mw: float = 300.0
    pipeline_dropout_rate: float = 0.50
    existing_facility_weight: float = 3.0


@dataclass(frozen=True)
class ApprovalConfig:
    provider: str = "placeholder"
    beta_concentration: float = 40.0


@dataclass(frozen=True)
class XGBoostConfig:
    max_depth: int = 3
    n_estimators: int = 500
    learning_rate: float = 0.05
    early_stopping_rounds: int = 20
    min_child_weight: int = 3
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    cv_folds: int = 5


@dataclass(frozen=True)
class LogisticConfig:
    penalty: str = "l2"
    C: float = 1.0
    cv_folds: int = 5


@dataclass(frozen=True)
class ModelConfig:
    type: str = "xgboost"
    xgboost: XGBoostConfig = field(default_factory=XGBoostConfig)
    logistic: LogisticConfig = field(default_factory=LogisticConfig)


@dataclass(frozen=True)
class CalibrationAnchor:
    name: str = ""
    target_p: float = 0.5
    type: str | None = None
    fips: str | None = None


@dataclass(frozen=True)
class CalibrationConfig:
    method: str = "linear"
    clip_min: float = 0.05
    clip_max: float = 0.95
    anchors: tuple[CalibrationAnchor, ...] = ()


@dataclass(frozen=True)
class TaxBenefitConfig:
    enabled: bool = False
    A: float = 0.20
    lambda_: float = 0.25
    cost_per_gw_million: float = 405.8


@dataclass(frozen=True)
class EmploymentBenefitConfig:
    enabled: bool = False
    L: float = 0.15
    n0: int = 10
    construction_jobs_per_gw: int = 45367
    permanent_jobs_per_gw: int = 5322


@dataclass(frozen=True)
class InterventionsConfig:
    tax_benefit: TaxBenefitConfig = field(default_factory=TaxBenefitConfig)
    employment_benefit: EmploymentBenefitConfig = field(default_factory=EmploymentBenefitConfig)


@dataclass(frozen=True)
class ScenarioConfig:
    name: str = "base"
    threshold: float | None = None
    firm_borne: bool = False


@dataclass(frozen=True)
class MetricsConfig:
    track: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimConfig:
    """Top-level frozen configuration mirroring configs/base.yaml."""

    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    candidate_queue: CandidateQueueConfig = field(default_factory=CandidateQueueConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    interventions: InterventionsConfig = field(default_factory=InterventionsConfig)
    scenario: ScenarioConfig = field(default_factory=ScenarioConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)


# ---------------------------------------------------------------------------
# Deep merge
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *overlay* onto *base*, returning a new dict."""
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# Dict → dataclass conversion
# ---------------------------------------------------------------------------


def _build_simulation(d: dict[str, Any]) -> SimulationConfig:
    return SimulationConfig(**d)


def _build_candidate_queue(d: dict[str, Any]) -> CandidateQueueConfig:
    return CandidateQueueConfig(**d)


def _build_approval(d: dict[str, Any]) -> ApprovalConfig:
    return ApprovalConfig(**d)


def _build_model(d: dict[str, Any]) -> ModelConfig:
    raw = dict(d)
    xgb = XGBoostConfig(**raw.pop("xgboost", {}))
    log = LogisticConfig(**raw.pop("logistic", {}))
    return ModelConfig(xgboost=xgb, logistic=log, **raw)


def _build_calibration(d: dict[str, Any]) -> CalibrationConfig:
    raw = dict(d)
    anchors = tuple(CalibrationAnchor(**a) for a in raw.pop("anchors", []))
    return CalibrationConfig(anchors=anchors, **raw)


def _build_interventions(d: dict[str, Any]) -> InterventionsConfig:
    raw = dict(d)
    # Handle YAML key `lambda` → Python field `lambda_`
    tax_raw = dict(raw.get("tax_benefit", {}))
    if "lambda" in tax_raw:
        tax_raw["lambda_"] = tax_raw.pop("lambda")
    tax = TaxBenefitConfig(**tax_raw)
    emp = EmploymentBenefitConfig(**raw.get("employment_benefit", {}))
    return InterventionsConfig(tax_benefit=tax, employment_benefit=emp)


def _build_scenario(d: dict[str, Any]) -> ScenarioConfig:
    return ScenarioConfig(**d)


def _build_metrics(d: dict[str, Any]) -> MetricsConfig:
    raw = dict(d)
    track = tuple(raw.pop("track", []))
    return MetricsConfig(track=track, **raw)


def _dict_to_simconfig(d: dict[str, Any]) -> SimConfig:
    return SimConfig(
        simulation=_build_simulation(d.get("simulation", {})),
        candidate_queue=_build_candidate_queue(d.get("candidate_queue", {})),
        approval=_build_approval(d.get("approval", {})),
        model=_build_model(d.get("model", {})),
        calibration=_build_calibration(d.get("calibration", {})),
        interventions=_build_interventions(d.get("interventions", {})),
        scenario=_build_scenario(d.get("scenario", {})),
        metrics=_build_metrics(d.get("metrics", {})),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


def _validate(cfg: SimConfig) -> None:
    """Validate a fully-built SimConfig; raises ConfigError on problems."""
    errors: list[str] = []

    # simulation
    if cfg.simulation.n_draws <= 0:
        errors.append("simulation.n_draws must be > 0")
    if cfg.simulation.n_steps <= 0:
        errors.append("simulation.n_steps must be > 0")
    if not isinstance(cfg.simulation.seed, int):
        errors.append("simulation.seed must be an integer")

    # scenario threshold
    thr = cfg.scenario.threshold
    if thr is not None:
        if not (0.0 < thr <= 1.0):
            errors.append("scenario.threshold must be None or a float in (0, 1]")

    # calibration clips
    if not (0.0 <= cfg.calibration.clip_min < cfg.calibration.clip_max <= 1.0):
        errors.append("calibration.clip_min/clip_max must satisfy 0 <= min < max <= 1")

    if errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(errors))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(scenario_path: str | Path | None = None) -> SimConfig:
    """Load base.yaml and optionally deep-merge a scenario overlay.

    Parameters
    ----------
    scenario_path : path to a scenario YAML overlay, or None for base only.

    Returns
    -------
    SimConfig — a frozen dataclass tree.
    """
    with open(_BASE_CONFIG_PATH) as f:
        base_dict: dict[str, Any] = yaml.safe_load(f)

    if scenario_path is not None:
        with open(scenario_path) as f:
            overlay_dict: dict[str, Any] = yaml.safe_load(f)
        merged = _deep_merge(base_dict, overlay_dict)
    else:
        merged = base_dict

    cfg = _dict_to_simconfig(merged)
    _validate(cfg)
    return cfg


def serialize_run_metadata(cfg: SimConfig, seed: int, output_path: str | Path) -> None:
    """Write merged config + runtime info to a JSON file.

    Parameters
    ----------
    cfg : The merged SimConfig.
    seed : The master RNG seed used for the run.
    output_path : Destination JSON file path.
    """
    import dataclasses

    def _to_dict(obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
        if isinstance(obj, (list, tuple)):
            return [_to_dict(item) for item in obj]
        return obj

    metadata = {
        "config": _to_dict(cfg),
        "runtime": {
            "seed": seed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)
