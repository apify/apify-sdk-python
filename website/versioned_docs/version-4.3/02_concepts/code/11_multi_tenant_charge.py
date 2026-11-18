import asyncio
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Header

from apify import Actor

app = FastAPI()


@app.get('/')
async def index(
    x_actor_request_id: Annotated[str | None, Header()] = None,
    x_apify_container_server_readiness_probe: Annotated[str | None, Header()] = None,
) -> str:
    # The platform checks that the server is ready before it sends any requests.
    if x_apify_container_server_readiness_probe is not None:
        return 'ready'

    # The platform identifies the caller of each request with this header.
    # Pass it along so the charge lands on the caller's account, not yours.
    # Locally, the header is missing and the charge goes to the local log.
    if x_actor_request_id is None:
        await Actor.charge(event_name='api-call')
    else:
        await Actor.charge(event_name='api-call', request_id=x_actor_request_id)
    return 'done'


async def main() -> None:
    async with Actor:
        config = uvicorn.Config(
            app,
            host='0.0.0.0',  # noqa: S104
            port=Actor.configuration.web_server_port,
        )
        await uvicorn.Server(config).serve()


if __name__ == '__main__':
    asyncio.run(main())
