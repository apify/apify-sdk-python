import asyncio
import os

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'


@tool
def sum_numbers(numbers: list[int]) -> int:
    """Return the sum of a list of numbers."""
    return sum(numbers)


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        query = actor_input.get('query', 'What is the sum of 128, 64, and 32?')
        model = actor_input.get('model', 'openai/gpt-4o-mini')

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        llm = ChatOpenAI(
            model=model,
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )
        # The agent decides on its own when to call the `sum_numbers` tool.
        agent = create_agent(llm, tools=[sum_numbers])

        result = await agent.ainvoke({'messages': [('user', query)]})
        answer = result['messages'][-1].content
        Actor.log.info(f'Agent answer:\n{answer}')
        await Actor.push_data({'query': query, 'answer': answer})


if __name__ == '__main__':
    asyncio.run(main())
