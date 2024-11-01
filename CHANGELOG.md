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


## [1.1.2](https://github.com/apify/apify-sdk-python/releases/tags/v1.1.2) (2023-08-02)

### 🚀 Features

- Use Actor env vars ([#105](https://github.com/apify/apify-sdk-python/pull/105)) ([f0ba351](https://github.com/apify/apify-sdk-python/commit/f0ba35103eb9efbf39ea394d390430c849bf127c)) by [@jirimoravcik](https://github.com/jirimoravcik)


## [1.1.0](https://github.com/apify/apify-sdk-python/releases/tags/v1.1.0) (2023-05-23)

### 🚀 Features

- Use test user token from organisation secrets ([#90](https://github.com/apify/apify-sdk-python/pull/90)) ([7826a38](https://github.com/apify/apify-sdk-python/commit/7826a382d7a3c0a1531b3a7bb73369e2801e6fa0)) by [@drobnikj](https://github.com/drobnikj)


## [0.2.0](https://github.com/apify/apify-sdk-python/releases/tags/v0.2.0) (2023-03-06)

### 🚀 Features

- Add chunking mechanism to push_data, cleanup TODOs ([#67](https://github.com/apify/apify-sdk-python/pull/67)) ([5f38d51](https://github.com/apify/apify-sdk-python/commit/5f38d51a57912071439ac88405311d2cb7044190)) by [@jirimoravcik](https://github.com/jirimoravcik)


## [0.1.0](https://github.com/apify/apify-sdk-python/releases/tags/v0.1.0) (2023-02-09)

### 🚀 Features

- Implement MemoryStorage and local storage clients ([#15](https://github.com/apify/apify-sdk-python/pull/15)) ([b7c9886](https://github.com/apify/apify-sdk-python/commit/b7c98869bdc749feadc7b5a0d105fce041506011)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Implement Dataset, KeyValueStore classes, create storage management logic ([#21](https://github.com/apify/apify-sdk-python/pull/21)) ([d1b357c](https://github.com/apify/apify-sdk-python/commit/d1b357cd02f7357137fd9413b105a8ac48b1796b)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Implement RequestQueue class ([#25](https://github.com/apify/apify-sdk-python/pull/25)) ([c6cad34](https://github.com/apify/apify-sdk-python/commit/c6cad3442d1a9a37c3eb3991cf45daed03e74ff5)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Add test for get_env and is_at_home ([#29](https://github.com/apify/apify-sdk-python/pull/29)) ([cc45afb](https://github.com/apify/apify-sdk-python/commit/cc45afbf848db3626054c599cb3a5a2972a48748)) by [@drobnikj](https://github.com/drobnikj)
- Updating pull request toolkit config [INTERNAL] ([387143c](https://github.com/apify/apify-sdk-python/commit/387143ccf2c32a99c95e9931e5649e558d35daeb)) by [@mtrunkat](https://github.com/mtrunkat)
- Add documentation for `StorageManager` and `StorageClientManager`, open_* methods in `Actor` ([#34](https://github.com/apify/apify-sdk-python/pull/34)) ([3f6b942](https://github.com/apify/apify-sdk-python/commit/3f6b9426dc03fea40d80af2e4c8f04ecf2620e8a)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Add tests for actor lifecycle ([#35](https://github.com/apify/apify-sdk-python/pull/35)) ([4674728](https://github.com/apify/apify-sdk-python/commit/4674728905be5076283ff3795332866e8bef6ee8)) by [@drobnikj](https://github.com/drobnikj)
- Add docs for `Dataset`, `KeyValueStore`, and `RequestQueue` ([#37](https://github.com/apify/apify-sdk-python/pull/37)) ([174548e](https://github.com/apify/apify-sdk-python/commit/174548e952b47ee519d1a05c0821a2c42c2fddf6)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Docs string for memory storage clients ([#31](https://github.com/apify/apify-sdk-python/pull/31)) ([8f55d46](https://github.com/apify/apify-sdk-python/commit/8f55d463394307b004193efc43b67b44d030f6de)) by [@drobnikj](https://github.com/drobnikj)
- Add test for storage actor methods ([#39](https://github.com/apify/apify-sdk-python/pull/39)) ([b89bbcf](https://github.com/apify/apify-sdk-python/commit/b89bbcfdcae4f436a68e92f1f60628aea1036dde)) by [@drobnikj](https://github.com/drobnikj)
- Various fixes and improvements ([#41](https://github.com/apify/apify-sdk-python/pull/41)) ([5bae238](https://github.com/apify/apify-sdk-python/commit/5bae238821b3b63c73d0cbadf4b478511cb045d2)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Add the rest unit tests for actor ([#40](https://github.com/apify/apify-sdk-python/pull/40)) ([72d92ea](https://github.com/apify/apify-sdk-python/commit/72d92ea080670ceecc234c149058d2ebe763e3a8)) by [@drobnikj](https://github.com/drobnikj)
- Decrypt input secrets if there are some ([#45](https://github.com/apify/apify-sdk-python/pull/45)) ([6eb1630](https://github.com/apify/apify-sdk-python/commit/6eb163077341218a3f9dcf566986d7464f6ab09e)) by [@drobnikj](https://github.com/drobnikj)
- Add a few integration tests ([#48](https://github.com/apify/apify-sdk-python/pull/48)) ([1843f48](https://github.com/apify/apify-sdk-python/commit/1843f48845e724e1c2682b8d09a6b5c48c57d9ec)) by [@drobnikj](https://github.com/drobnikj)
- Add integration tests for storages, proxy configuration ([#49](https://github.com/apify/apify-sdk-python/pull/49)) ([fd0566e](https://github.com/apify/apify-sdk-python/commit/fd0566ed3b8c85c7884f8bba3cf7394215fabed0)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Unify datetime handling, remove utcnow() ([#52](https://github.com/apify/apify-sdk-python/pull/52)) ([09dd8ac](https://github.com/apify/apify-sdk-python/commit/09dd8ac9dc26afee777f497ed1d2733af1eef848)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Separate ID and name params for `Actor.open_xxx` ([#56](https://github.com/apify/apify-sdk-python/pull/56)) ([a1e962e](https://github.com/apify/apify-sdk-python/commit/a1e962ebe74384baabb96fdbb4f0e0ed2f92e454)) by [@jirimoravcik](https://github.com/jirimoravcik)

### 🐛 Bug Fixes

- Key error for storage name ([#28](https://github.com/apify/apify-sdk-python/pull/28)) ([83b30a9](https://github.com/apify/apify-sdk-python/commit/83b30a90df4d3b173302f1c6006b346091fced60)) by [@drobnikj](https://github.com/drobnikj)


<!-- generated by git-cliff -->