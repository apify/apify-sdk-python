from __future__ import annotations

from crawlee.crawlers import FileDownloadCrawler, FileDownloadCrawlingContext
from crawlee.storages import RequestQueue

from apify import Actor

_BUFFERED_URLS = ['http://localhost:8080/files/1024.pdf', 'http://localhost:8080/files/2048.png']
_STREAMED_URLS = ['http://localhost:8080/files/5242880.bin']


async def _store_file(context: FileDownloadCrawlingContext, content: bytes, chunk_count: int) -> None:
    key = context.request.url.rsplit('/', 1)[-1]
    kvs = await context.get_key_value_store()
    await kvs.set_value(key, content, content_type=context.http_response.headers.get('content-type'))
    await context.push_data({'url': context.request.url, 'key': key, 'chunk_count': chunk_count})


async def main() -> None:
    async with Actor:
        buffered_crawler = FileDownloadCrawler()

        @buffered_crawler.router.default_handler
        async def buffered_handler(context: FileDownloadCrawlingContext) -> None:
            content = await context.http_response.read()
            await _store_file(context, content, chunk_count=1)

        await buffered_crawler.run(_BUFFERED_URLS)

        # The default RQ already holds the buffered crawl, so the streamed crawl gets a queue of its own.
        streamed_crawler = FileDownloadCrawler(stream=True, request_manager=await RequestQueue.open(alias='streamed'))

        @streamed_crawler.router.default_handler
        async def streamed_handler(context: FileDownloadCrawlingContext) -> None:
            chunks = [chunk async for chunk in context.http_response.read_stream()]
            await _store_file(context, b''.join(chunks), chunk_count=len(chunks))

        await streamed_crawler.run(_STREAMED_URLS)
