from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Awaitable, Coroutine, Iterator
from itertools import chain, cycle
from typing import TYPE_CHECKING, Any, Callable

from uvicorn.server import Server
from yarl import URL

if TYPE_CHECKING:
    from socket import socket


Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Coroutine[None, None, None]]


async def send_json_response(send: Send, data: Any, status: int = 200) -> None:
    """Send a JSON response to the client."""
    await send(
        {
            'type': 'http.response.start',
            'status': status,
            'headers': [[b'content-type', b'application/json']],
        }
    )
    await send({'type': 'http.response.body', 'body': json.dumps(data, indent=2).encode()})


async def send_html_response(send: Send, html_content: bytes, status: int = 200) -> None:
    """Send an HTML response to the client."""
    await send(
        {
            'type': 'http.response.start',
            'status': status,
            'headers': [[b'content-type', b'text/html; charset=utf-8']],
        }
    )
    await send({'type': 'http.response.body', 'body': html_content})


async def app(scope: dict[str, Any], receive: Receive, send: Send) -> None:  # noqa: ARG001
    """Main ASGI application handler that routes requests to specific handlers.

    Args:
        scope: The ASGI connection scope.
        receive: The ASGI receive function.
        send: The ASGI send function.
    """
    assert scope['type'] == 'http'
    path = scope['path']

    # Route requests to appropriate handlers
    if path.startswith('/v2/datasets/default'):
        await v2_datasets_default(send)
    else:
        await hello_world(send)


async def hello_world(send: Send) -> None:
    """Handle basic requests with a simple HTML response."""
    await send_html_response(
        send,
        b"""<html>
        <head>
            <title>Hello, world!</title>
        </head>
    </html>""",
    )


_API_V2_DATASET_ACCESS_DEALY = chain(iter([360]), cycle([0]))


async def v2_datasets_default(send: Send) -> None:
    """Handle requests for v2/datasets/default."""
    await asyncio.sleep(next(_API_V2_DATASET_ACCESS_DEALY))
    await send_json_response(
        send,
        {
            'data': {
                'id': 'WkzbQMuFYuamGv3YF',
                'name': 'd7b9MDYsbtX5L7XAj',
                'userId': 'wRsJZtadYvn4mBZmm',
                'createdAt': '2019-12-12T07:34:14.202Z',
                'modifiedAt': '2019-12-13T08:36:13.202Z',
                'accessedAt': '2019-12-14T08:36:13.202Z',
                'itemCount': 7,
                'cleanItemCount': 5,
                'actId': 'null',
                'actRunId': 'null',
                'fields': [],
            }
        },
    )


class TestServer(Server):
    """A test HTTP server implementation based on Uvicorn Server."""

    @property
    def url(self) -> URL:
        """Get the base URL of the server.

        Returns:
            A URL instance with the server's base URL.
        """
        protocol = 'https' if self.config.is_ssl else 'http'
        return URL(f'{protocol}://{self.config.host}:{self.config.port}/')

    async def serve(self, sockets: list[socket] | None = None) -> None:
        """Run the server and set up restart capability.

        Args:
            sockets: Optional list of sockets to bind to.
        """
        self.restart_requested = asyncio.Event()

        loop = asyncio.get_event_loop()
        tasks = {
            loop.create_task(super().serve(sockets=sockets)),
            loop.create_task(self.watch_restarts()),
        }
        await asyncio.wait(tasks)

    async def restart(self) -> None:
        """Request server restart and wait for it to complete.

        This method can be called from a different thread than the one the server
        is running on, and from a different async environment.
        """
        self.started = False
        self.restart_requested.set()
        while not self.started:  # noqa: ASYNC110
            await asyncio.sleep(0.2)

    async def watch_restarts(self) -> None:
        """Watch for and handle restart requests."""
        while True:
            if self.should_exit:
                return

            try:
                await asyncio.wait_for(self.restart_requested.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

            self.restart_requested.clear()
            await self.shutdown()
            await self.startup()


def serve_in_thread(server: TestServer) -> Iterator[TestServer]:
    """Run a server in a background thread and yield it."""
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        while not server.started:
            time.sleep(1e-3)
        yield server
    finally:
        server.should_exit = True
        thread.join()
