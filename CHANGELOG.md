# Changelog

All notable changes to this project will be documented in this file.

<!-- git-cliff-unreleased-start -->
## 3.0.5 - **not yet released**

### 🐛 Bug Fixes

- Fix crash in `Actor.push_data` with PPE and a strict charging limit ([#664](https://github.com/apify/apify-sdk-python/pull/664)) ([8f2e4b2](https://github.com/apify/apify-sdk-python/commit/8f2e4b2cc1f62e9a09656b4d3334caf840338a3a)) by [@janbuchar](https://github.com/janbuchar)
- Avoid charge calls with count=0 ([#665](https://github.com/apify/apify-sdk-python/pull/665)) ([a0f894e](https://github.com/apify/apify-sdk-python/commit/a0f894e879225eb1b639c4f897a1dd0103903c78)) by [@janbuchar](https://github.com/janbuchar)
- Fix Actor.charge behavior when the budget is overdrawn ([#668](https://github.com/apify/apify-sdk-python/pull/668)) ([88e6ba3](https://github.com/apify/apify-sdk-python/commit/88e6ba340a68dcf5e272ee947f4e38ce0f3dea46)) by [@janbuchar](https://github.com/janbuchar)
- Fix detection of whether any instance is initialized ([#675](https://github.com/apify/apify-sdk-python/pull/675)) ([b2355cf](https://github.com/apify/apify-sdk-python/commit/b2355cf697aac6383a404e1bbbefbecd5f38c760)) by [@vdusek](https://github.com/vdusek), closes [#674](https://github.com/apify/apify-sdk-python/issues/674)
- Update apify client to fix rare `JSONDecodeError` ([#679](https://github.com/apify/apify-sdk-python/pull/679)) ([17c13d1](https://github.com/apify/apify-sdk-python/commit/17c13d1ecfbe231fdc4f91c5a24abe65b8abdb26)) by [@Pijukatel](https://github.com/Pijukatel), closes [#672](https://github.com/apify/apify-sdk-python/issues/672)


<!-- git-cliff-unreleased-end -->
## [3.0.4](https://github.com/apify/apify-sdk-python/releases/tag/v3.0.4) (2025-11-03)

### 🐛 Bug Fixes

- Fix type of `cloud_storage_client` in `SmartApifyStorageClient` ([#642](https://github.com/apify/apify-sdk-python/pull/642)) ([3bf285d](https://github.com/apify/apify-sdk-python/commit/3bf285d60f507730954986a80c19ed2e27a38f9c)) by [@vdusek](https://github.com/vdusek)
- Fix local charging log dataset name ([#649](https://github.com/apify/apify-sdk-python/pull/649)) ([fdb1276](https://github.com/apify/apify-sdk-python/commit/fdb1276264aee2687596d87c96d19033fe915823)) by [@vdusek](https://github.com/vdusek), closes [#648](https://github.com/apify/apify-sdk-python/issues/648)

### ⚡ Performance

- Use Apify-provided environment variables to obtain PPE pricing information ([#644](https://github.com/apify/apify-sdk-python/pull/644)) ([0c32f29](https://github.com/apify/apify-sdk-python/commit/0c32f29d6a316f5bacc931595d694f262c925b2b)) by [@Mantisus](https://github.com/Mantisus), closes [#614](https://github.com/apify/apify-sdk-python/issues/614)


## [3.0.3](https://github.com/apify/apify-sdk-python/releases/tag/v3.0.3) (2025-10-21)

### 🐛 Bug Fixes

- Cache requests in RQ implementations by `id` ([#633](https://github.com/apify/apify-sdk-python/pull/633)) ([76886ce](https://github.com/apify/apify-sdk-python/commit/76886ce496165346a01f67e018547287c211ea54)) by [@Pijukatel](https://github.com/Pijukatel), closes [#630](https://github.com/apify/apify-sdk-python/issues/630)


## [3.0.2](https://github.com/apify/apify-sdk-python/releases/tag/v3.0.2) (2025-10-17)

### 🐛 Bug Fixes

- Handle None result in single consumer request queue client ([#623](https://github.com/apify/apify-sdk-python/pull/623)) ([451284a](https://github.com/apify/apify-sdk-python/commit/451284a5c633bc5613bd1e9060df286a1c20b259)) by [@janbuchar](https://github.com/janbuchar), closes [#1472](https://github.com/apify/apify-sdk-python/issues/1472)
- Unify Actor context manager with init &amp; exit methods ([#600](https://github.com/apify/apify-sdk-python/pull/600)) ([6b0d084](https://github.com/apify/apify-sdk-python/commit/6b0d0842ae66a3a206bbb682a3e5f81ad552f029)) by [@vdusek](https://github.com/vdusek), closes [#598](https://github.com/apify/apify-sdk-python/issues/598)
- Handle truncated `unique_key` in `list_head` by fetching full request data ([#631](https://github.com/apify/apify-sdk-python/pull/631)) ([4238086](https://github.com/apify/apify-sdk-python/commit/423808678d9155a84a266bf50bb09f1a56466174)) by [@vdusek](https://github.com/vdusek), closes [#627](https://github.com/apify/apify-sdk-python/issues/627)


## [3.0.1](https://github.com/apify/apify-sdk-python/releases/tag/v3.0.1) (2025-10-08)

### 🐛 Bug Fixes

- Also load input from a file with a .json extension in file system storage ([#617](https://github.com/apify/apify-sdk-python/pull/617)) ([b62804c](https://github.com/apify/apify-sdk-python/commit/b62804c170069cd7aa77572bb9682a156581cbac)) by [@janbuchar](https://github.com/janbuchar)


## [3.0.0](https://github.com/apify/apify-sdk-python/releases/tag/v3.0.0) (2025-09-29)

- Check out the [Upgrading guide](https://docs.apify.com/sdk/python/docs/upgrading/upgrading-to-v3) to ensure a smooth update.

### 🚀 Features

- Add deduplication to `add_batch_of_requests` ([#534](https://github.com/apify/apify-sdk-python/pull/534)) ([dd03c4d](https://github.com/apify/apify-sdk-python/commit/dd03c4d446f611492adf35f1b5738648ee5a66f7)) by [@Pijukatel](https://github.com/Pijukatel), closes [#514](https://github.com/apify/apify-sdk-python/issues/514)
- Add new methods to ChargingManager ([#580](https://github.com/apify/apify-sdk-python/pull/580)) ([54f7f8b](https://github.com/apify/apify-sdk-python/commit/54f7f8b29c5982be98b595dac11eceff915035c9)) by [@vdusek](https://github.com/vdusek)
- Add support for NDU storages ([#594](https://github.com/apify/apify-sdk-python/pull/594)) ([8721ef5](https://github.com/apify/apify-sdk-python/commit/8721ef5731bcb1a04ad63c930089bf83be29f308)) by [@vdusek](https://github.com/vdusek), closes [#1175](https://github.com/apify/apify-sdk-python/issues/1175)
- Add stats to `ApifyRequestQueueClient` ([#574](https://github.com/apify/apify-sdk-python/pull/574)) ([21f6782](https://github.com/apify/apify-sdk-python/commit/21f6782b444f623aba986b4922cf67bafafd4b2c)) by [@Pijukatel](https://github.com/Pijukatel), closes [#1344](https://github.com/apify/apify-sdk-python/issues/1344)
- Add specialized ApifyRequestQueue clients ([#573](https://github.com/apify/apify-sdk-python/pull/573)) ([f830ab0](https://github.com/apify/apify-sdk-python/commit/f830ab09b1fa12189c9d3297d5cf18a4f2da62fa)) by [@Pijukatel](https://github.com/Pijukatel)

### 🐛 Bug Fixes

- Restrict apify-shared and apify-client versions ([#523](https://github.com/apify/apify-sdk-python/pull/523)) ([b3ae5a9](https://github.com/apify/apify-sdk-python/commit/b3ae5a972a65454a4998eda59c9fcc3f6b7e8579)) by [@vdusek](https://github.com/vdusek)
- Expose `APIFY_USER_IS_PAYING` env var to the configuration ([#507](https://github.com/apify/apify-sdk-python/pull/507)) ([0801e54](https://github.com/apify/apify-sdk-python/commit/0801e54887317c1280cc6828ecd3f2cc53287e76)) by [@stepskop](https://github.com/stepskop)
- Resolve DeprecationWarning in ApifyEventManager ([#555](https://github.com/apify/apify-sdk-python/pull/555)) ([0c5111d](https://github.com/apify/apify-sdk-python/commit/0c5111dafe19796ec1fb9652a44c031bed9758df)) by [@vdusek](https://github.com/vdusek), closes [#343](https://github.com/apify/apify-sdk-python/issues/343)
- Use same `client_key` for `Actor` created `request_queue` and improve its metadata estimation ([#552](https://github.com/apify/apify-sdk-python/pull/552)) ([7e4e5da](https://github.com/apify/apify-sdk-python/commit/7e4e5da81dd87e84ebeef2bd336c6c1d422cb9a7)) by [@Pijukatel](https://github.com/Pijukatel), closes [#536](https://github.com/apify/apify-sdk-python/issues/536)
- Properly process pre-existing Actor input file ([#591](https://github.com/apify/apify-sdk-python/pull/591)) ([cc5075f](https://github.com/apify/apify-sdk-python/commit/cc5075fab8c72ca5711cfd97932037b34e6997cd)) by [@Pijukatel](https://github.com/Pijukatel), closes [#590](https://github.com/apify/apify-sdk-python/issues/590)

### Chore

- [**breaking**] Update apify-client and apify-shared to v2.0 ([#548](https://github.com/apify/apify-sdk-python/pull/548)) ([8ba084d](https://github.com/apify/apify-sdk-python/commit/8ba084ded6cd018111343f2219260b481c8d4e35)) by [@vdusek](https://github.com/vdusek)

### Refactor

- [**breaking**] Adapt to the Crawlee v1.0 ([#470](https://github.com/apify/apify-sdk-python/pull/470)) ([f7e3320](https://github.com/apify/apify-sdk-python/commit/f7e33206cf3e4767faacbdc43511b45b6785f929)) by [@vdusek](https://github.com/vdusek), closes [#469](https://github.com/apify/apify-sdk-python/issues/469), [#540](https://github.com/apify/apify-sdk-python/issues/540)
- [**breaking**] Replace `httpx` with `impit` ([#560](https://github.com/apify/apify-sdk-python/pull/560)) ([cca3869](https://github.com/apify/apify-sdk-python/commit/cca3869e85968865e56aafcdcb36fbccba27aef0)) by [@Mantisus](https://github.com/Mantisus), closes [#558](https://github.com/apify/apify-sdk-python/issues/558)
- [**breaking**] Remove `Request.id` field ([#553](https://github.com/apify/apify-sdk-python/pull/553)) ([445ab5d](https://github.com/apify/apify-sdk-python/commit/445ab5d752b785fc2018b35c8adbe779253d7acd)) by [@Pijukatel](https://github.com/Pijukatel)
- [**breaking**] Make `Actor` initialization stricter and more predictable ([#576](https://github.com/apify/apify-sdk-python/pull/576)) ([912222a](https://github.com/apify/apify-sdk-python/commit/912222a7a8123be66c94c50a2e461276fbfc50c4)) by [@Pijukatel](https://github.com/Pijukatel)
- [**breaking**] Make default Apify storages use alias mechanism ([#606](https://github.com/apify/apify-sdk-python/pull/606)) ([dbea7d9](https://github.com/apify/apify-sdk-python/commit/dbea7d97fe7f25aa8658a32c5bb46a3800561df5)) by [@Pijukatel](https://github.com/Pijukatel), closes [#599](https://github.com/apify/apify-sdk-python/issues/599)


## [2.7.3](https://github.com/apify/apify-sdk-python/releases/tag/v2.7.3) (2025-08-11)

### 🐛 Bug Fixes

- Expose `APIFY_USER_IS_PAYING` env var to the configuration (#507) ([0de022c](https://github.com/apify/apify-sdk-python/commit/0de022c3435f24c821053c771e7b659433e3fb6e))


## [2.7.2](https://github.com/apify/apify-sdk-python/releases/tag/v2.7.2) (2025-07-30)

### 🐛 Bug Fixes

- Restrict apify-shared and apify-client versions ([#523](https://github.com/apify/apify-sdk-python/pull/523)) ([581ebae](https://github.com/apify/apify-sdk-python/commit/581ebae5752a984a34cbabc02c49945ae392db00)) by [@vdusek](https://github.com/vdusek)


## [2.7.1](https://github.com/apify/apify-sdk-python/releases/tag/v2.7.1) (2025-07-24)

### 🐛 Bug Fixes

- Add back support for Python 3.9.


## [2.7.0](https://github.com/apify/apify-sdk-python/releases/tag/v2.7.0) (2025-07-14)

### 🚀 Features

- Expose `logger` argument on `Actor.call` to control log redirection from started Actor run ([#487](https://github.com/apify/apify-sdk-python/pull/487)) ([aa6fa47](https://github.com/apify/apify-sdk-python/commit/aa6fa4750ea1bc7909be1191c0d276a2046930c2)) by [@Pijukatel](https://github.com/Pijukatel)
- **crypto:** Decrypt secret objects ([#482](https://github.com/apify/apify-sdk-python/pull/482)) ([ce9daf7](https://github.com/apify/apify-sdk-python/commit/ce9daf7381212b8dc194e8a643e5ca0dedbc0078)) by [@MFori](https://github.com/MFori)


## [2.6.0](https://github.com/apify/apify-sdk-python/releases/tag/v2.6.0) (2025-06-09)

### 🚀 Features

- Add `RemainingTime` option for `timeout` argument of `Actor.call` and `Actor.start` ([#473](https://github.com/apify/apify-sdk-python/pull/473)) ([ba7f757](https://github.com/apify/apify-sdk-python/commit/ba7f757a82661a5a181d9bd767950d09557409f9)) by [@Pijukatel](https://github.com/Pijukatel), closes [#472](https://github.com/apify/apify-sdk-python/issues/472)

### 🐛 Bug Fixes

- Fix duplicate logs from apify logger in Scrapy integration ([#457](https://github.com/apify/apify-sdk-python/pull/457)) ([2745ee6](https://github.com/apify/apify-sdk-python/commit/2745ee6529deecb4f2838c764b9bb3fb6606762b)) by [@vdusek](https://github.com/vdusek), closes [#391](https://github.com/apify/apify-sdk-python/issues/391)
- Prefer proxy password from env var  ([#468](https://github.com/apify/apify-sdk-python/pull/468)) ([1c4ad9b](https://github.com/apify/apify-sdk-python/commit/1c4ad9bcfbf6ac404f942d7d2d249b036c2e7f54)) by [@stepskop](https://github.com/stepskop)


## [2.5.0](https://github.com/apify/apify-sdk-python/releases/tag/v2.5.0) (2025-03-27)

### 🚀 Features

- Implement Scrapy HTTP cache backend  ([#403](https://github.com/apify/apify-sdk-python/pull/403)) ([137e3c8](https://github.com/apify/apify-sdk-python/commit/137e3c8d5c6b28cf6935cfb742b5f072cd2e0a02)) by [@honzajavorek](https://github.com/honzajavorek)

### 🐛 Bug Fixes

- Fix calculation of CPU utilization from SystemInfo events ([#447](https://github.com/apify/apify-sdk-python/pull/447)) ([eb4c8e4](https://github.com/apify/apify-sdk-python/commit/eb4c8e4e498e23f573b9e2d4c7dbd8e2ecc277d9)) by [@janbuchar](https://github.com/janbuchar)


## [2.4.0](https://github.com/apify/apify-sdk-python/releases/tag/v2.4.0) (2025-03-07)

### 🚀 Features

- Update to Crawlee v0.6 ([#420](https://github.com/apify/apify-sdk-python/pull/420)) ([9be4336](https://github.com/apify/apify-sdk-python/commit/9be433667231cc5739861fa693d7a726860d6aca)) by [@vdusek](https://github.com/vdusek)
- Add Actor `exit_process` option ([#424](https://github.com/apify/apify-sdk-python/pull/424)) ([994c832](https://github.com/apify/apify-sdk-python/commit/994c8323b994e009db0ccdcb624891a2fef97070)) by [@vdusek](https://github.com/vdusek), closes [#396](https://github.com/apify/apify-sdk-python/issues/396), [#401](https://github.com/apify/apify-sdk-python/issues/401)
- Upgrade websockets to v14 to adapt to library API changes ([#425](https://github.com/apify/apify-sdk-python/pull/425)) ([5f49275](https://github.com/apify/apify-sdk-python/commit/5f49275ca1177e5ba56856ffe3860f6b97bee9ee)) by [@Mantisus](https://github.com/Mantisus), closes [#325](https://github.com/apify/apify-sdk-python/issues/325)
- Add signing of public URL ([#407](https://github.com/apify/apify-sdk-python/pull/407)) ([a865461](https://github.com/apify/apify-sdk-python/commit/a865461c703aea01d91317f4fdf38c1bedd35f00)) by [@danpoletaev](https://github.com/danpoletaev)


## [2.3.1](https://github.com/apify/apify-sdk-python/releases/tag/v2.3.1) (2025-02-25)

### 🐛 Bug Fixes

- Allow None value in &#x27;inputBodyLen&#x27; in ActorRunStats ([#413](https://github.com/apify/apify-sdk-python/pull/413)) ([1cf37f1](https://github.com/apify/apify-sdk-python/commit/1cf37f13f8db1313ac82276d13200af4aa2bf773)) by [@janbuchar](https://github.com/janbuchar)


## [2.3.0](https://github.com/apify/apify-sdk-python/releases/tag/v2.3.0) (2025-02-19)

### 🚀 Features

- Add `rate_limit_errors` property for `ApifyStorageClient` ([#387](https://github.com/apify/apify-sdk-python/pull/387)) ([89c230a](https://github.com/apify/apify-sdk-python/commit/89c230a21a1a8698159975f97c73a724b9063278)) by [@Mantisus](https://github.com/Mantisus), closes [#318](https://github.com/apify/apify-sdk-python/issues/318)
- Unify Apify and Scrapy to use single event loop &amp; remove `nest-asyncio` ([#390](https://github.com/apify/apify-sdk-python/pull/390)) ([96949be](https://github.com/apify/apify-sdk-python/commit/96949be4f7687ac9285992d1fb02ac6172307bdb)) by [@vdusek](https://github.com/vdusek), closes [#148](https://github.com/apify/apify-sdk-python/issues/148), [#176](https://github.com/apify/apify-sdk-python/issues/176), [#392](https://github.com/apify/apify-sdk-python/issues/392)
- Support pay-per-event via `Actor.charge` ([#393](https://github.com/apify/apify-sdk-python/pull/393)) ([78888c4](https://github.com/apify/apify-sdk-python/commit/78888c4d6258211cdbc5fd5b5cbadbf23c39d818)) by [@janbuchar](https://github.com/janbuchar), closes [#374](https://github.com/apify/apify-sdk-python/issues/374)

### 🐛 Bug Fixes

- Fix RQ usage in Scrapy scheduler ([#385](https://github.com/apify/apify-sdk-python/pull/385)) ([3363478](https://github.com/apify/apify-sdk-python/commit/3363478dbf6eb35e45c237546fe0df5c104166f6)) by [@vdusek](https://github.com/vdusek)
- Make sure that Actor instances with non-default configurations are also accessible through the global Actor proxy after initialization ([#402](https://github.com/apify/apify-sdk-python/pull/402)) ([b956a02](https://github.com/apify/apify-sdk-python/commit/b956a02d0ba59e0cfde489cc13ca92d7f8f8c84f)) by [@janbuchar](https://github.com/janbuchar), closes [#397](https://github.com/apify/apify-sdk-python/issues/397)


## [2.2.1](https://github.com/apify/apify-sdk-python/releases/tag/v2.2.1) (2025-01-17)

### 🐛 Bug Fixes

- Better event listener type definitions ([#354](https://github.com/apify/apify-sdk-python/pull/354)) ([52a6dee](https://github.com/apify/apify-sdk-python/commit/52a6dee92cc0cc4fa032dfc8c312545bc5e07206)) by [@janbuchar](https://github.com/janbuchar), closes [#344](https://github.com/apify/apify-sdk-python/issues/344)


## [2.2.0](https://github.com/apify/apify-sdk-python/releases/tag/v2.2.0) (2025-01-10)

### 🚀 Features

- Add new config variables to `Actor.config` ([#351](https://github.com/apify/apify-sdk-python/pull/351)) ([7b6478c](https://github.com/apify/apify-sdk-python/commit/7b6478c3fc239b454f733fbd98348dab7b3a1766)) by [@fnesveda](https://github.com/fnesveda)
- Upgrade to Crawlee v0.5 ([#355](https://github.com/apify/apify-sdk-python/pull/355)) ([826f4db](https://github.com/apify/apify-sdk-python/commit/826f4dbcc8cfd693d97e40c17faf91d225d7ffaf)) by [@vdusek](https://github.com/vdusek)

### 🐛 Bug Fixes

- Better error message when attempting to use force_cloud without an Apify token ([#356](https://github.com/apify/apify-sdk-python/pull/356)) ([33245ce](https://github.com/apify/apify-sdk-python/commit/33245ceddb1fa0ed39548181fb57fb3e6b98f954)) by [@janbuchar](https://github.com/janbuchar)
- Allow calling `Actor.reboot()` from migrating handler, align reboot behavior with JS SDK ([#361](https://github.com/apify/apify-sdk-python/pull/361)) ([7ba0221](https://github.com/apify/apify-sdk-python/commit/7ba022121fe7b65470fec901295f74cebce72610)) by [@fnesveda](https://github.com/fnesveda)


## [2.1.0](https://github.com/apify/apify-sdk-python/releases/tag/v2.1.0) (2024-12-03)

### 🚀 Features

- Handle request list user input ([#326](https://github.com/apify/apify-sdk-python/pull/326)) ([c14fb9a](https://github.com/apify/apify-sdk-python/commit/c14fb9a9527c8b699e32ed49d39ce0a69447f87c)) by [@Pijukatel](https://github.com/Pijukatel), closes [#310](https://github.com/apify/apify-sdk-python/issues/310)

### 🐛 Bug Fixes

- Add upper bound of HTTPX version ([#347](https://github.com/apify/apify-sdk-python/pull/347)) ([e86dbce](https://github.com/apify/apify-sdk-python/commit/e86dbce69f6978cf2c15910213655e5d80f62a23)) by [@vdusek](https://github.com/vdusek)


## [2.0.2](https://github.com/apify/apify-sdk-python/releases/tag/v2.0.2) (2024-11-12)

### 🐛 Bug Fixes

- Fix CPU usage calculation ([#315](https://github.com/apify/apify-sdk-python/pull/315)) ([0521d91](https://github.com/apify/apify-sdk-python/commit/0521d911afbb8029ad29949f69c4f19166a01fc0)) by [@janbuchar](https://github.com/janbuchar)
- Set version constraint of the `websockets` dependency to &lt;14.0.0 ([#322](https://github.com/apify/apify-sdk-python/pull/322)) ([15ad055](https://github.com/apify/apify-sdk-python/commit/15ad0550e7a5508adff3eb35511248c611a0f595)) by [@Pijukatel](https://github.com/Pijukatel)
- Fix Dataset.iter_items for apify_storage ([#321](https://github.com/apify/apify-sdk-python/pull/321)) ([2db1beb](https://github.com/apify/apify-sdk-python/commit/2db1beb2d56a7e7954cd76023d1273c7546d7cbf)) by [@Pijukatel](https://github.com/Pijukatel), closes [#320](https://github.com/apify/apify-sdk-python/issues/320)


## [2.0.1](https://github.com/apify/apify-sdk-python/releases/tag/v2.0.1) (2024-10-25)

### 🚀 Features

- Add standby URL, change default standby port ([#287](https://github.com/apify/apify-sdk-python/pull/287)) ([8cd2f2c](https://github.com/apify/apify-sdk-python/commit/8cd2f2cb9d1191dbc93bf1b8a2d70189881c64ad)) by [@jirimoravcik](https://github.com/jirimoravcik)
- Add crawlee version to system info print ([#304](https://github.com/apify/apify-sdk-python/pull/304)) ([c28f38f](https://github.com/apify/apify-sdk-python/commit/c28f38f4e205515e1b5d1ce97a2072be3a09d338)) by [@vdusek](https://github.com/vdusek)

### 🐛 Bug Fixes

- Adjust tests of scrapy user data ([#284](https://github.com/apify/apify-sdk-python/pull/284)) ([26ffb15](https://github.com/apify/apify-sdk-python/commit/26ffb15797effcfad1a25c840dd3d17663e26ea3)) by [@janbuchar](https://github.com/janbuchar)
- Use HttpHeaders type in Scrapy integration ([#289](https://github.com/apify/apify-sdk-python/pull/289)) ([3e33e91](https://github.com/apify/apify-sdk-python/commit/3e33e9147bfd60554b9da41b032c0451f91ba27b)) by [@vdusek](https://github.com/vdusek)
- Allow empty timeout_at env variable ([#303](https://github.com/apify/apify-sdk-python/pull/303)) ([b67ec98](https://github.com/apify/apify-sdk-python/commit/b67ec989dfcc21756cc976c52edc25735a3f0501)) by [@janbuchar](https://github.com/janbuchar), closes [#596](https://github.com/apify/apify-sdk-python/issues/596)


## [2.0.0](https://github.com/apify/apify-sdk-python/releases/tag/v2.0.0) (2024-09-10)

- Check out the [Upgrading guide](https://docs.apify.com/sdk/python/docs/upgrading/upgrading-to-v2) to ensure a smooth update.

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

- [**breaking**] Preparation for v2 release ([#210](https://github.com/apify/apify-sdk-python/pull/210)) ([2f9dcc5](https://github.com/apify/apify-sdk-python/commit/2f9dcc559414f31e3f4fc87e72417a36494b9c84)) by [@janbuchar](https://github.com/janbuchar), closes [#135](https://github.com/apify/apify-sdk-python/issues/135), [#137](https://github.com/apify/apify-sdk-python/issues/137), [#138](https://github.com/apify/apify-sdk-python/issues/138), [#147](https://github.com/apify/apify-sdk-python/issues/147), [#149](https://github.com/apify/apify-sdk-python/issues/149), [#237](https://github.com/apify/apify-sdk-python/issues/237)

### Chore

- [**breaking**] Drop support for Python 3.8


## [1.7.2](https://github.com/apify/apify-sdk-python/releases/tag/v1.7.2) (2024-07-08)

- Add Actor Standby port


## [1.7.1](https://github.com/apify/apify-sdk-python/releases/tag/v1.7.1) (2024-05-23)

### 🐛 Bug Fixes

- Set a timeout for Actor cleanup


## [1.7.0](https://github.com/apify/apify-sdk-python/releases/tag/v1.7.0) (2024-03-12)

### 🚀 Features

- Add a new way of generating the `uniqueKey` field of the request, aligning it with the Crawlee.

### 🐛 Bug Fixes

- Improve error handling for `to_apify_request` serialization failures
- Scrapy's `Request.dont_filter` works.


## [1.6.0](https://github.com/apify/apify-sdk-python/releases/tag/v1.6.0) (2024-02-23)

### 🐛 Bug Fixes

- Update of Scrapy integration, fixes in `ApifyScheduler`, `to_apify_request` and `apply_apify_settings`.

### Chore

- Remove `ApifyRetryMiddleware` and stay with the Scrapy's default one


## [1.5.5](https://github.com/apify/apify-sdk-python/releases/tag/v1.5.5) (2024-02-01)

### 🐛 Bug Fixes

- Fix conversion of `headers` fields in Apify <--> Scrapy request translation


## [1.5.4](https://github.com/apify/apify-sdk-python/releases/tag/v1.5.4) (2024-01-24)

### 🐛 Bug Fixes

- Fix conversion of `userData` and `headers` fields in Apify <--> Scrapy request translation


## [1.5.3](https://github.com/apify/apify-sdk-python/releases/tag/v1.5.3) (2024-01-23)

### 🚀 Features

- Add `apply_apify_settings` function to Scrapy subpackage


## [1.5.2](https://github.com/apify/apify-sdk-python/releases/tag/v1.5.2) (2024-01-19)

### 🐛 Bug Fixes

- Add missing import check to `ApifyHttpProxyMiddleware`

### Chore

- Create a new subpackage for Scrapy pipelines
- Remove some noqas thanks to the new Ruff release
- Replace relative imports with absolute imports
- Replace asserts with custom checks in Scrapy subpackage


## [1.5.1](https://github.com/apify/apify-sdk-python/releases/tag/v1.5.1) (2024-01-10)

### Chore

- Allowed running integration tests from PRs from forks, after maintainer approval
- Do not close `nested_event_loop` in the `Scheduler.__del__`


## [1.5.0](https://github.com/apify/apify-sdk-python/releases/tag/v1.5.0) (2024-01-03)

### 🚀 Features

- Add `ApifyHttpProxyMiddleware`


## [1.4.1](https://github.com/apify/apify-sdk-python/releases/tag/v1.4.1) (2023-12-21)

### 🐛 Bug Fixes

- Resolve issue in `ApifyRetryMiddleware.process_exception()`, where requests were getting stuck in the request queue

### Chore

- Fix type hint problems for resource clients


## [1.4.0](https://github.com/apify/apify-sdk-python/releases/tag/v1.4.0) (2023-12-05)

### Chore

- Migrate from Autopep8 and Flake8 to Ruff


## [1.3.0](https://github.com/apify/apify-sdk-python/releases/tag/v1.3.0) (2023-11-15)

### 🚀 Features

- Add `scrapy` extra


## [1.2.0](https://github.com/apify/apify-sdk-python/releases/tag/v1.2.0) (2023-10-23)

### 🚀 Features

- Add support for Python 3.12

### Chore

- Fix lint error (E721) in unit tests (for instance checks use `isinstance()`)


## [1.1.5](https://github.com/apify/apify-sdk-python/releases/tag/v1.1.5) (2023-10-03)

### 🚀 Features

- Update the Apify log formatter to contain an option for adding the logger name

### Chore

- Rewrite documentation publication to use Docusaurus
- Remove PR Toolkit workflow


## [1.1.4](https://github.com/apify/apify-sdk-python/releases/tag/v1.1.4) (2023-09-06)

### 🐛 Bug Fixes

- Resolve issue with querying request queue head multiple times in parallel

### Chore

- Fix integration tests for Actor logger
- Remove `pytest-randomly` Pytest plugin
- Unpin `apify-client` and `apify-shared` to improve compatibility with their newer versions


## [1.1.3](https://github.com/apify/apify-sdk-python/releases/tag/v1.1.3) (2023-08-25)

### Chore

- Unify indentation in configuration files
- Update the `Actor.reboot` method to use the new reboot endpoint


## [1.1.2](https://github.com/apify/apify-sdk-python/releases/tag/v1.1.2) (2023-08-02)

### Chore

- Start importing general constants and utilities from the `apify-shared` library
- Simplify code via `flake8-simplify`
- Start using environment variables with prefix `ACTOR_` instead of some with prefix `APIFY_`
- Pin `apify-client` and `apify-shared` to prevent their implicit updates from breaking SDK


## [1.1.1](https://github.com/apify/apify-sdk-python/releases/tag/v1.1.1) (2023-05-23)

### 🐛 Bug Fixes

- Relax dependency requirements to improve compatibility with other libraries


## [1.1.0](https://github.com/apify/apify-sdk-python/releases/tag/v1.1.0) (2023-05-23)

### 🚀 Features

- Add option to add event handlers which accept no arguments
- Add support for `is_terminal` flag in status message update
- Add option to set status message along with `Actor.exit()`

### 🐛 Bug Fixes

- Start enforcing local storage to always use the UTF-8 encoding
- Fix saving key-value store values to local storage with the right extension for a given content type

### Chore

- Switch from `setup.py` to `pyproject.toml` for specifying project setup


## [1.0.0](https://github.com/apify/apify-sdk-python/releases/tag/v1.0.0) (2023-03-13)

### 🐛 Bug Fixes

- Fix `RequestQueue` not loading requests from an existing queue properly

### Chore

- Update to `apify-client` 1.0.0
- Start triggering base Docker image builds when releasing a new version


## [0.2.0](https://github.com/apify/apify-sdk-python/releases/tag/v0.2.0) (2023-03-06)

### 🚀 Features

- Add chunking mechanism to push_data, cleanup TODOs ([#67](https://github.com/apify/apify-sdk-python/pull/67)) ([5f38d51](https://github.com/apify/apify-sdk-python/commit/5f38d51a57912071439ac88405311d2cb7044190)) by [@jirimoravcik](https://github.com/jirimoravcik)


## [0.1.0](https://github.com/apify/apify-sdk-python/releases/tag/v0.1.0) (2023-02-09)

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