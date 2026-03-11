# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Speculative algorithm design project for VC 162 (Values in Computational Thinking). Models U.S. data center growth (2026–2035) under alternative community consent regimes via Monte Carlo simulation. Final deliverable: a data journalism article (~1200–1600 words) with 3–5 interactive visualizations.

**Research question:** What if tech corporations bore the cost of obtaining local consent for data center construction, rather than communities bearing the cost of resistance?

**Status:** Phase 1 — Implementing research pipeline (config + state complete, data ingestion next).

## Research Phases

The project is organized as 5 research milestones (#16–#20), not infra tasks:

1. **County Data Foundation** (#16) — FracTracker ingestion, FIPS mapping, external data enrichment (Census QWI, water stress, partisan lean, state incentives, opposition data). Output: county feature matrix.
2. **Approval Probability Model** (#17) — XGBoost on ~108 labeled counties for probability output + feature importances for interpretability. Calibration via anchor points → Beta(α,β) per county. Intervention functions (tax decay, employment bell curve). Placeholder model for Phase 1.
3. **Monte Carlo Simulation** (#18) — Candidate generation, monthly simulation loop, firm optimization (LP), metrics (Gini, surplus, firm cost). 120 months × 10,000 draws/scenario.
4. **Scenario Analysis** (#19) — Runner + CLI, comparative results across 5 consent regimes, sensitivity analysis, integration test.
5. **Visual Storytelling** (#20) — Growth trajectories, county heatmap, Gini concentration, cost-benefit, interactive p5.js threshold explorer.

## Key Modules

- `src/config.py` — YAML config loading with base + scenario overlay merge (complete)
- `src/simulation/state.py` — Mutable state dataclasses for Monte Carlo draws (complete)
- `src/data/` — FracTracker ingestion, feature engineering, external data
- `src/model/` — XGBoost approval model, calibration, placeholder
- `src/interventions/` — Tax benefit (exponential decay) and employment benefit (bell curve)
- `src/simulation/` — Engine, candidate queue, metrics, runner
- `src/viz/` — Matplotlib figures; JSON export for p5.js interactive

## Tech Stack

Python 3.11+ | numpy, pandas, scipy, xgboost, scikit-learn, matplotlib, seaborn, pyyaml | pytest, ruff

## Commands

```bash
make test              # Run pytest
make lint              # Ruff check + format check
make format            # Auto-format with ruff
make run SCENARIO=s1_laissez_faire  # Run a scenario
```

## Scenarios (configs/scenarios/)

| Scenario | Threshold | Firm-borne |
|----------|-----------|------------|
| s1_laissez_faire | None | No |
| s2_majority_50 | 50% | No |
| s3_supermajority_75 | 75% | No |
| s4_firm_consent_50 | 50% | Yes |
| s5_firm_consent_75 | 75% | Yes |

Plus ±30% sensitivity variants in `configs/scenarios/sensitivity/`.

## Key Conventions

- All tunable parameters in YAML configs, never hardcoded in Python
- Explicit RNG: pass `rng: np.random.Generator`, never use global `np.random.seed()`
- County-level analysis keyed by FIPS code
- Approval model: XGBoost for probability output, feature importances for interpretability. Protocol interface shared by placeholder and real models.
- Use `gemini -p` for bulk web research and data source exploration
