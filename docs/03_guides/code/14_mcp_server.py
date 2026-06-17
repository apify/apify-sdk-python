import asyncio

import uvicorn
from fastmcp import FastMCP

from apify import Actor


def build_server() -> FastMCP:
    """Create a FastMCP server exposing one tool and one resource."""
    server = FastMCP(name='calculator')

    @server.tool()
    def add(a: float, b: float) -> float:
        """Add two numbers and return the sum."""
        return a + b

    @server.resource(uri='resource://calculator/info', name='calculator-info')
    def info() -> str:
        """Describe what this MCP server does."""
        return 'A simple calculator MCP server that adds two numbers.'

    return server


async def main() -> None:
    async with Actor:
        # Build the server and expose it over the Streamable HTTP transport.
        server = build_server()
        app = server.http_app(transport='streamable-http')

        # Serve it on the platform's web server port. Binding to 0.0.0.0 makes
        # the server reachable through the Actor's container URL.
        config = uvicorn.Config(
            app,
            host='0.0.0.0',  # noqa: S104
            port=Actor.configuration.web_server_port,
        )

        url = Actor.configuration.web_server_url
        Actor.log.info(f'MCP server is available at {url}/mcp')

        # Keep serving until the platform shuts the Actor down, for example when
        # a Standby instance has been idle past its timeout.
        await uvicorn.Server(config).serve()


if __name__ == '__main__':
    asyncio.run(main())
