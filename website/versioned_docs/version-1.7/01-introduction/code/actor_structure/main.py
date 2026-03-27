from apify import Actor


async def main() -> None:
    async with Actor:
        Actor.log.info('Actor input:', await Actor.get_input())
        await Actor.set_value('OUTPUT', 'Hello, world!')
