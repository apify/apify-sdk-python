import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # With context manager
        async with await Actor.new_client().run('some_actor_id').get_streamed_log():
            await asyncio.sleep(5)
            # Logging will stop out of context

        # With direct call (lifecycle of logging has to be manually handled)
        streamed_log = await Actor.new_client().run('some_id').get_streamed_log()
        streamed_log.start()
        await asyncio.sleep(5)
        await streamed_log.stop()
