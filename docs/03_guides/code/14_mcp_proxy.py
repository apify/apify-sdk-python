import asyncio

import uvicorn
from fastmcp.server import create_proxy

from apify import Actor

# The upstream MCP server to expose. Point this at any remote Streamable HTTP or
# SSE endpoint. To wrap a local stdio server instead, pass an `mcpServers` config
# (see the MCP proxy guide section).
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

        url = Actor.configuration.web_server_url
        Actor.log.info(f'MCP proxy is available at {url}/mcp')

        # Keep serving until the platform shuts the Actor down.
        await uvicorn.Server(config).serve()


if __name__ == '__main__':
    asyncio.run(main())
