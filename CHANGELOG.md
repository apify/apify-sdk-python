Changelog
=========

[1.1.0](../../releases/tag/v1.1.0) - Unreleased
-----------------------------------------------

### Added

- option to add event handlers which accept no arguments
- added support for `is_terminal` flag in status message update
- option to set status message along with `Actor.exit()`

### Fixed

- started enforcing local storage to always use the UTF-8 encoding
- fixed saving key-value store values to local storage with the right extension for a given content type

[1.0.0](../../releases/tag/v1.0.0) - 2022-03-13
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
