.PHONY: install compile test lint run demo clean

install:
	pip install -e ".[dev]"

compile:
	python -m vehiclepassport.chain.compile

test:
	pytest --cov=vehiclepassport --cov-report=term-missing

lint:
	ruff check vehiclepassport tests

run:
	uvicorn vehiclepassport.main:app --reload --port 8000

demo:
	python -m vehiclepassport.cli demo

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
