import asyncio
import random

from apify import Actor, Request

FAILURE_RATE = 0.3


async def main() -> None:
    async with Actor:
        # Open the queue
        queue = await Actor.open_request_queue()

        # Add some requests to the queue
        for i in range(1, 10):
            await queue.add_request(Request.from_url(f'http://example.com/{i}'))

        # Add a request to the start of the queue, for priority processing
        await queue.add_request(Request.from_url('http://example.com/0'), forefront=True)

        # If you try to add an existing request again, it will not do anything
        add_request_info = await queue.add_request(
            Request.from_url('http://different-example.com/5')
        )
        Actor.log.info(f'Add request info: {add_request_info}')

        processed_request = await queue.get_request(add_request_info.id)
        Actor.log.info(f'Processed request: {processed_request}')

        # Finally, process the queue until all requests are handled
        while not await queue.is_finished():
            # Fetch the next unhandled request in the queue
            request = await queue.fetch_next_request()
            # This can happen due to the eventual consistency of the underlying request
            # queue storage, best solution is just to sleep a bit.
            if request is None:
                await asyncio.sleep(1)
                continue

            Actor.log.info(f'Processing request {request.unique_key}...')
            Actor.log.info(f'Scraping URL {request.url}...')

            # Do some fake work, which fails 30% of the time
            await asyncio.sleep(1)
            if random.random() > FAILURE_RATE:
                # If processing the request was successful, mark it as handled
                Actor.log.info('Request successful.')
                await queue.mark_request_as_handled(request)
            else:
                # If processing the request was unsuccessful, reclaim it so it can be
                # processed again.
                Actor.log.warning('Request failed, will retry!')
                await queue.reclaim_request(request)
