import httpx
from bs4 import BeautifulSoup

from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input()
        async with httpx.AsyncClient() as client:
            response = await client.get(actor_input['url'])
        soup = BeautifulSoup(response.content, 'html.parser')
        data = {'url': actor_input['url'], 'title': soup.title.string if soup.title else None}
        await Actor.push_data(data)
