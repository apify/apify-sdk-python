import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # highlight-start
        # Charge for a single occurrence of an event
        await Actor.charge(event_name='init')
        # highlight-end

        # Prepare some mock results
        result = [
            {'word': 'Lorem'},
            {'word': 'Ipsum'},
            {'word': 'Dolor'},
            {'word': 'Sit'},
            {'word': 'Amet'},
        ]
        # highlight-start
        # Shortcut for charging for each pushed dataset item
        await Actor.push_data(result, 'result-item')
        # highlight-end

        # highlight-start
        # Or you can charge for a given number of events manually
        await Actor.charge(
            event_name='result-item',
            count=len(result),
        )
        # highlight-end


if __name__ == '__main__':
    asyncio.run(main())
