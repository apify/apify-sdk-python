Changelog
=========

[0.2.0](../../releases/tag/v0.2.0) - Upcoming
---------------------------------------------

### Breaking changes

- fixed local `MemoryStorageClient` not handling the difference between storage `id` and `name` correctly

### Fixed

- fixed parsing messages from the platform events websocket when they have no event data
- fixed `EventManager` not waiting for platform events websocket connection during initialization
- fixed local `RequestQueueClient` not respecting the `forefront` argument
- fixed local `RequestQueueClient` not counting the `handledRequestCount` property

### Internal changes

- started running unit tests in CI on Windows runners in addition to Linux
- added unit tests for environment variables handling
- added unit tests for the `Configuration` class
- added unit tests for the `EventManager` class
- added more Flake8 plugins and fixed issues they reported

[0.1.0](../../releases/tag/v0.1.0) - 2023-02-09
-----------------------------------------------

Initial release of the package.
