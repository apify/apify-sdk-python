from __future__ import annotations

import asyncio

from apify import Actor, Request


async def custom_new_url_function(
    session_id: str | None = None,
    _: Request | None = None,
) -> str | None:
    if session_id is not None:
        return f'http://my-custom-proxy-supporting-sessions.com?session-id={session_id}'
    return 'http://my-custom-proxy-not-supporting-sessions.com'


async def main() -> None:
    async with Actor:
        proxy_cfg = await Actor.create_proxy_configuration(
            new_url_function=custom_new_url_function,  # type: ignore[arg-type]
        )

        if not proxy_cfg:
            raise RuntimeError('No proxy configuration available.')

        proxy_url_with_session = await proxy_cfg.new_url('a')
        Actor.log.info(f'Using proxy URL: {proxy_url_with_session}')

        proxy_url_without_session = await proxy_cfg.new_url()
        Actor.log.info(f'Using proxy URL: {proxy_url_without_session}')


if __name__ == '__main__':
    asyncio.run(main())
