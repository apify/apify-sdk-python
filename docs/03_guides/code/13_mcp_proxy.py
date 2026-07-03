import asyncio

import uvicorn
from fastmcp.server import create_proxy

from apify import Actor

# The upstream MCP server to expose. Point this at any remote Streamable HTTP or
# SSE endpoint. To wrap a local stdio server instead, pass `create_proxy` an
# `mcpServers` config mapping (`{'command': ..., 'args': [...]}`) instead of a URL.
UPSTREAM_URL = 'https://mcp.example.com/mcp'


async def main() -> None:
    async with Actor:
        # Connect to the upstream server and re-expose it over Streamable HTTP.
        proxy = create_proxy(UPSTREAM_URL, name='my-mcp-proxy')
        app = proxy.http_app(transport='streamable-http')

        # Serve it on the platform's web server port, exactly like a server you
        # build yourself. Binding to 0.0.0.0 makes it reachable through the
        # Actor's container URL.
        config = uvicorn.Config(
            app,
            host='0.0.0.0',  # noqa: S104
            port=Actor.configuration.web_server_port,
        )
        web_server = uvicorn.Server(config)

        # Run the server in the background.
        server_task = asyncio.create_task(web_server.serve())

        url = Actor.configuration.web_server_url
        Actor.log.info(f'MCP proxy is available at {url}/mcp')

        # In production the server runs until the platform shuts the Actor down.
        # This runnable example instead serves for a short window so the run
        # finishes on its own.
        await asyncio.sleep(60)

        # Signal the server to shut down and wait.
        web_server.should_exit = True
        await server_task


if __name__ == '__main__':
    asyncio.run(main())
