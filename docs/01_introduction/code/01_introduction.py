import asyncio

import httpx
from bs4 import BeautifulSoup

from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        url = actor_input.get('url', 'https://apify.com')
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        data = {
            'url': url,
            'title': soup.title.string if soup.title else None,
        }
        await Actor.push_data(data)


if __name__ == '__main__':
    asyncio.run(main())
