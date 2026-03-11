.PHONY: test lint format run

test:
	python -m pytest tests/ -v

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/

run:
	python -m src.simulation.runner --scenario configs/scenarios/$(SCENARIO).yaml
