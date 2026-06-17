import asyncio
import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        prompt = actor_input.get('prompt', 'Explain Apify Actors in two sentences.')
        model = actor_input.get('model', 'openai/gpt-4o-mini')

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        provider = OpenAIProvider(
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )
        agent = Agent(
            OpenAIChatModel(model, provider=provider),
            output_type=str,
            system_prompt='You are a concise, helpful assistant.',
        )

        result = await agent.run(user_prompt=prompt)
        Actor.log.info(f'Agent response:\n{result.output}')
        await Actor.push_data({'prompt': prompt, 'response': result.output})


if __name__ == '__main__':
    asyncio.run(main())
