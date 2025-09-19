from apify import Actor


async def main() -> None:
    async with Actor:
        proxy_configuration = await Actor.create_proxy_configuration(
            groups=['RESIDENTIAL'],
            country_code='US',
        )

        if not proxy_configuration:
            raise RuntimeError('No proxy configuration available.')

        proxy_url = await proxy_configuration.new_url()
        Actor.log.info(f'Proxy URL: {proxy_url}')
