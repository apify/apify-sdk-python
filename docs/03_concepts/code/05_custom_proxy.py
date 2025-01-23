from apify import Actor


async def main() -> None:
    async with Actor:
        proxy_configuration = await Actor.create_proxy_configuration(
            proxy_urls=[
                'http://proxy-1.com',
                'http://proxy-2.com',
            ],
        )

        if not proxy_configuration:
            raise RuntimeError('No proxy configuration available.')

        proxy_url = await proxy_configuration.new_url()
        Actor.log.info(f'Using proxy URL: {proxy_url}')
