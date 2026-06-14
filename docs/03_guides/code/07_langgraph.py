import asyncio

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from apify import Actor


class InstagramPost(BaseModel):
    """A single Instagram post returned by the scraping tool."""

    url: str
    likes: int
    comments: int


class Summary(BaseModel):
    """The structured result returned by the agent."""

    total_likes: int
    total_comments: int
    most_popular: list[InstagramPost]


@tool
async def scrape_instagram_posts(handle: str, limit: int = 30) -> list[InstagramPost]:
    """Scrape recent posts of a public Instagram profile by its handle."""
    run_input = {
        'directUrls': [f'https://www.instagram.com/{handle}/'],
        'resultsType': 'posts',
        'resultsLimit': limit,
    }
    # Call the Instagram Scraper Actor from the Apify Store as the tool's backend.
    run = await Actor.apify_client.actor('apify/instagram-scraper').call(
        run_input=run_input,
    )
    if run is None:
        raise RuntimeError('Failed to start the Instagram Scraper Actor.')

    dataset = Actor.apify_client.dataset(run.default_dataset_id)
    items = (await dataset.list_items()).items
    return [
        InstagramPost(
            url=item['url'],
            likes=item.get('likesCount', 0),
            comments=item.get('commentsCount', 0),
        )
        for item in items
        if item.get('url')
    ]


async def main() -> None:
    async with Actor:
        # Charge a flat fee for starting the run (pay-per-event).
        await Actor.charge('actor-start')

        # Read the Actor input.
        actor_input = await Actor.get_input() or {}
        query = actor_input.get('query')
        if not query:
            raise ValueError('Missing "query" attribute in the Actor input!')
        model_name = actor_input.get('modelName', 'gpt-4o-mini')

        # Build a ReAct agent with the Apify Actor exposed as a tool.
        llm = ChatOpenAI(model=model_name)
        agent = create_agent(
            llm,
            [scrape_instagram_posts],
            response_format=Summary,
        )

        # Run the agent and read its structured response.
        result = await agent.ainvoke({'messages': [('user', query)]})
        summary: Summary = result['structured_response']
        Actor.log.info(f'Total likes across the posts: {summary.total_likes}')

        await Actor.push_data(summary.model_dump())

        # Charge a flat fee once the task is done.
        await Actor.charge('task-completed')


if __name__ == '__main__':
    asyncio.run(main())
