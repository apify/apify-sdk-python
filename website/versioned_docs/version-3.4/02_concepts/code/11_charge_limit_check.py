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
            # Do some expensive work (e.g. scraping, API calls)
            result = {'url': url, 'data': f'Scraped data from {url}'}

            # highlight-start
            # push_data returns a ChargeResult - check it to know if the budget ran out
            charge_result = await Actor.push_data(result, 'result-item')

            if charge_result.event_charge_limit_reached:
                Actor.log.info('Charge limit reached, stopping the Actor')
                break
            # highlight-end


if __name__ == '__main__':
    asyncio.run(main())
