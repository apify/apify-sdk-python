import requests
from bs4 import BeautifulSoup

from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input()
        response = requests.get(actor_input['url'])
        soup = BeautifulSoup(response.content, 'html.parser')
        await Actor.push_data({'url': actor_input['url'], 'title': soup.title.string})
