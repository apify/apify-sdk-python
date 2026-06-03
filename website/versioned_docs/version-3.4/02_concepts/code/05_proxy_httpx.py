import asyncio

import httpx

from apify import Actor


async def main() -> None:
    async with Actor:
        proxy_cfg = await Actor.create_proxy_configuration(
            proxy_urls=[
                'http://proxy-1.com',
                'http://proxy-2.com',
            ],
        )

        if not proxy_cfg:
            raise RuntimeError('No proxy configuration available.')

        proxy_url = await proxy_cfg.new_url()

        async with httpx.AsyncClient(proxy=proxy_url) as httpx_client:
            response = await httpx_client.get('http://example.com')
            Actor.log.info(f'Response: {response}')


if __name__ == '__main__':
    asyncio.run(main())
