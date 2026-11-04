import asyncio
import os
from urllib.parse import urlsplit

from browser_use import Agent, Browser, ChatOpenAI
from browser_use.browser import ProxySettings
from pydantic import BaseModel

from apify import Actor

# Default task, aligned with the `Posts` schema below.
DEFAULT_TASK = (
    'Open https://news.ycombinator.com and return the title and URL '
    'of the top 5 posts on the front page.'
)


class Post(BaseModel):
    """A single item the agent is asked to extract."""

    title: str
    url: str


class Posts(BaseModel):
    """The structured result returned by the agent."""

    posts: list[Post]


def to_browser_use_proxy(proxy_url: str) -> ProxySettings:
    """Convert an Apify Proxy URL into Browser Use `ProxySettings`."""
    parts = urlsplit(proxy_url)
    return ProxySettings(
        server=f'{parts.scheme}://{parts.hostname}:{parts.port}',
        username=parts.username,
        password=parts.password,
    )


async def run_agent_task(
    task: str,
    *,
    model: str,
    llm_api_key: str,
    max_steps: int,
    headless: bool = True,
    proxy_url: str | None = None,
) -> Posts | None:
    """Run a Browser Use agent for one task and return its structured output."""
    # Configure the LLM. Swap `ChatOpenAI` for another provider if needed.
    llm = ChatOpenAI(model=model, api_key=llm_api_key)

    # Configure the browser, optionally routed through a proxy.
    browser = Browser(
        headless=headless,
        proxy=to_browser_use_proxy(proxy_url) if proxy_url else None,
    )

    # `output_model_schema` returns a validated `Posts`; signals stay with the Actor.
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        output_model_schema=Posts,
        enable_signal_handler=False,
    )

    history = await agent.run(max_steps=max_steps)
    return history.structured_output


async def main() -> None:
    async with Actor:
        # Read the Actor input.
        actor_input = await Actor.get_input() or {}
        task = actor_input.get('task', DEFAULT_TASK)
        model = actor_input.get('model', 'gpt-4.1-mini')
        max_steps = actor_input.get('maxSteps', 25)

        # Read the LLM API key from the environment (set it as a secret on Apify).
        llm_api_key = os.environ.get('OPENAI_API_KEY')
        if not llm_api_key:
            raise RuntimeError('The OPENAI_API_KEY environment variable is not set.')

        # Route the browser through Apify Proxy.
        proxy_configuration = await Actor.create_proxy_configuration()
        proxy_url = await proxy_configuration.new_url() if proxy_configuration else None

        Actor.log.info(f'Running the agent (model={model}) for task: {task}')

        result = await run_agent_task(
            task,
            model=model,
            llm_api_key=llm_api_key,
            max_steps=max_steps,
            headless=Actor.configuration.headless,
            proxy_url=proxy_url,
        )

        if result is None:
            Actor.log.warning('The agent did not return any structured output.')
            return

        # Store each extracted item as a dataset row.
        Actor.log.info(f'The agent returned {len(result.posts)} post(s); storing them.')
        for post in result.posts:
            Actor.log.info(f'Storing post: {post.title!r} ({post.url})')
            await Actor.push_data(post.model_dump())


if __name__ == '__main__':
    asyncio.run(main())
