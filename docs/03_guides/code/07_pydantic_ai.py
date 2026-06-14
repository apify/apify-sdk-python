import asyncio
import os

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from apify import Actor

# The Apify OpenRouter proxy is an OpenAI-compatible endpoint billed to the run's
# Apify account, so no provider API key is needed. It authenticates with the
# `APIFY_TOKEN` that the platform injects into every run.
OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'


class Joke(BaseModel):
    """The structured result returned by the agent."""

    topic: str
    joke: str


async def main() -> None:
    async with Actor:
        # Charge a flat fee for starting the run (pay-per-event).
        await Actor.charge('actor-start')

        # Read the Actor input.
        actor_input = await Actor.get_input() or {}
        topic = actor_input.get('jokeTopic', 'Bad weather')
        model_name = actor_input.get('modelName', 'openai/gpt-4o-mini')

        # Point the OpenAI-compatible client at the Apify OpenRouter proxy.
        provider = OpenAIProvider(
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )
        agent = Agent(
            OpenAIChatModel(model_name, provider=provider),
            output_type=Joke,
            system_prompt='You are a witty comedian. Write one short, clean joke.',
        )

        # Run the agent and store its validated, typed result.
        result = await agent.run(user_prompt=f'Tell me a joke about {topic}.')
        joke = result.output
        Actor.log.info(f'Generated a joke about {joke.topic}: {joke.joke}')
        await Actor.push_data(joke.model_dump())

        # Charge a flat fee once the task is done.
        await Actor.charge('task-completed')


if __name__ == '__main__':
    asyncio.run(main())
