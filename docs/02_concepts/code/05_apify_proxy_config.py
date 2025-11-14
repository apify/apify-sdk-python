import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        proxy_cfg = await Actor.create_proxy_configuration(
            groups=['RESIDENTIAL'],
            country_code='US',
        )

        if not proxy_cfg:
            raise RuntimeError('No proxy configuration available.')

        proxy_url = await proxy_cfg.new_url()
        Actor.log.info(f'Proxy URL: {proxy_url}')


if __name__ == '__main__':
    asyncio.run(main())
