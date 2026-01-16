import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from apify import Actor

processed_items = 0
http_server = None


# Just a simple handler that will print the number of processed items so far
# on every GET request.
class RequestHandler(BaseHTTPRequestHandler):
    def do_get(self) -> None:
        self.log_request()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(bytes(f'Processed items: {processed_items}', encoding='utf-8'))


def run_server() -> None:
    # Start the HTTP server on the provided port,
    # and save a reference to the server.
    global http_server
    with ThreadingHTTPServer(
        ('', Actor.configuration.web_server_port), RequestHandler
    ) as server:
        Actor.log.info(f'Server running on {Actor.configuration.web_server_port}')
        http_server = server
        server.serve_forever()


async def main() -> None:
    global processed_items
    async with Actor:
        # Start the HTTP server in a separate thread.
        run_server_task = asyncio.get_running_loop().run_in_executor(None, run_server)

        # Simulate doing some work.
        for _ in range(100):
            await asyncio.sleep(1)
            processed_items += 1
            Actor.log.info(f'Processed items: {processed_items}')

        if http_server is None:
            raise RuntimeError('HTTP server not started')

        # Signal the HTTP server to shut down, and wait for it to finish.
        http_server.shutdown()
        await run_server_task


if __name__ == '__main__':
    asyncio.run(main())
