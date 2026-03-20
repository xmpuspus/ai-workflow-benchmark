.PHONY: install dev lint format test clean validate run compare leaderboard

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

test:
	python3 -m pytest tests/ -v

clean:
	rm -rf results/runs/*
	rm -rf leaderboard/output/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

validate:
	awb validate

run:
	@echo "Usage: awb run <tool> [--task <id>] [--category <cat>]"

compare:
	@echo "Usage: awb compare <run-dir-1> <run-dir-2>"

leaderboard:
	awb leaderboard
