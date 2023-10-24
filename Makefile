.PHONY: clean install-dev build publish twine-check lint unit-tests integration-tests type-check check-code format check-version-availability check-changelog-entry build-api-reference

# This is default for local testing, but GitHub workflows override it to a higher value in CI
INTEGRATION_TESTS_CONCURRENCY = 1

clean:
	rm -rf build dist .mypy_cache .pytest_cache src/*.egg-info __pycache__

install-dev:
	python -m pip install --upgrade pip
	pip install --no-cache-dir -e ".[dev]"
	pre-commit install

build:
	python -m build

publish:
	python -m twine upload dist/*

twine-check:
	python -m twine check dist/*

lint:
	python3 -m flake8

unit-tests:
	python3 -m pytest -n auto -ra tests/unit

integration-tests:
	python3 -m pytest -n $(INTEGRATION_TESTS_CONCURRENCY) -ra tests/integration

type-check:
	python3 -m mypy

check-code: lint type-check unit-tests

format:
	python3 -m isort src tests
	python3 -m autopep8 --in-place --recursive src tests

check-version-availability:
	python3 scripts/check_version_availability.py

check-changelog-entry:
	python3 scripts/check_version_in_changelog.py

build-api-reference:
	cd website && ./build_api_reference.sh
