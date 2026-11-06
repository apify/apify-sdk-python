import asyncio
import os

from apify import Actor, ApifyEnvVars


async def main() -> None:
    async with Actor:
        config = Actor.configuration

        Actor.log.info(f'Actor ID: {config.actor_id}')
        Actor.log.info(f'Run ID: {config.actor_run_id}')
        Actor.log.info(f'Default dataset ID: {config.default_dataset_id}')
        Actor.log.info(f'Default KVS ID: {config.default_key_value_store_id}')

        # Variables the configuration does not expose are read from the environment.
        latest_sdk_version = os.environ.get(ApifyEnvVars.SDK_LATEST_VERSION)
        Actor.log.info(f'Latest SDK version: {latest_sdk_version}')


if __name__ == '__main__':
    asyncio.run(main())
