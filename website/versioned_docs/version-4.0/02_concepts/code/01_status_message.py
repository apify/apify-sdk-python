import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        await Actor.set_status_message('Here we go!')
        # Do some work...
        await asyncio.sleep(3)
        await Actor.set_status_message('So far so good...')
        await asyncio.sleep(3)
        # Do some more work...
        await Actor.set_status_message('Steady as she goes...')
        await asyncio.sleep(3)
        # Do even more work...
        await Actor.set_status_message('Almost there...')
        await asyncio.sleep(3)
        # Finish the job
        await Actor.set_status_message('Phew! That was not that hard!')


if __name__ == '__main__':
    asyncio.run(main())
