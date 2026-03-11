# Testing Rules

## Framework
- `pytest` with fixtures in `tests/conftest.py`
- Run with: `make test` (or `python -m pytest tests/ -v`)

## Deterministic Testing
- Every mathematical function (intervention curves, Beta parameterization, Gini, surplus) has deterministic unit tests
- Monte Carlo / simulation tests use seeded `np.random.default_rng(seed=12345)` via the `rng` fixture
- Same seed + same config = same output, always

## Required Fixtures (conftest.py)
- `rng` — seeded Generator for reproducible randomness
- `tiny_counties` — 3 counties with known features for fast tests
- `base_config` — loaded from configs/base.yaml

## Test Categories
- **Unit tests**: each mathematical function in isolation (interventions, metrics, calibration)
- **Integration test**: end-to-end simulation with 100 draws, must complete in < 30 seconds
- **Config tests**: every YAML in configs/scenarios/ must load and validate without error

## Coverage Expectations
- Every new function that computes a value must have at least one test
- Edge cases: n=0 saturation, threshold=1.0, empty county set, single-county scenarios
