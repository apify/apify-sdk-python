import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Get the original Actor input.
        actor_input = await Actor.get_input() or {}
        hotel_url = actor_input.get('hotel_url')

        # Create new input for apify/web-scraper Actor.
        web_scraper_input = {
            'startUrls': [{'url': hotel_url}],
            'pageFunction': """async function pageFunction(context) {
                // Here you pass the JavaScript page function
                // that scrapes all the reviews from the hotel's URL
            }""",
        }

        # Metamorph the Actor run to `apify/web-scraper` with the new input.
        await Actor.metamorph('apify/web-scraper', web_scraper_input)

        # This code will not be called, since the `metamorph` action terminates
        # the current Actor run container.
        Actor.log.info('You will not see this!')


if __name__ == '__main__':
    asyncio.run(main())
