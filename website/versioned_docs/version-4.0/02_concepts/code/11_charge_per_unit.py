import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        urls = [
            'https://example.com/1',
            'https://example.com/2',
            'https://example.com/3',
        ]

        for url in urls:
            # Charge for a single event
            charge_result = await Actor.charge(
                event_name='page-scraped',
            )

            if charge_result.event_charge_limit_reached:
                break

            result = {'url': url, 'data': f'Scraped data from {url}'}

            # Push the result to the dataset
            await Actor.push_data(result)


if __name__ == '__main__':
    asyncio.run(main())
