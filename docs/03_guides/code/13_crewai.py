import asyncio
import os

from crewai import Agent, Crew, Task
from crewai_tools import ApifyActorsTool

from apify import Actor

# On a fresh container, CrewAI shows a one-time trace-consent prompt that blocks on
# stdin. `CREWAI_TESTING=true` is the only flag that suppresses it.
os.environ.setdefault('CREWAI_TESTING', 'true')


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        query = actor_input.get(
            'query', 'Summarize the latest posts on the @openai Instagram profile.'
        )
        model = actor_input.get('model', 'gpt-4o-mini')

        # CrewAI calls the LLM through LiteLLM, which reads OPENAI_API_KEY.
        # `ApifyActorsTool` reads APIFY_API_TOKEN. The platform injects APIFY_TOKEN.
        os.environ.setdefault('APIFY_API_TOKEN', os.environ['APIFY_TOKEN'])

        # The agent can run any Apify Actor as a tool, here the Instagram scraper.
        analyst = Agent(
            role='Social Media Analyst',
            goal='Analyze social media profiles and summarize the findings.',
            backstory='An analyst who turns raw social media data into concise insights.',
            tools=[ApifyActorsTool('apify/instagram-scraper')],
            llm=model,
        )
        task = Task(
            description=query,
            expected_output='A short, readable summary that answers the query.',
            agent=analyst,
        )

        # `kickoff_async` keeps the Actor's event loop responsive.
        result = await Crew(agents=[analyst], tasks=[task]).kickoff_async()
        Actor.log.info(f'Crew result:\n{result.raw}')
        await Actor.push_data({'query': query, 'summary': result.raw})


if __name__ == '__main__':
    asyncio.run(main())
