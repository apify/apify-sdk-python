# Changelog

## [1.7.3](../../releases/tag/v1.7.3) - Unreleased

### Added

- Upgrade Apify Client to 1.7.1

## [1.7.2](../../releases/tag/v1.7.2) - 2024-07-08

### Added

- Add Actor Standby port

## [1.7.1](../../releases/tag/v1.7.1) - 2024-05-23

### Fixed

- Set a timeout for Actor cleanup

## [1.7.0](../../releases/tag/v1.7.0) - 2024-03-12

### Added

- Add a new way of generating the `uniqueKey` field of the request, aligning it with the Crawlee.

### Fixed

- Improve error handling for `to_apify_request` serialization failures
- Scrapy's `Request.dont_filter` works.

## [1.6.0](../../releases/tag/v1.6.0) - 2024-02-23

### Fixed

- Update of Scrapy integration, fixes in `ApifyScheduler`, `to_apify_request` and `apply_apify_settings`.

### Removed

- Removed `ApifyRetryMiddleware` and stay with the Scrapy's default one

## [1.5.5](../../releases/tag/v1.5.5) - 2024-02-01

### Fixed

- Fix conversion of `headers` fields in Apify <--> Scrapy request translation

## [1.5.4](../../releases/tag/v1.5.4) - 2024-01-24

### Fixed

- Fix conversion of `userData` and `headers` fields in Apify <--> Scrapy request translation

## [1.5.3](../../releases/tag/v1.5.3) - 2024-01-23

### Added

- Add `apply_apify_settings` function to Scrapy subpackage

## [1.5.2](../../releases/tag/v1.5.2) - 2024-01-19

### Internal changes

- Create a new subpackage for Scrapy pipelines
- Remove some noqas thanks to the new Ruff release
- Replace relative imports with absolute imports
- Replace asserts with custom checks in Scrapy subpackage

### Fixed

- Add missing import check to `ApifyHttpProxyMiddleware`

## [1.5.1](../../releases/tag/v1.5.1) - 2024-01-10

### Internal changes

- Allowed running integration tests from PRs from forks, after maintainer approval
- Do not close `nested_event_loop` in the `Scheduler.__del__`

## [1.5.0](../../releases/tag/v1.5.0) - 2024-01-03

### Added

- Added `ApifyHttpProxyMiddleware`

## [1.4.1](../../releases/tag/v1.4.1) - 2023-12-21

### Fixed

- Resolved issue in `ApifyRetryMiddleware.process_exception()`, where requests were getting stuck in the request queue

### Internal changes

- Fixed type hint problems for resource clients

## [1.4.0](../../releases/tag/v1.4.0) - 2023-12-05

### Internal changes

- Migrate from Autopep8 and Flake8 to Ruff

## [1.3.0](../../releases/tag/v1.3.0) - 2023-11-15

### Added

- Added `scrapy` extra

## [1.2.0](../../releases/tag/v1.2.0) - 2023-10-23

### Added

- Added support for Python 3.12

### Internal changes

- Fix lint error (E721) in unit tests (for instance checks use `isinstance()`)

## [1.1.5](../../releases/tag/v1.1.5) - 2023-10-03

### Added

- Update the Apify log formatter to contain an option for adding the logger name

### Internal changes

- rewrote documentation publication to use Docusaurus
- removed PR Toolkit workflow

## [1.1.4](../../releases/tag/v1.1.4) - 2023-09-06

### Fixed

- resolved issue with querying request queue head multiple times in parallel

### Internal changes

- fixed integration tests for Actor logger
- removed `pytest-randomly` Pytest plugin
- unpinned `apify-client` and `apify-shared` to improve compatibility with their newer versions

## [1.1.3](../../releases/tag/v1.1.3) - 2023-08-25

### Internal changes

- unified indentation in configuration files
- update the `Actor.reboot` method to use the new reboot endpoint

## [1.1.2](../../releases/tag/v1.1.2) - 2023-08-02

### Internal changes

- started importing general constants and utilities from the `apify-shared` library
- simplified code via `flake8-simplify`
- started using environment variables with prefix `ACTOR_` instead of some with prefix `APIFY_`
- pinned `apify-client` and `apify-shared` to prevent their implicit updates from breaking SDK

## [1.1.1](../../releases/tag/v1.1.1) - 2023-05-23

### Fixed

- relaxed dependency requirements to improve compatibility with other libraries

## [1.1.0](../../releases/tag/v1.1.0) - 2023-05-23

### Added

- option to add event handlers which accept no arguments
- added support for `is_terminal` flag in status message update
- option to set status message along with `Actor.exit()`

### Fixed

- started enforcing local storage to always use the UTF-8 encoding
- fixed saving key-value store values to local storage with the right extension for a given content type

### Internal changes

- switched from `setup.py` to `pyproject.toml` for specifying project setup

## [1.0.0](../../releases/tag/v1.0.0) - 2023-03-13

### Internal changes

- updated to `apify-client` 1.0.0
- started triggering base Docker image builds when releasing a new version

### Fixed

- fixed `RequestQueue` not loading requests from an existing queue properly

## [0.2.0](../../releases/tag/v0.2.0) - 2023-03-06

### Breaking changes

- fixed local `MemoryStorageClient` not handling the difference between storage `id` and `name` correctly

### Added

- Added the `KeyValueStore.get_public_url()` method to get public URLs of key-value store records

### Fixed

- fixed parsing messages from the platform events websocket when they have no event data
- fixed `EventManager` not waiting for platform events websocket connection during initialization
- fixed local `RequestQueueClient` not respecting the `forefront` argument
- fixed local `RequestQueueClient` not counting the `handledRequestCount` property
- fixed local storage operations possibly running in parallel
- stopped calling `sys.exit()` in a nested asyncio loop
- stopped purging storages by default

### Internal changes

- started running unit tests in CI on Windows runners in addition to Linux
- added unit tests for environment variables handling
- added unit tests for the `Configuration` class
- added unit tests for the `EventManager` class
- added more Flake8 plugins and fixed issues they reported

## [0.1.0](../../releases/tag/v0.1.0) - 2023-02-09

Initial release of the package.
