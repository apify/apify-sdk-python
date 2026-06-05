import asyncio
import os
from urllib.parse import urlsplit

from browser_use import Agent, Browser, ChatOpenAI
from browser_use.browser import ProxySettings
from pydantic import BaseModel

from apify import Actor

# The default task is aligned with the `Posts` output schema defined below.
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


def _proxy_settings(proxy_url: str) -> ProxySettings:
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
    """Run a Browser Use agent for a single task and return its structured output.

    The agent is driven by an OpenAI model and a real Chromium browser. Passing
    `output_model_schema` makes the agent return a validated `Posts` instance instead
    of free-form text, and `enable_signal_handler=False` leaves signal handling to the
    Actor.
    """
    # Configure the LLM that drives the agent. Swap `ChatOpenAI` for `ChatAnthropic`,
    # `ChatGoogle`, or another provider to use a different model.
    llm = ChatOpenAI(model=model, api_key=llm_api_key)

    # Configure the browser. When a proxy URL is provided, route the browser through it.
    browser = Browser(
        headless=headless,
        proxy=_proxy_settings(proxy_url) if proxy_url else None,
    )

    # Create the agent and run it for at most `max_steps` steps.
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
    # Enter the context of the Actor.
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        task = actor_input.get('task', DEFAULT_TASK)
        model = actor_input.get('model', 'gpt-4.1-mini')
        max_steps = actor_input.get('maxSteps', 25)

        # Read the LLM API key from the environment so it is never stored in the Actor
        # input. On the Apify platform, set it as a secret environment variable.
        llm_api_key = os.environ.get('OPENAI_API_KEY')
        if not llm_api_key:
            raise RuntimeError('The OPENAI_API_KEY environment variable is not set.')

        # Create a proxy configuration that routes the browser through Apify Proxy.
        proxy_configuration = await Actor.create_proxy_configuration()
        proxy_url = await proxy_configuration.new_url() if proxy_configuration else None

        Actor.log.info(f'Running the agent (model={model}) for task: {task}')

        # Run the Browser Use agent and collect its structured output.
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

        # Store every extracted item as a separate row in the default dataset.
        Actor.log.info(f'The agent returned {len(result.posts)} post(s); storing them.')
        for post in result.posts:
            Actor.log.info(f'Storing post: {post.title!r} ({post.url})')
            await Actor.push_data(post.model_dump())


if __name__ == '__main__':
    asyncio.run(main())
