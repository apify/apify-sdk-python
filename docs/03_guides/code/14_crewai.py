import asyncio
import os

from crewai import LLM, Agent, Crew, Task
from crewai.tools import tool

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'

# On a fresh container, CrewAI shows a one-time trace-consent prompt that blocks on
# stdin. `CREWAI_TESTING=true` is the only flag that suppresses it.
os.environ.setdefault('CREWAI_TESTING', 'true')


@tool('Average')
def average(numbers: list[float]) -> float:
    """Return the arithmetic mean of a list of numbers."""
    return sum(numbers) / len(numbers)


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        query = actor_input.get('query', 'What is the average of 12, 18, and 30?')
        model = actor_input.get('model', 'openai/gpt-4o-mini')

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        # The `openai/` prefix selects CrewAI's OpenAI-compatible client. The rest
        # is the OpenRouter model slug sent to the proxy.
        llm = LLM(
            model=f'openai/{model}',
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )

        # A one-agent crew: an analyst that answers using the `average` tool.
        analyst = Agent(
            role='Data Analyst',
            goal='Answer numeric questions accurately.',
            backstory='An analyst who turns raw numbers into clear answers.',
            tools=[average],
            llm=llm,
        )
        task = Task(
            description=query,
            expected_output='A short, readable answer to the query.',
            agent=analyst,
        )

        # `kickoff_async` keeps the Actor's event loop responsive.
        result = await Crew(agents=[analyst], tasks=[task]).kickoff_async()
        Actor.log.info(f'Crew result:\n{result.raw}')
        await Actor.push_data({'query': query, 'answer': result.raw})


if __name__ == '__main__':
    asyncio.run(main())
