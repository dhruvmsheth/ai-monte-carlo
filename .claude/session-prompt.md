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

## Phase 1 Issue Dependency Order

Implement in this order (earlier issues unblock later ones):

```
#2 Config system ──→ #3 Scenario YAMLs
       │
       ├──→ #4 Simulation state
       │
       ├──→ #5 Placeholder model
       │
       ├──→ #6 Intervention functions
       │
       └──→ #7 Candidate queue
                │
                └──→ #8 Simulation engine ──→ #9 Metrics ──→ #10 Runner ──→ #11 Viz ──→ #12 Integration test
```

Issue #1 (scaffolding) is already done.

## Workflow for Each Issue

1. `gh issue view N` — read the issue
2. `git checkout -b feature/issue-N-description main`
3. Implement with tests (see `.claude/rules/testing.md`)
4. `make test` and `make lint` must pass
5. Commit: `git commit -m "feat(module): description (#N)"`
6. Push + PR: `git push -u origin <branch>` then `gh pr create`

## Important Design Decisions (from docs/IMPLEMENTATION.md)

- **FracTracker CSV** is in `data/raw/` (1,380 rows; filter to >100MW = 337 facilities for modeling)
- **Employment benefit curve** is bell-shaped: `L × (n/n₀) × exp(1 - n/n₀)`, NOT sigmoid
- **Dual model:** XGBoost + logistic regression, common `ApprovalModel` protocol
- **Explicit RNG:** Always pass `rng: np.random.Generator`, never global seed
- **Config-driven:** All params in YAML, scenarios are overlays on `configs/base.yaml`
- **FIPS mapping:** Use `addfips` library to map county+state → 5-digit FIPS
- **Cooling type feature is unusable** (98% empty) — use water_stress as proxy instead
