from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from uvicorn import Config
from uvicorn.server import Server

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Coroutine[None, None, None]]

_PRODUCTS = {
    '1': {'name': 'Widget A', 'price': '$19.99', 'description': 'A basic widget for everyday use'},
    '2': {'name': 'Widget B', 'price': '$29.99', 'description': 'An advanced widget with extra features'},
    '3': {'name': 'Widget C', 'price': '$39.99', 'description': 'A premium widget for professionals'},
}


async def _send_html(send: Send, html: str, status: int = 200) -> None:
    await send(
        {
            'type': 'http.response.start',
            'status': status,
            'headers': [[b'content-type', b'text/html; charset=utf-8']],
        }
    )
    await send({'type': 'http.response.body', 'body': html.encode()})


async def app(scope: dict[str, Any], _receive: Receive, send: Send) -> None:
    assert scope['type'] == 'http'
    path = scope['path']

    if path == '/':
        await _send_html(
            send,
            '<html><head><title>E-commerce Test Store</title></head><body>'
            '<h1>Welcome to Test Store</h1>'
            '<a href="/products/1">Widget A</a>'
            '<a href="/products/2">Widget B</a>'
            '<a href="/products/3">Widget C</a>'
            '<a href="/about">About Us</a>'
            '</body></html>',
        )
    elif path.startswith('/products/'):
        product = _PRODUCTS.get(path.split('/')[-1])
        if product:
            await _send_html(
                send,
                f'<html><head><title>{product["name"]}</title></head><body>'
                f'<h1>{product["name"]}</h1>'
                f'<span class="price">{product["price"]}</span>'
                f'<p class="description">{product["description"]}</p>'
                f'<a href="/">Back to Home</a>'
                f'</body></html>',
            )
        else:
            await _send_html(send, '<html><body>Not Found</body></html>', 404)
    elif path == '/about':
        await _send_html(
            send,
            '<html><head><title>About Us</title></head><body>'
            '<h1>About Test Store</h1>'
            '<p class="description">We sell the best widgets in the world.</p>'
            '<a href="/">Back to Home</a>'
            '</body></html>',
        )
    else:
        await _send_html(send, '<html><body>Not Found</body></html>', 404)


if __name__ == '__main__':
    asyncio.run(
        Server(
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
