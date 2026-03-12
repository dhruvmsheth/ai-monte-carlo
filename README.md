# What If Tech Corporations Bore the Cost of Consent?

*Modeling Data Center Growth Under Alternative Consent Regimes*

A Monte Carlo simulation modeling U.S. data center growth from 2026–2035 under five community consent scenarios. Built for VC 162 (Values in Computational Thinking).

## Setup

```bash
pip install -e ".[dev]"
pip install addfips requests plotly geopandas
```

## Quick Start

All data is pre-fetched and committed. To reproduce results from scratch:

```bash
# 1. Rebuild data pipeline (feature matrix + XGBoost + all-county extrapolation, ~15 min)
PYTHONPATH=. python scripts/rebuild_data.py

# 2. Run Monte Carlo simulation
PYTHONPATH=. python scripts/run_simulation.py -s all -n 100     # Quick test (~1.5 min)
PYTHONPATH=. python scripts/run_simulation.py -s all -n 10000   # Full research run (~30 min/scenario)

# 3. Generate animated map GIFs
PYTHONPATH=. python scripts/generate_gif.py -s all              # All 5 scenarios (~50 min)
PYTHONPATH=. python scripts/generate_gif.py -s s1               # Single scenario (~10 min)
```

Individual scenarios can be run separately:

```bash
PYTHONPATH=. python scripts/run_simulation.py -s s1 -n 100   # Laissez-faire
PYTHONPATH=. python scripts/run_simulation.py -s s2 -n 100   # Majority (50%)
PYTHONPATH=. python scripts/run_simulation.py -s s3 -n 100   # Supermajority (75%)
PYTHONPATH=. python scripts/run_simulation.py -s s4 -n 100   # Firm consent (50%)
PYTHONPATH=. python scripts/run_simulation.py -s s5 -n 100   # Firm consent (75%)
```

## Outputs

| Output | Path | Description |
|--------|------|-------------|
| Simulation results | `outputs/simulation/{scenario}/` | `aggregate.json`, `monthly_time_series.csv`, `draw_summaries.csv` |
| Map GIFs | `outputs/animation/{scenario}_evolution.gif` | County-level approval + facility builds over 120 months |
| Static maps | `outputs/figures/` | Interactive HTML maps (232 FracTracker + 3,153 all-county) |

## Scenarios

| Scenario | Threshold | Firm-borne | Description |
|----------|-----------|------------|-------------|
| s1_laissez_faire | None | No | Baseline — no consent requirement |
| s2_majority_50 | 50% | No | Simple majority approval needed |
| s3_supermajority_75 | 75% | No | Supermajority approval needed |
| s4_firm_consent_50 | 50% | Yes | Firm invests to achieve 50% approval |
| s5_firm_consent_75 | 75% | Yes | Firm invests to achieve 75% approval |

Plus ±30% sensitivity variants in `configs/scenarios/sensitivity/`.

## Static Maps

```bash
# 232 FracTracker counties + 108 labeled training counties
PYTHONPATH=. python scripts/generate_maps.py

# All 3,153 US counties (extrapolated)
PYTHONPATH=. python scripts/build_full_county_map.py
```

**Caveat:** For ~2,900 greenfield counties, predictions are driven by Census demographics, water stress, and partisan lean only (no facility history). Lower confidence than the 232-county map.

## Data Pipeline (Advanced)

The unified `scripts/rebuild_data.py` handles the full pipeline. To re-fetch individual external datasets from their original APIs:

```bash
PYTHONPATH=. python scripts/fetch_census_acs.py --api-key YOUR_KEY   # Census ACS demographics
PYTHONPATH=. python scripts/fetch_qwi.py                             # Census QWI employment
PYTHONPATH=. python scripts/build_water_stress.py                    # WRI Aqueduct water stress
PYTHONPATH=. python scripts/fetch_eia_electricity.py                 # EIA electricity prices
PYTHONPATH=. python scripts/build_opposition_csv.py                  # Opposition data
```

See [docs/REFERENCE.md](docs/REFERENCE.md) for feature architecture, training configuration, and data source verification.
