# What If Tech Corporations Bore the Cost of Consent?

*Modeling Data Center Growth Under Alternative Consent Regimes*

A Monte Carlo simulation modeling U.S. data center growth from 2026–2035 under five community consent scenarios, from laissez-faire permitting to firm-borne consent mechanisms.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
make test                              # Run tests
make lint                              # Check code style
make run SCENARIO=s1_laissez_faire     # Run a scenario
```

## Project Structure

- `src/` — Simulation code (config, data, model, interventions, simulation, viz)
- `configs/` — YAML scenario definitions
- `tests/` — pytest test suite
- `viz/` — p5.js interactive visualization
- `data/` — Raw, processed, and external datasets
