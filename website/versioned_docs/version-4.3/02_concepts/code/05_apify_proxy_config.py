import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        proxy_cfg = await Actor.create_proxy_configuration(
            groups=['RESIDENTIAL'],
            country_code='US',
            subdivision_code='CA',
        )

        if not proxy_cfg:
            Actor.log.warning('Apify Proxy is not available, exiting...')
            return

        proxy_url = await proxy_cfg.new_url()
        Actor.log.info(f'Proxy URL: {proxy_url}')


if __name__ == '__main__':
    asyncio.run(main())
