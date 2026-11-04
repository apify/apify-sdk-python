import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        env = Actor.get_env()

        Actor.log.info(f'Actor ID: {env.get("id")}')
        Actor.log.info(f'Run ID: {env.get("run_id")}')
        Actor.log.info(f'Default dataset ID: {env.get("default_dataset_id")}')
        Actor.log.info(f'Default KVS ID: {env.get("default_key_value_store_id")}')


if __name__ == '__main__':
    asyncio.run(main())
