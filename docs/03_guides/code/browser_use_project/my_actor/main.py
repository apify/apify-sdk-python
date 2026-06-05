from __future__ import annotations

import os

from apify import Actor

from .agent import run_agent_task

# The default task is aligned with the `Posts` output schema defined in `agent.py`.
DEFAULT_TASK = (
    'Open https://news.ycombinator.com and return the title and URL '
    'of the top 5 posts on the front page.'
)


async def main() -> None:
    # Enter the context of the Actor.
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        task = actor_input.get('task', DEFAULT_TASK)
        model = actor_input.get('model', 'gpt-4.1-mini')
        max_steps = actor_input.get('max_steps', 25)

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
        for post in result.posts:
            await Actor.push_data(post.model_dump())
