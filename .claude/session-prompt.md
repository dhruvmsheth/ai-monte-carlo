# Session Kickoff

When starting a new session on this project, do the following:

1. Read `CLAUDE.md` for project overview, architecture, and commands
2. Read `docs/IMPLEMENTATION.md` for the detailed data pipeline, simulation design, and known risks — this is the master reference
3. Read `.claude/rules/workflow.md`, `.claude/rules/python.md`, `.claude/rules/testing.md` for coding conventions
4. Run `git status` and `git log --oneline -5` to see current branch and recent work
5. Run `gh issue list --state open` to see the backlog
6. Summarize the current state: what branch you're on, what's been done recently, what issues are open
7. Suggest the next logical issue to implement (respect dependency order below)

If resuming mid-issue, check for any failing tests with `make test` before continuing.

## Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project overview, tech stack, commands, scenarios |
| `docs/IMPLEMENTATION.md` | **Master reference** — data sources, pipeline, simulation pseudocode, viz plan, risks |
| `configs/base.yaml` | All simulation parameters (read this to understand the config structure) |
| `tests/conftest.py` | Shared test fixtures (rng, tiny_counties) |

## Research Phase Dependency Order

Issues are structured as research milestones, not infra tasks. Implement in this order:

```
[Complete] #2 Config system, #3 Scenario YAMLs, #4 Simulation state

[Complete] #16 County Data Foundation
 │   FracTracker ingestion, FIPS mapping, external data enrichment
 │   Output: county_feature_matrix.csv (232 counties × 22 cols), state_shares.csv
 │   External data: WRI Aqueduct 4.0, MIT Election Lab, Census QWI,
 │   Good Jobs First, Bryce/DataCenterWatch, Census ACS, EIA electricity
 │
 ▼
[Complete] #17 Approval Probability Model
 │   XGBoost on 108 labeled counties (81 approved, 27 blocked)
 │   15 structural features (see Feature Architecture below)
 │   Calibration: percentile-rank + FIPS anchor overrides
 │   Beta parameterization: p → Beta(α,β) for simulation sampling
 │   Intervention functions: tax benefit (exp decay) + employment (bell curve)
 │   Placeholder model with hardcoded probs for 25 key counties
 │   Output: county_approval_probs.csv
 │
 ▼
#18 Monte Carlo Simulation Engine  ← NEXT
 │   Candidate generation, monthly simulation loop, firm optimization (LP)
 │   Metrics: Gini, community surplus, firm cost
 │   120 months × 10,000 draws/scenario
 │
 ▼
#19 Scenario Analysis
 │   Runner + CLI, comparative results across 5 consent regimes
 │   Sensitivity analysis (±30%), integration test, reproducibility
 │
 ▼
#20 Visual Storytelling
     Growth trajectories, county heatmap, Gini concentration
     Firm cost vs community benefit, interactive p5.js threshold explorer
```

## Feature Architecture (Issue #17)

XGBoost predicts **structural baseline approval** — how receptive a county is *before* dynamic simulation effects. Saturation/facility count are handled by intervention Δp(n) functions during simulation, NOT by XGBoost. This avoids double-counting.

**15 structural features:**
1. avg_project_mw (FracTracker)
2. hyperscaler_share (FracTracker)
3. pushback_flag (FracTracker + Bryce + DataCenterWatch)
4. state_incentive_score (Good Jobs First + NCSL)
5. dc_employment (Census QWI NAICS 5182)
6. dc_employment_growth (Census QWI 5yr change)
7. water_stress_decile (WRI Aqueduct 4.0)
8. partisan_lean_r (MIT Election Lab 2024)
9. population (Census ACS 2022)
10. population_density (Census ACS + Gazetteer)
11. median_household_income (Census ACS 2022)
12. unemployment_rate (Census ACS 2022)
13. pct_college_educated (Census ACS 2022)
14. ag_employment_share (Census ACS 2022)
15. electricity_price (EIA 2023, state-level)

**Removed from XGBoost** (dynamic features → handled by simulation):
- saturation_count — input to intervention Δp(n), changes every sim step
- facility_count — correlated with saturation, changes during sim
- total_mw — r=0.82 with avg_project_mw, changes during sim

**Training config** (configs/base.yaml): 500 estimators, max_depth=3, lr=0.05, 5-fold CV, scale_pos_weight=auto. Training takes ~8-10 min.

## Simulation Design (Issue #18 — read docs/IMPLEMENTATION.md §4.3)

Each monthly simulation step:
1. Draw candidate facilities from baseline queue (1.3–1.7 GW/month, distributed by state EIA share)
2. Assign each candidate to a county within that state
3. Look up county's BASE approval prob (from XGBoost/calibration)
4. Apply intervention shifts: +Δp_tax(n) + Δp_jobs(n) if firm-borne scenario
5. Apply saturation penalty (dynamic, based on current n)
6. Sample approval share ~ Beta(α, β) where α = p×κ, β = (1−p)×κ
7. If approval share > threshold → build; else → reject (record resistance cost)
8. Update county saturation count, record metrics

Key components to implement:
- `src/simulation/candidate.py` — candidate queue generation + state/county allocation
- `src/simulation/engine.py` — monthly step loop, approval sampling, build/reject logic
- `src/simulation/metrics.py` — Gini coefficient, community surplus, firm cost, resistance cost
- `src/simulation/runner.py` — orchestrate N draws for a scenario, aggregate results

State shares are in `data/external/state_shares.csv` (51 states with facility counts and adjusted shares).

## Completed Code

| Module | Status | Tests |
|--------|--------|-------|
| `src/config.py` | Complete | 21 tests |
| `src/simulation/state.py` | Complete | 9 tests |
| `src/data/ingest.py` | Complete | 32 tests |
| `src/data/features.py` | Complete | 19 tests |
| `src/model/protocol.py` | Complete | 5 tests |
| `src/model/placeholder.py` | Complete | 8 tests |
| `src/model/calibration.py` | Complete | 7 tests |
| `src/model/xgboost_model.py` | Complete | 10 tests |
| `src/interventions/functions.py` | Complete | 15 tests |
| Scenario YAMLs (9 files) | Complete | 17 tests |

## Workflow for Each Issue

1. `gh issue view N` — read the issue
2. `git checkout -b feature/issue-N-description main`
3. Implement with tests (see `.claude/rules/testing.md`)
4. `make test` and `make lint` must pass
5. Commit: `git commit -m "feat(module): description (#N)"`
6. Push + PR: `git push -u origin <branch>` then `gh pr create`
7. Merge PR, update main locally
8. Write a natural-language narrative explaining what was built and why it matters

## Important Design Decisions

- **FracTracker CSV** is in `data/raw/` (1,380 rows; filter to >100MW = 337 facilities, 232 counties)
- **Approval model:** XGBoost only for probability output; feature importances for interpretability
- **Employment benefit curve** is bell-shaped: `L × (n/n₀) × exp(1 - n/n₀)`, NOT sigmoid
- **Explicit RNG:** Always pass `rng: np.random.Generator`, never global seed
- **Config-driven:** All params in YAML, scenarios are overlays on `configs/base.yaml`
- **FIPS mapping:** Use `addfips` library to map county+state → 5-digit FIPS
- **Cooling type feature is unusable** (98% empty) — use water_stress as proxy instead
- **No linting required** during development — user will clean up later
- **Training is slow** (~8-10 min with full config) — use fast config (n_estimators=20, cv_folds=3) in tests
