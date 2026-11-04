import asyncio

from apify import Actor
from apify.request_loaders import ApifyRequestList


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}

        # The input may contain a list of URL sources in the standard Apify format
        request_list_sources = actor_input.get('requestListSources', [])

        # Create a request list from the input sources.
        # Supports direct URLs and remote URL lists.
        request_list = await ApifyRequestList.open(
            request_list_sources_input=request_list_sources,
        )

        total = await request_list.get_total_count()
        Actor.log.info(f'Loaded {total} requests from input')

        # Process requests from the list
        while request := await request_list.fetch_next_request():
            Actor.log.info(f'Processing {request.url}')


if __name__ == '__main__':
    asyncio.run(main())
