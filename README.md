# What If Tech Corporations Bore the Cost of Consent?

*Modeling Data Center Growth Under Alternative Consent Regimes*

A Monte Carlo simulation modeling U.S. data center growth from 2026–2035 under five community consent scenarios. Built for VC 162 (Values in Computational Thinking).

## Setup

```bash
pip install -e ".[dev]"
pip install addfips requests plotly geopandas
```

## Data Pipeline

All external data is pre-fetched and committed. To rebuild from scratch:

```bash
# 1. Rebuild FracTracker → county feature matrix (no API needed)
PYTHONPATH=. python -c "
from src.data.ingest import run_ingestion
from src.data.features import build_feature_matrix
result = run_ingestion()
build_feature_matrix(result['county'], output_path='data/processed/county_feature_matrix.csv')
"

# 2. Re-fetch Census ACS demographics (requires Census API key)
PYTHONPATH=. python scripts/fetch_census_acs.py --api-key YOUR_KEY

# 3. Re-fetch Census QWI employment (requires Census API key)
PYTHONPATH=. python scripts/fetch_qwi.py

# 4. Rebuild water stress from WRI Aqueduct shapefiles
PYTHONPATH=. python scripts/build_water_stress.py

# 5. EIA electricity prices (hardcoded from EIA tables, no API needed)
PYTHONPATH=. python scripts/fetch_eia_electricity.py

# 6. Rebuild opposition data
PYTHONPATH=. python scripts/build_opposition_csv.py
```

## Training the XGBoost Model

```bash
# Train model, calibrate, save county probabilities
PYTHONPATH=. python scripts/train_model.py

# Output: data/processed/county_approval_probs.csv
```

### Training Configuration (configs/base.yaml)

Current config prioritizes accuracy over speed:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| max_depth | 3 | Shallow trees prevent overfitting on 108 samples |
| n_estimators | 500 | High count + early stopping finds optimal point |
| learning_rate | 0.05 | Low rate + many trees = better generalization |
| early_stopping_rounds | 20 | Stops if validation loss plateaus for 20 rounds |
| min_child_weight | 3 | Requires 3+ samples per leaf (prevents memorization) |
| subsample | 0.8 | 80% row sampling per tree (reduces variance) |
| colsample_bytree | 0.8 | 80% feature sampling per tree |
| reg_alpha | 0.1 | L1 regularization (sparse feature selection) |
| reg_lambda | 1.0 | L2 regularization (smooth weights) |
| cv_folds | 5 | 5-fold stratified CV for AUC evaluation |
| scale_pos_weight | auto | Set to n_blocked/n_approved = 27/81 ≈ 0.33 |

Expected training time: ~8-10 minutes (500 estimators × 5-fold CV × 3 train phases).

### Feature Architecture

The XGBoost model predicts **structural baseline approval** — how receptive a county is to data centers before any dynamic simulation effects. Dynamic features (saturation, facility count) are handled by intervention functions during simulation, not by XGBoost.

**15 structural features:**

| # | Feature | Source | Coverage | What It Captures |
|---|---------|--------|----------|-----------------|
| 1 | avg_project_mw | FracTracker MW column | 232 counties | Project size/visibility |
| 2 | hyperscaler_share | FracTracker operator column | 232 counties | Who's building (Big Tech vs colo) |
| 3 | pushback_flag | FracTracker + Bryce Rejection DB + DataCenterWatch | 47 opposition cases | Community opposition capacity |
| 4 | state_incentive_score | Good Jobs First Nov 2025 + NCSL | 51 states | Policy friendliness |
| 5 | dc_employment | Census QWI NAICS 5182 (2020-2025) | 2,007 counties | Existing DC workforce |
| 6 | dc_employment_growth | Census QWI NAICS 5182 (5yr change) | 1,102 counties | Workforce trajectory |
| 7 | water_stress_decile | WRI Aqueduct 4.0 (area-weighted spatial join) | 3,144 counties | Environmental strain |
| 8 | partisan_lean_r | MIT Election Lab 2024 presidential | 3,151 counties | Political baseline |
| 9 | population | Census ACS 5-Year 2022 (B01003) | 3,222 counties | County size |
| 10 | population_density | Census ACS + Gazetteer (pop/sq mi) | 3,222 counties | Urban/suburban/rural character |
| 11 | median_household_income | Census ACS 5-Year 2022 (B19013) | 3,222 counties | Economic capacity to resist |
| 12 | unemployment_rate | Census ACS 5-Year 2022 (B23025) | 3,222 counties | Receptivity to jobs argument |
| 13 | pct_college_educated | Census ACS 5-Year 2022 (B15003) | 3,222 counties | Organized opposition capacity |
| 14 | ag_employment_share | Census ACS 5-Year 2022 (DP03) | 3,222 counties | Rural/agricultural economy |
| 15 | electricity_price | EIA Electric Power Monthly 2023 | 51 states | Grid strain concern |

**Why saturation_count was removed from XGBoost:** The proposal's Section 4.3 specifies that during simulation, p_county = base_probability + Δp_tax(n) + Δp_jobs(n) − saturation_penalties. Saturation is a *dynamic* variable that changes every simulation step as facilities are built. If XGBoost also learns saturation effects internally, the penalty gets applied twice. The intervention functions (tax benefit exponential decay, employment bell curve) already model how saturation affects approval. XGBoost's job is to predict the *structural baseline* from features that don't change during the 10-year simulation.

**Why pushback_flag was kept:** Despite being the most predictive feature (~21% importance), it's not tautological with the outcome — 34 of 81 approved counties also have documented pushback. It captures *organized opposition capacity* as a structural property: activist groups exist, media attention has been established, and board precedent has been set. This is a durable community characteristic, not a dynamic simulation variable.

### Data Source Verification

All external data was fetched from real APIs and public datasets:

| Dataset | How Obtained | Verifiable? |
|---------|-------------|-------------|
| Census ACS | `scripts/fetch_census_acs.py` — live API call to `api.census.gov/data/2022/acs/acs5` | Yes — rerun script with API key, compare output |
| Census QWI | `scripts/fetch_qwi.py` — live API call to `api.census.gov/data/timeseries/qwi` | Yes — cached JSON in `data/raw/qwi/` |
| WRI Aqueduct | `scripts/build_water_stress.py` — spatial join of WRI shapefiles × county boundaries | Yes — requires WRI Aqueduct 4.0 download |
| Partisan lean | Downloaded from tonmcg GitHub (MIT Election Lab 2024 results) | Yes — `data/external/partisan_lean.csv` |
| Opposition | `scripts/build_opposition_csv.py` — 47 cases from Bryce DB + DataCenterWatch + news | Partially — 4 manually verified, 43 from web research |
| State incentives | `data/external/state_incentives.csv` — Good Jobs First + NCSL survey | Yes — scores derived from public incentive databases |
| EIA electricity | `scripts/fetch_eia_electricity.py` — hardcoded from EIA Electric Power Monthly tables | Yes — cross-check at eia.gov/electricity/monthly |

**Nothing is fabricated.** Every dataset has a fetch/build script that reproduces it from the original source. The one partial exception is opposition data (47 cases), where 43 were sourced by web research and may contain errors in specific counties.

## Visualizing Results

```bash
# 232 FracTracker counties
PYTHONPATH=. python scripts/interactive_map.py

# All 3,153 US counties (extrapolated — see caveat below)
PYTHONPATH=. python scripts/build_full_county_map.py
```

**Caveat on the full map:** For ~2,900 greenfield counties, the model predicts from structural features only (no facility history). The top FracTracker-derived features (pushback_flag, avg_project_mw, hyperscaler_share) are all zero for these counties. Predictions are driven primarily by Census demographics, water stress, and partisan lean — reasonable but lower confidence than the 232-county map.

## Scenarios

| Scenario | Threshold | Firm-borne |
|----------|-----------|------------|
| s1_laissez_faire | None | No |
| s2_majority_50 | 50% | No |
| s3_supermajority_75 | 75% | No |
| s4_firm_consent_50 | 50% | Yes |
| s5_firm_consent_75 | 75% | Yes |

Plus ±30% sensitivity variants in `configs/scenarios/sensitivity/`.
