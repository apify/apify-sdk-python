from apify import Actor


async def main() -> None:
    async with Actor:
        await Actor.set_status_message('Here we go!')
        # Do some work...
        await Actor.set_status_message('So far so good...')
        # Do some more work...
        await Actor.set_status_message('Steady as she goes...')
        # Do even more work...
        await Actor.set_status_message('Almost there...')
        # Finish the job
        await Actor.set_status_message('Phew! That was not that hard!')
