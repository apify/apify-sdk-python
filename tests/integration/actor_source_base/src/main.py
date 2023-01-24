from apify import Actor


async def main() -> None:
    async with Actor():
        raise RuntimeError('You need to override the `main.py` file in the integration test!')
