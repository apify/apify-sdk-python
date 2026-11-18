import asyncio

from apify import Actor


async def main() -> None:
    # Enter the context of the Actor.
    async with Actor:
        # Read the input and reach into the raw dict.
        actor_input = await Actor.get_input() or {}
        search_terms = actor_input.get('searchTerms', [])
        max_results = actor_input.get('maxResults', 10)

        Actor.log.info('search_terms=%s, max_results=%s', search_terms, max_results)


if __name__ == '__main__':
    asyncio.run(main())
