import asyncio

from apify import Actor
from apify.errors import ActorError


async def main() -> None:
    async with Actor:
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                run = await Actor.call('apify/web-scraper')
            except ActorError as exc:
                # Give up on permanent errors, or once the attempts are exhausted.
                if not exc.retryable or attempt == max_attempts:
                    raise

                backoff_secs = 2**attempt
                Actor.log.warning(
                    f'Attempt {attempt} failed ({exc.code}); retrying in {backoff_secs}s.'
                )
                await asyncio.sleep(backoff_secs)
            else:
                Actor.log.info(f'Run {run.id} finished with status {run.status}.')
                break


if __name__ == '__main__':
    asyncio.run(main())
