import asyncio
import os

from crewai import Agent, Crew, Task
from crewai_tools import ApifyActorsTool

from apify import Actor


async def main() -> None:
    async with Actor:
        # Charge a flat fee for starting the run (pay-per-event).
        await Actor.charge('actor-start')

        # `CREWAI_TESTING` disables an interactive first-run prompt that would
        # otherwise block inside a container. `ApifyActorsTool` reads the API
        # token from `APIFY_API_TOKEN`, which we set from the injected token.
        os.environ.setdefault('CREWAI_TESTING', 'true')
        os.environ['APIFY_API_TOKEN'] = os.environ['APIFY_TOKEN']

        # Read the Actor input.
        actor_input = await Actor.get_input() or {}
        query = actor_input.get('query')
        if not query:
            raise ValueError('Missing "query" attribute in the Actor input!')
        model_name = actor_input.get('modelName', 'gpt-4o-mini')

        # Give the agent an Apify Store Actor as a tool.
        agent = Agent(
            role='Social media analyst',
            goal='Analyze social media profiles and summarize the findings.',
            backstory='You turn raw social media data into clear insights.',
            tools=[ApifyActorsTool('apify/instagram-scraper')],
            llm=model_name,
        )
        task = Task(
            description=query,
            expected_output='A concise, helpful answer to the user query.',
            agent=agent,
        )
        crew = Crew(agents=[agent], tasks=[task])

        # `kickoff_async` runs the crew without blocking the event loop.
        result = await crew.kickoff_async()
        Actor.log.info(f'Tokens used: {result.token_usage.total_tokens}')

        await Actor.push_data({'query': query, 'response': result.raw})

        # Charge a flat fee once the task is done.
        await Actor.charge('task-completed')


if __name__ == '__main__':
    asyncio.run(main())
