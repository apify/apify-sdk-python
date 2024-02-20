.PHONY: clean install-dev build publish twine-check lint unit-tests integration-tests type-check check-code format check-version-availability check-changelog-entry build-api-reference

DIRS_WITH_CODE = src tests scripts

# This is default for local testing, but GitHub workflows override it to a higher value in CI
INTEGRATION_TESTS_CONCURRENCY = 1

clean:
	rm -rf build dist .mypy_cache .pytest_cache src/*.egg-info __pycache__

install-dev:
	pip install poetry
	poetry config virtualenvs.create true --local
	poetry config virtualenvs.in-project true --local
	poetry install --all-extras
	poetry run pre-commit install

build:
	poetry run python -m build

publish:
	poetry run twine upload dist/*

twine-check:
	poetry run twine check dist/*

lint:
	poetry run ruff check $(DIRS_WITH_CODE)

unit-tests:
	poetry run pytest -n auto -ra tests/unit --cov=src/apify

unit-tests-cov:
	poetry run pytest -n auto -ra tests/unit --cov=src/apify --cov-report=html

integration-tests:
	poetry run pytest -n $(INTEGRATION_TESTS_CONCURRENCY) -ra tests/integration

type-check:
	poetry run mypy $(DIRS_WITH_CODE)

check-code: lint type-check unit-tests

format:
	poetry run ruff check --fix $(DIRS_WITH_CODE)
	poetry run ruff format $(DIRS_WITH_CODE)

check-version-availability:
	python3 scripts/check_version_availability.py

check-changelog-entry:
	python3 scripts/check_version_in_changelog.py

build-api-reference:
	cd website && ./build_api_reference.sh
