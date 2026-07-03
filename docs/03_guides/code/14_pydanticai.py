import asyncio
import os

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'


class Joke(BaseModel):
    """The agent's typed output: a joke split into its setup and punchline."""

    setup: str
    punchline: str


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        topic = actor_input.get('topic', 'bad weather')
        model = actor_input.get('model', 'openai/gpt-4o-mini')

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        provider = OpenAIProvider(
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )
        # `output_type=Joke` makes the agent return a validated `Joke` instance.
        agent = Agent(
            OpenAIChatModel(model, provider=provider),
            output_type=Joke,
            system_prompt='You are a witty comedian. Write a single short joke.',
        )

        joke = (await agent.run(user_prompt=f'Tell me a joke about {topic}.')).output
        Actor.log.info(f'Joke:\n{joke.setup}\n{joke.punchline}')
        await Actor.push_data(
            {'topic': topic, 'setup': joke.setup, 'punchline': joke.punchline}
        )


if __name__ == '__main__':
    asyncio.run(main())
