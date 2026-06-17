import asyncio

from crewai import Agent, Crew, Task

from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        topic = actor_input.get('topic', 'the Apify platform')
        model = actor_input.get('model', 'gpt-4o-mini')

        # CrewAI calls the LLM through LiteLLM, which reads OPENAI_API_KEY.
        analyst = Agent(
            role='Research Analyst',
            goal=f'Write a short, accurate summary about {topic}.',
            backstory='An analyst who turns a topic into a concise brief.',
            llm=model,
        )
        task = Task(
            description=f'Write a three-sentence summary about {topic}.',
            expected_output='A three-sentence summary.',
            agent=analyst,
        )

        # `kickoff_async` keeps the Actor's event loop responsive.
        result = await Crew(agents=[analyst], tasks=[task]).kickoff_async()
        Actor.log.info(f'Crew result:\n{result.raw}')
        await Actor.push_data({'topic': topic, 'summary': result.raw})


if __name__ == '__main__':
    asyncio.run(main())
