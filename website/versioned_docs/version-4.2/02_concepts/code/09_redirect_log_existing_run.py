import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Lifecycle of redirected logs is handled by the context manager.
        async with await Actor.apify_client.run('some_actor_id').get_streamed_log(
            # Redirect all logs from the start of that run, even the logs from past.
            from_start=True
        ):
            await asyncio.sleep(5)
            # Logging will stop out of context

        # Lifecycle of redirected logs can be handled manually.
        streamed_log = await Actor.apify_client.run('some_id').get_streamed_log(
            # Do not redirect historical logs from this actor run.
            # Redirect only new logs from now on.
            from_start=False
        )
        streamed_log.start()
        await asyncio.sleep(5)
        await streamed_log.stop()


if __name__ == '__main__':
    asyncio.run(main())
