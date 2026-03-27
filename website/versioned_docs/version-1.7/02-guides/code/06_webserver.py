import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from apify import Actor

processed_items = 0
http_server = None


class RequestHandler(BaseHTTPRequestHandler):
    """A handler that prints the number of processed items on every GET request."""

    def do_GET(self):
        self.log_request()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(bytes(f'Processed items: {processed_items}', encoding='utf-8'))


def run_server():
    """Start the HTTP server on the provided port, and save a reference to the server."""
    global http_server
    with ThreadingHTTPServer(('', Actor.config.container_port), RequestHandler) as server:
        Actor.log.info(f'Server running on {Actor.config.container_url}')
        http_server = server
        server.serve_forever()


async def main():
    global processed_items
    async with Actor:
        # Start the HTTP server in a separate thread
        run_server_task = asyncio.get_running_loop().run_in_executor(None, run_server)

        # Simulate doing some work
        for _ in range(100):
            await asyncio.sleep(1)
            processed_items += 1
            Actor.log.info(f'Processed items: {processed_items}')

        # Signal the HTTP server to shut down, and wait for it to finish
        http_server.shutdown()
        await run_server_task
