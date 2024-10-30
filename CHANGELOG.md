# Changelog

All notable changes to this project will be documented in this file.

## [2.0.1](https://github.com/apify/apify-sdk-python/releases/tags/v2.0.1) (2024-10-25)

### 🚀 Features

- Add standby URL, change default standby port ([#287](https://github.com/apify/apify-sdk-python/pull/287)) ([8cd2f2c](https://github.com/apify/apify-sdk-python/commit/8cd2f2cb9d1191dbc93bf1b8a2d70189881c64ad)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Add crawlee version to system info print ([#304](https://github.com/apify/apify-sdk-python/pull/304)) ([c28f38f](https://github.com/apify/apify-sdk-python/commit/c28f38f4e205515e1b5d1ce97a2072be3a09d338)) by [@vdusek](https://github.com/vdusek)

### 🐛 Bug Fixes

- Adjust tests of scrapy user data ([#284](https://github.com/apify/apify-sdk-python/pull/284)) ([26ffb15](https://github.com/apify/apify-sdk-python/commit/26ffb15797effcfad1a25c840dd3d17663e26ea3)) by [@janbuchar](https://github.com/janbuchar)
- Use HttpHeaders type in Scrapy integration ([#289](https://github.com/apify/apify-sdk-python/pull/289)) ([3e33e91](https://github.com/apify/apify-sdk-python/commit/3e33e9147bfd60554b9da41b032c0451f91ba27b)) by [@vdusek](https://github.com/vdusek)
- Allow empty timeout_at env variable ([#303](https://github.com/apify/apify-sdk-python/pull/303)) ([b67ec98](https://github.com/apify/apify-sdk-python/commit/b67ec989dfcc21756cc976c52edc25735a3f0501)) by [@janbuchar](https://github.com/janbuchar), closes [#596](https://github.com/apify/apify-sdk-python/issues/596)


## [2.0.0](https://github.com/apify/apify-sdk-python/releases/tags/v2.0.0) (2024-09-10)

- Check the [Upgrading to v2.0](https://docs.apify.com/sdk/python/docs/upgrading/upgrading-to-v2) guide.

### 🚀 Features

- Better Actor API typing ([#256](https://github.com/apify/apify-sdk-python/pull/256)) ([abb87e7](https://github.com/apify/apify-sdk-python/commit/abb87e7f3c272f88a9a76292d8394fe93b98428a)) by [@janbuchar](https://github.com/janbuchar), closes [#243](https://github.com/apify/apify-sdk-python/issues/243)
- Expose Request from Crawlee ([#266](https://github.com/apify/apify-sdk-python/pull/266)) ([1f01278](https://github.com/apify/apify-sdk-python/commit/1f01278c77f261500bc74efd700c0583ac45fd82)) by [@vdusek](https://github.com/vdusek)
- Automatically configure logging ([#271](https://github.com/apify/apify-sdk-python/pull/271)) ([1906bb2](https://github.com/apify/apify-sdk-python/commit/1906bb216b8a3f1c2ad740c551ee019c2ba0696f)) by [@janbuchar](https://github.com/janbuchar)

### 🐛 Bug Fixes

- Make apify.log public again ([#249](https://github.com/apify/apify-sdk-python/pull/249)) ([22677f5](https://github.com/apify/apify-sdk-python/commit/22677f57b2aff6c9bddbee305e5a62e39bbf5915)) by [@janbuchar](https://github.com/janbuchar)
- Dataset list response handling ([#257](https://github.com/apify/apify-sdk-python/pull/257)) ([0ea57d7](https://github.com/apify/apify-sdk-python/commit/0ea57d7c4788bff31f215c447c1881e56d6508bb)) by [@janbuchar](https://github.com/janbuchar)
- Ignore deprecated platform events ([#258](https://github.com/apify/apify-sdk-python/pull/258)) ([ed5ab3b](https://github.com/apify/apify-sdk-python/commit/ed5ab3b80c851a817aa87806c39cd8ef3e86fde5)) by [@janbuchar](https://github.com/janbuchar)
- Possible infinity loop in Apify-Scrapy proxy middleware ([#259](https://github.com/apify/apify-sdk-python/pull/259)) ([8647a94](https://github.com/apify/apify-sdk-python/commit/8647a94289423528f2940d9f7174f81682fbb407)) by [@vdusek](https://github.com/vdusek)
- Hotfix for batch_add_requests batch size limit ([#261](https://github.com/apify/apify-sdk-python/pull/261)) ([61d7a39](https://github.com/apify/apify-sdk-python/commit/61d7a392d182a752c91193170dca351f4cb0fbf3)) by [@janbuchar](https://github.com/janbuchar)

### Refactor

- Preparation for v2 release ([#210](https://github.com/apify/apify-sdk-python/pull/210)) ([2f9dcc5](https://github.com/apify/apify-sdk-python/commit/2f9dcc559414f31e3f4fc87e72417a36494b9c84)) by [@janbuchar](https://github.com/janbuchar), closes [#135](https://github.com/apify/apify-sdk-python/issues/135), [#137](https://github.com/apify/apify-sdk-python/issues/137), [#138](https://github.com/apify/apify-sdk-python/issues/138), [#147](https://github.com/apify/apify-sdk-python/issues/147), [#149](https://github.com/apify/apify-sdk-python/issues/149), [#237](https://github.com/apify/apify-sdk-python/issues/237)


## [1.7.2](https://github.com/apify/apify-sdk-python/releases/tags/v1.7.2) (2024-07-08)

### 🚀 Features

- Add actor standby port ([#220](https://github.com/apify/apify-sdk-python/pull/220)) ([6d0d87d](https://github.com/apify/apify-sdk-python/commit/6d0d87dcaedaf42d8eeb7d23c56f6b102434cbcb)) by [@jirimoravcik](https://github.com/jirimoravcik)


## [1.7.1](https://github.com/apify/apify-sdk-python/releases/tags/v1.7.1) (2024-05-23)

### 🐛 Bug Fixes

- Set a timeout for Actor cleanup ([#206](https://github.com/apify/apify-sdk-python/pull/206)) ([cfed57d](https://github.com/apify/apify-sdk-python/commit/cfed57d6cff4fd15fe4b25578573190d53b9942c)) by [@janbuchar](https://github.com/janbuchar), closes [#200](https://github.com/apify/apify-sdk-python/issues/200)



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
