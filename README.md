# Apify SDK for Python

Apify SDK is the core set of tools and utilities that we've built to help make your interaction with the [Apify Platform](https://apify.com) easier.
It's still under heavy development, check back in a few weeks if you want to use it!

## Installation

Requires Python 3.8+

You can install the package from its [PyPI listing](https://pypi.org/project/apify).
To do that, simply run `pip install apify` in your terminal.

## Usage

For usage instructions, check the documentation on [Apify Docs](https://docs.apify.com/sdk/python/) or in [`docs/docs.md`](docs/docs.md).

## Development

### Environment

For local development, it is required to have Python 3.8 installed.

It is recommended to set up a virtual environment while developing this package to isolate your development environment,
however, due to the many varied ways Python can be installed and virtual environments can be set up,
this is left up to the developers to do themselves.

One recommended way is with the built-in `venv` module:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

To improve on the experience, you can use [pyenv](https://github.com/pyenv/pyenv) to have an environment with a pinned Python version,
and [direnv](https://github.com/direnv/direnv) to automatically activate/deactivate the environment when you enter/exit the project folder.

### Dependencies

To install this package and its development dependencies, run `make install-dev`

### Formatting

We use `autopep8` and `isort` to automatically format the code to a common format. To run the formatting, just run `make format`.

### Linting, type-checking and unit testing

We use `flake8` for linting, `mypy` for type checking and `pytest` for unit testing. To run these tools, just run `make check-code`.

### Integration tests

We have integration tests which build and run actors using the Python SDK on the Apify Platform.
To run these tests, you need to set the `APIFY_TEST_USER_API_TOKEN` environment variable to the API token of the Apify user you want to use for the tests,
and then start them with `make integration-tests`.

If you want to run the integration tests on a different environment than the main Apify Platform,
you need to set the `APIFY_INTEGRATION_TESTS_API_URL` environment variable to the right URL to the Apify API you want to use.

### Documentation

We use the [Google docstring format](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html) for documenting the code.
We document every user-facing class or method, and enforce that using the flake8-docstrings library.

The documentation is then rendered from the docstrings in the code using Sphinx and some heavy post-processing and saved as `docs/docs.md`.
To generate the documentation, just run `make docs`.

### Release process

Publishing new versions to [PyPI](https://pypi.org/project/apify) happens automatically through GitHub Actions.

On each commit to the `master` branch, a new beta release is published, taking the version number from `src/apify/_version.py`
and automatically incrementing the beta version suffix by 1 from the last beta release published to PyPI.

A stable version is published when a new release is created using GitHub Releases, again taking the version number from `src/apify/_version.py`. The built package assets are automatically uploaded to the GitHub release.

If there is already a stable version with the same version number as in `src/apify/_version.py` published to PyPI, the publish process fails,
so don't forget to update the version number before releasing a new version.
The release process also fails when the released version is not described in `CHANGELOG.md`,
so don't forget to describe the changes in the new version there.
