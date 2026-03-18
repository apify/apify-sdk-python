from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        proxy_settings = actor_input.get('proxySettings')
        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=proxy_settings
        )

        if not proxy_configuration:
            raise RuntimeError('No proxy configuration available.')

        proxy_url = await proxy_configuration.new_url()
        Actor.log.info(f'Using proxy URL: {proxy_url}')
