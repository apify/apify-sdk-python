import asyncio

from apify import Actor, ProxyConfiguration


async def main() -> None:
    async with Actor:
        # Create a proxy configuration with tiered proxy URLs.
        # The proxy rotator starts with the cheapest tier and escalates as needed.
        proxy_configuration = ProxyConfiguration(
            tiered_proxy_urls=[
                # Tier 0: cheap datacenter proxies, tried first
                ['http://datacenter-proxy-1:8080', 'http://datacenter-proxy-2:8080'],
                # Tier 1: residential proxies, used when tier 0 gets blocked
                ['http://residential-proxy-1:8080', 'http://residential-proxy-2:8080'],
            ],
        )

        await proxy_configuration.initialize()

        proxy_url = await proxy_configuration.new_url()
        Actor.log.info(f'Using proxy URL: {proxy_url}')


if __name__ == '__main__':
    asyncio.run(main())
