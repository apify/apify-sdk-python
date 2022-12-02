.PHONY: clean install-dev lint test type-check check-code format docs check-docs

clean:
	rm -rf build dist .mypy_cache .pytest_cache src/*.egg-info __pycache__

install-dev:
	python -m pip install --upgrade pip
	pip install --upgrade setuptools wheel
	pip install --no-cache-dir -e ".[dev]"

lint:
	python3 -m flake8

test:
	python3 -m pytest -rA tests

type-check:
	python3 -m mypy

check-code: lint type-check test

format:
	python3 -m isort src tests
	python3 -m autopep8 --in-place --recursive src tests

docs:
	./docs/res/build.sh

check-docs:
	./docs/res/check.sh
