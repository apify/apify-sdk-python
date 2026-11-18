import asyncio
from datetime import timedelta

from apify import Actor


async def main() -> None:
    async with Actor:
        timeout = timedelta(minutes=5)
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            run = await Actor.call('apify/web-scraper', timeout=timeout)

            if run.status != 'TIMED-OUT' or attempt == max_attempts:
                Actor.log.info(f'Run {run.id} ended with status {run.status}.')
                break

            timeout *= 2
            Actor.log.warning(f'Timed out, retrying with timeout {timeout}.')


if __name__ == '__main__':
    asyncio.run(main())
