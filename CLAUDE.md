# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Speculative algorithm design project for VC 162 (Values in Computational Thinking). Models U.S. data center growth (2026–2035) under alternative community consent regimes via Monte Carlo simulation. Final deliverable: a data journalism article (~1200–1600 words) with 3–5 interactive visualizations.

**Research question:** What if tech corporations bore the cost of obtaining local consent for data center construction, rather than communities bearing the cost of resistance?

**Status:** Phase 1 — Building simulation engine with placeholder approval probabilities.

## Architecture

Three-stage pipeline:
1. **Approval Model** (`src/model/`) — XGBoost + logistic regression on ~60–80 county observations. Phase 1 uses `placeholders.py`.
2. **Anchor Calibration** (`src/model/calibration.py`) — Linear rescaling → Beta(α,β) per county.
3. **Monte Carlo Simulation** (`src/simulation/`) — 120 monthly steps, 10,000 draws/scenario.

Supporting modules:
- `src/config.py` — YAML config loading with base + scenario overlay merge
- `src/interventions/` — Tax benefit (exponential decay) and employment benefit (bell curve)
- `src/viz/` — Matplotlib trajectories, heatmaps, tables; JSON export for p5.js

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
- Approval model accessed via protocol interface (placeholder/xgboost/logistic)
- Use `gemini -p` for bulk web research and data source exploration
