# Python Rules

## Language & Style
- Python 3.11+
- Type hints on all function signatures
- Line length: 100 characters (configured in pyproject.toml)
- Linter/formatter: `ruff`

## Project Structure
- `src/` — all application code (importable as `src.*`)
- `tests/` — all test files (mirror src/ structure with `test_` prefix)
- `configs/` — YAML configuration files (never hardcode tunable parameters in Python)

## Randomness
- Always use `np.random.default_rng(seed)` for reproducible randomness
- Pass `rng: np.random.Generator` explicitly to any function that needs randomness
- Never use `np.random.seed()` or global random state
- Derive per-draw seeds deterministically: `draw_seed = master_seed + draw_id`

## Data Handling
- All county-level data keyed by FIPS code (string, zero-padded to 5 digits)
- DataFrame validation at ingestion boundaries (src/data/schemas.py)
- Missing data: assign sensible defaults (e.g., 0 for missing QWI employment), never silently drop rows

## Configuration
- All simulation parameters, model hyperparameters, and intervention coefficients live in `configs/base.yaml`
- Scenarios are YAML overlays that deep-merge onto base
- `src/config.py` loads, merges, validates, and exposes a frozen dataclass
