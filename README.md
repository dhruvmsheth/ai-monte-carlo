# What If Tech Corporations Bore the Cost of Consent?

*Modeling Data Center Growth Under Alternative Consent Regimes*

A Monte Carlo simulation modeling U.S. data center growth from 2026–2035 under five community consent scenarios, from laissez-faire permitting to firm-borne consent mechanisms. Built for VC 162 (Values in Computational Thinking).

## Quick Start

```bash
# Install project + dependencies (uses pyproject.toml)
pip install -e ".[dev]"

# Also install extra dependencies for data pipeline and visualization
pip install addfips requests plotly geopandas

# Verify everything works
make test
make lint
```

## Training the Approval Model

The XGBoost model predicts county-level approval probability for data center proposals, trained on 108 labeled counties from the FracTracker database.

```bash
# Train XGBoost + calibrate + save county probabilities
PYTHONPATH=. python scripts/train_model.py

# Output: data/processed/county_approval_probs.csv
# Prints: CV AUC, feature importances, calibration info
```

**Model details:**
- Training set: 108 counties (81 approved, 27 blocked)
- 5-fold stratified CV AUC: ~0.70
- Top features: saturation_count (32%), pushback_flag (21%), avg_project_mw (15%)
- Calibrated to national median 44% (Heatmap/Embold 2025 survey)
- Anchor overrides: Loudoun VA → 77.5%, Prince William VA → 25%

## Visualizing Approval Probabilities

### Interactive map (232 FracTracker counties)
```bash
PYTHONPATH=. python scripts/interactive_map.py
# Opens: outputs/figures/approval_map.html
```

### Full US county map (3,144 counties)
```bash
PYTHONPATH=. python scripts/build_full_county_map.py
# Opens: outputs/figures/full_approval_map.html
```

The full map extends predictions to all US counties by using external features (water stress, partisan lean, state incentives, QWI employment) and setting facility features to 0 for non-FracTracker counties.

## Data Pipeline

### 1. FracTracker Ingestion
Raw CSV → clean → FIPS mapping → tier classification → county aggregation.
```bash
# Already run — outputs in data/processed/
# county_facilities.csv: 232 counties with facility features
# county_feature_matrix.csv: 232 counties × 14 features
```

### 2. External Data Sources
| Dataset | Source | Counties | File |
|---------|--------|----------|------|
| Water stress | WRI Aqueduct 4.0 | 3,144 | `data/external/water_stress.csv` |
| Partisan lean | MIT Election Lab 2024 | 3,151 | `data/external/partisan_lean.csv` |
| State incentives | Good Jobs First + NCSL | 51 | `data/external/state_incentives.csv` |
| DC employment | Census QWI NAICS 5182 | 2,007 | `data/external/qwi_employment.csv` |
| Opposition data | Bryce + DataCenterWatch | 47 | `data/external/opposition.csv` |

### 3. Rebuilding External Data (optional)
```bash
# Re-fetch Census QWI employment data (requires API key in script)
PYTHONPATH=. python scripts/fetch_qwi.py

# Rebuild opposition CSV from researched cases
PYTHONPATH=. python scripts/build_opposition_csv.py

# Rebuild water stress from WRI Aqueduct shapefiles
PYTHONPATH=. python scripts/build_water_stress.py
```

## Scenarios

| Scenario | Threshold | Firm-borne | Config |
|----------|-----------|------------|--------|
| s1_laissez_faire | None | No | `configs/scenarios/s1_laissez_faire.yaml` |
| s2_majority_50 | 50% | No | `configs/scenarios/s2_majority_50.yaml` |
| s3_supermajority_75 | 75% | No | `configs/scenarios/s3_supermajority_75.yaml` |
| s4_firm_consent_50 | 50% | Yes | `configs/scenarios/s4_firm_consent_50.yaml` |
| s5_firm_consent_75 | 75% | Yes | `configs/scenarios/s5_firm_consent_75.yaml` |

Plus ±30% sensitivity variants in `configs/scenarios/sensitivity/`.

```bash
make run SCENARIO=s1_laissez_faire
```

## Development

```bash
make test              # Run pytest (143+ tests)
make lint              # Ruff check + format check
make format            # Auto-format with ruff
```

## Project Structure

```
src/
  config.py            # YAML config loading, validation, frozen dataclasses
  data/
    ingest.py          # FracTracker ingestion, FIPS mapping, aggregation
    features.py        # External data enrichment and feature matrix
  model/
    protocol.py        # ApprovalModel protocol + Beta parameterization
    placeholder.py     # Hardcoded probabilities for 25 key counties
    calibration.py     # Percentile-rank calibration with anchor overrides
    xgboost_model.py   # XGBoost training, CV, calibration, prediction
  interventions/
    functions.py       # Tax benefit (exp decay) + employment benefit (bell curve)
  simulation/
    state.py           # Mutable state dataclasses for Monte Carlo draws
configs/
  base.yaml            # All simulation parameters
  scenarios/           # 5 main + 4 sensitivity YAML overlays
tests/                 # 143+ tests mirroring src/ structure
scripts/
  train_model.py       # Train XGBoost and save probabilities
  interactive_map.py   # Generate Plotly choropleth (232 counties)
  build_full_county_map.py  # Full US map (3,144 counties)
  fetch_qwi.py         # Census QWI API fetcher
  build_opposition_csv.py   # Opposition data builder
data/
  raw/                 # FracTracker CSV, QWI cache
  external/            # Water stress, partisan lean, incentives, opposition, QWI
  processed/           # County features, approval probabilities
outputs/
  figures/             # Interactive HTML maps
```
