import asyncio

from apify import Actor
from apify.errors import ActorRunError, ApifyApiError


async def main() -> None:
    async with Actor:
        try:
            run = await Actor.call('apify/web-scraper', run_input={'startUrls': []})
        except ApifyApiError as exc:
            # The Apify API rejected the request, e.g. the Actor does not exist or
            # the token is invalid. The HTTP status code is on the exception.
            Actor.log.error(f'Could not start the Actor: {exc} (HTTP {exc.status_code}).')
            return

        # `Actor.call` returns the finished run whatever its status, so check it.
        if run.status != 'SUCCEEDED':
            raise ActorRunError.from_run(run)

        Actor.log.info(f'Run {run.id} finished successfully.')


if __name__ == '__main__':
    asyncio.run(main())
