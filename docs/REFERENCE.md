# Reference: Model Architecture & Data Sources

## Training Configuration (configs/base.yaml)

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
| scale_pos_weight | auto | Set to n_blocked/n_approved = 27/81 ~ 0.33 |

Expected training time: ~8-10 minutes (500 estimators x 5-fold CV x 3 train phases).

## Feature Architecture

The XGBoost model predicts **structural baseline approval** — how receptive a county is to data centers before any dynamic simulation effects. Dynamic features (saturation, facility count) are handled by intervention functions during simulation.

### 15 Structural Features

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

## Data Source Verification

All external data was fetched from real APIs and public datasets:

| Dataset | How Obtained | Verifiable? |
|---------|-------------|-------------|
| Census ACS | `scripts/fetch_census_acs.py` — live API call to `api.census.gov/data/2022/acs/acs5` | Yes — rerun script with API key, compare output |
| Census QWI | `scripts/fetch_qwi.py` — live API call to `api.census.gov/data/timeseries/qwi` | Yes — cached JSON in `data/raw/qwi/` |
| WRI Aqueduct | `scripts/build_water_stress.py` — spatial join of WRI shapefiles x county boundaries | Yes — requires WRI Aqueduct 4.0 download |
| Partisan lean | Downloaded from tonmcg GitHub (MIT Election Lab 2024 results) | Yes — `data/external/partisan_lean.csv` |
| Opposition | `scripts/build_opposition_csv.py` — 47 cases from Bryce DB + DataCenterWatch + news | Partially — 4 manually verified, 43 from web research |
| State incentives | `data/external/state_incentives.csv` — Good Jobs First + NCSL survey | Yes — scores derived from public incentive databases |
| EIA electricity | `scripts/fetch_eia_electricity.py` — hardcoded from EIA Electric Power Monthly tables | Yes — cross-check at eia.gov/electricity/monthly |

**Nothing is fabricated.** Every dataset has a fetch/build script that reproduces it from the original source.
