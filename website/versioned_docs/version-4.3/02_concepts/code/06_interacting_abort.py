import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Start another Actor
        actor_run = await Actor.start(
            actor_id='apify/web-scraper',
            run_input={'startUrls': [{'url': 'https://example.com'}]},
        )

        Actor.log.info(f'Started run {actor_run.id}')

        # ... later, decide the run is no longer needed ...

        # Graceful abort sends ABORTING and PERSIST_STATE events to the target Actor,
        # then force-stops it after 30 seconds.
        aborted_run = await Actor.abort(
            run_id=actor_run.id,
            gracefully=True,
            status_message='No longer needed',
        )

        Actor.log.info(f'Aborted run status: {aborted_run.status}')


if __name__ == '__main__':
    asyncio.run(main())
