import asyncio

from apify import Actor
from apify.errors import ActorError, ActorRunError, ActorTimeoutError


async def main() -> None:
    async with Actor:
        try:
            run = await Actor.call('apify/web-scraper', run_input={'startUrls': []})
        # Order matters: catch the most specific subclasses first.
        except ActorTimeoutError as exc:
            Actor.log.warning(f'Run {exc.run_id} timed out; try a longer timeout.')
        except ActorRunError as exc:
            Actor.log.error(
                f'Run {exc.run_id} failed: {exc.status} (exit {exc.exit_code}).'
            )
        except ActorError as exc:
            # Authentication, rate limit, server error, or any other API failure.
            if exc.retryable:
                Actor.log.warning(f'Transient error ({exc.code}); can be retried.')
            else:
                Actor.log.error(f'Permanent error ({exc.code}): {exc}')
        else:
            Actor.log.info(f'Run {run.id} finished with status {run.status}.')


if __name__ == '__main__':
    asyncio.run(main())
