import asyncio

import uvicorn
from fastapi import FastAPI

from apify import Actor

# A module-level counter that the web server reports and the Actor keeps updating.
processed_items = 0

# The FastAPI application with a single endpoint.
app = FastAPI()


@app.get('/')
async def index() -> dict[str, int]:
    """Respond to every GET request with the number of processed items."""
    return {'processed_items': processed_items}


async def main() -> None:
    global processed_items
    async with Actor:
        # Serve the FastAPI app with uvicorn on the platform's web server port.
        # Binding to 0.0.0.0 makes it reachable through the Actor's container URL.
        config = uvicorn.Config(
            app,
            host='0.0.0.0',  # noqa: S104
            port=Actor.configuration.web_server_port,
        )
        server = uvicorn.Server(config)

        # Run the server in the background while the Actor does its work.
        server_task = asyncio.create_task(server.serve())
        Actor.log.info(f'Server running at {Actor.configuration.web_server_url}')

        # Simulate doing some work, updating the counter the endpoint reports.
        for _ in range(100):
            await asyncio.sleep(1)
            processed_items += 1
            Actor.log.info(f'Processed items: {processed_items}')

        # Signal the server to shut down, and wait for it to finish.
        server.should_exit = True
        await server_task


if __name__ == '__main__':
    asyncio.run(main())
