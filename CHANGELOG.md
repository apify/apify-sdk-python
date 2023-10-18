Changelog
=========

[1.1.6](../../releases/tag/v1.1.6) - Unreleased
-----------------------------------------------

### Internal changes

- Fix lint error (E721) in unit tests (for instance checks use `isinstance()`)

[1.1.5](../../releases/tag/v1.1.5) - 2023-10-03
-----------------------------------------------

### Added

- Update the Apify log formatter to contain an option for adding the logger name

### Internal changes

- rewrote documentation publication to use Docusaurus
- removed PR Toolkit workflow

[1.1.4](../../releases/tag/v1.1.4) - 2023-09-06
-----------------------------------------------

### Fixed

- resolved issue with querying request queue head multiple times in parallel

### Internal changes

- fixed integration tests for Actor logger
- removed `pytest-randomly` Pytest plugin
- unpinned `apify-client` and `apify-shared` to improve compatibility with their newer versions

[1.1.3](../../releases/tag/v1.1.3) - 2023-08-25
-----------------------------------------------

### Internal changes

- unified indentation in configuration files
- update the `Actor.reboot` method to use the new reboot endpoint

[1.1.2](../../releases/tag/v1.1.2) - 2023-08-02
-----------------------------------------------

### Internal changes

- started importing general constants and utilities from the `apify-shared` library
- simplified code via `flake8-simplify`
- started using environment variables with prefix `ACTOR_` instead of some with prefix `APIFY_`
- pinned `apify-client` and `apify-shared` to prevent their implicit updates from breaking SDK

[1.1.1](../../releases/tag/v1.1.1) - 2023-05-23
-----------------------------------------------

### Fixed

- relaxed dependency requirements to improve compatibility with other libraries

[1.1.0](../../releases/tag/v1.1.0) - 2023-05-23
-----------------------------------------------

### Added

- option to add event handlers which accept no arguments
- added support for `is_terminal` flag in status message update
- option to set status message along with `Actor.exit()`

### Fixed

- started enforcing local storage to always use the UTF-8 encoding
- fixed saving key-value store values to local storage with the right extension for a given content type

### Internal changes

- switched from `setup.py` to `pyproject.toml` for specifying project setup

[1.0.0](../../releases/tag/v1.0.0) - 2023-03-13
-----------------------------------------------

### Internal changes

- updated to `apify-client` 1.0.0
- started triggering base Docker image builds when releasing a new version

### Fixed

- fixed `RequestQueue` not loading requests from an existing queue properly

[0.2.0](../../releases/tag/v0.2.0) - 2023-03-06
-----------------------------------------------

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

[0.1.0](../../releases/tag/v0.1.0) - 2023-02-09
-----------------------------------------------

Initial release of the package.
