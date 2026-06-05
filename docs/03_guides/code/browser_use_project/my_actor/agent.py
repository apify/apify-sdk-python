from __future__ import annotations

from urllib.parse import urlsplit

from browser_use import Agent, Browser, ChatOpenAI
from browser_use.browser import ProxySettings
from pydantic import BaseModel


class Post(BaseModel):
    """A single item the agent is asked to extract."""

    title: str
    url: str


class Posts(BaseModel):
    """The structured result returned by the agent."""

    posts: list[Post]


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


def _proxy_settings(proxy_url: str) -> ProxySettings:
    """Convert an Apify Proxy URL into Browser Use `ProxySettings`."""
    parts = urlsplit(proxy_url)
    return ProxySettings(
        server=f'{parts.scheme}://{parts.hostname}:{parts.port}',
        username=parts.username,
        password=parts.password,
    )
