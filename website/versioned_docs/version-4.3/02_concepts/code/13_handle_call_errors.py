import asyncio

from apify import Actor
from apify.errors import ApifyApiError, NotFoundError


async def main() -> None:
    async with Actor:
        try:
            run = await Actor.call('apify/web-scraper', run_input={'startUrls': []})
        except NotFoundError:
            # Catch a specific subclass first.
            Actor.log.error('The Actor to call does not exist.')
            return
        except ApifyApiError as exc:
            # Any other API failure, e.g. an invalid token or a server error.
            Actor.log.error(f'Calling the Actor failed: {exc} (HTTP {exc.status_code}).')
            return

        # `Actor.call` returns the finished run whatever its status, so check it.
        if run.status != 'SUCCEEDED':
            Actor.log.error(f'Run {run.id} ended with status {run.status}.')
            return

        Actor.log.info(f'Run {run.id} finished successfully.')


if __name__ == '__main__':
    asyncio.run(main())
