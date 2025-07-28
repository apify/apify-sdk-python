"""
Test server is infinite server http://localhost:8080/{any_number} and each page has links to the next 10 pages.
For example:
    http://localhost:8080/ contains links:
http://localhost:8080/0, http://localhost:8080/1, ..., http://localhost:8080/9

    http://localhost:8080/1 contains links:
http://localhost:8080/10, http://localhost:8080/11, ..., http://localhost:8080/19

... and so on.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from socket import socket
from typing import Any

from uvicorn import Config
from uvicorn.server import Server
from yarl import URL

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Coroutine[None, None, None]]


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


async def app(scope: dict[str, Any], _: Receive, send: Send) -> None:
    """Main ASGI application handler that routes requests to specific handlers.

    Args:
        scope: The ASGI connection scope.
        _: The ASGI receive function.
        send: The ASGI send function.
    """
    assert scope['type'] == 'http'
    path = scope['path']

    links = '\n'.join(f'<a href="{path}{i}">{path}{i}</a>' for i in range(10))
    await send_html_response(
        send,
        f"""\
<html><head>
    <title>Title for {path} </title>
</head>
<body>
    {links}
</body></html>""".encode(),
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
        """Run the server."""
        if sockets:
            raise RuntimeError('Simple TestServer does not support custom sockets')
        self.restart_requested = asyncio.Event()

        loop = asyncio.get_event_loop()
        tasks = {
            loop.create_task(super().serve()),
        }
        await asyncio.wait(tasks)


if __name__ == '__main__':
    asyncio.run(
        TestServer(
            config=Config(
                app=app,
                lifespan='off',
                loop='asyncio',
                port=8080,
                log_config=None,
                log_level=logging.CRITICAL,
            )
        ).serve()
    )
