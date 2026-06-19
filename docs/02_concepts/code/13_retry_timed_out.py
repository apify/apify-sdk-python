import asyncio
from datetime import timedelta

from apify import Actor
from apify.errors import ActorRunError, ActorTimeoutError


async def main() -> None:
    async with Actor:
        timeout = timedelta(minutes=5)
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            run = await Actor.call('apify/web-scraper', timeout=timeout)

            if run.status == 'SUCCEEDED':
                Actor.log.info(f'Run {run.id} finished.')
                break

            # Build a typed error from the finished run so we can branch on it.
            error = ActorRunError.from_run(run)
            if isinstance(error, ActorTimeoutError) and attempt < max_attempts:
                timeout *= 2
                Actor.log.warning(f'Timed out, retrying with timeout {timeout}.')
                continue

            raise error


if __name__ == '__main__':
    asyncio.run(main())
