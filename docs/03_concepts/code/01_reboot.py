from apify import Actor


async def main() -> None:
    async with Actor:
        # ... your code here ...
        await Actor.reboot()
