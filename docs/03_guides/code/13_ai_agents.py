import asyncio
import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from apify import Actor

# The agent reaches its LLM through the Apify OpenRouter proxy, an
# OpenAI-compatible endpoint billed against the run's Apify account. It
# authenticates with the `APIFY_TOKEN` that the platform injects into every run,
# so no separate provider API key (such as `OPENAI_API_KEY`) is needed.
OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'

DEFAULT_PROMPT = 'In two sentences, explain what an Apify Actor is.'


def build_agent(model_name: str) -> Agent[None, str]:
    """Build a PydanticAI agent that routes LLM calls through Apify OpenRouter."""
    provider = OpenAIProvider(
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ['APIFY_TOKEN'],
    )
    return Agent(
        OpenAIChatModel(model_name, provider=provider),
        output_type=str,
        system_prompt='You are a concise, helpful research assistant.',
    )


async def main() -> None:
    async with Actor:
        # Read the Actor input.
        actor_input = await Actor.get_input() or {}
        prompt = actor_input.get('prompt', DEFAULT_PROMPT)
        model_name = actor_input.get('model', 'openai/gpt-4o-mini')

        # Build the agent and run it for a single prompt.
        Actor.log.info(f'Running the agent (model={model_name}) for: {prompt}')
        agent = build_agent(model_name)
        result = await agent.run(user_prompt=prompt)

        # Store the agent's answer in the default dataset.
        Actor.log.info(f'The agent responded:\n{result.output}')
        await Actor.push_data({'prompt': prompt, 'response': result.output})


if __name__ == '__main__':
    asyncio.run(main())
