import asyncio
import os

from crewai import LLM, Agent, Crew, Task
from crewai_tools import ApifyActorsTool
from pydantic import BaseModel

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'

# On a fresh container, CrewAI shows a one-time trace-consent prompt that blocks on
# stdin. `CREWAI_TESTING=true` suppresses it.
os.environ.setdefault('CREWAI_TESTING', 'true')

# The Crawlee docs page the crew reads when the input has no `url`.
DEFAULT_URL = 'https://crawlee.dev/python/docs/guides/architecture-overview'


class ActorInput(BaseModel):
    """The Actor input, validated with default values."""

    url: str = DEFAULT_URL
    model: str = 'openai/gpt-5.4-mini'


class Crawler(BaseModel):
    """One crawler class that Crawlee provides."""

    name: str
    built_on: str
    best_for: str


class CrawlerGuide(BaseModel):
    """The structured guide the crew distills from the docs page."""

    crawlers: list[Crawler]


async def main() -> None:
    async with Actor:
        # Parse the Actor input into the typed model, filling in defaults.
        actor_input = ActorInput.model_validate(await Actor.get_input() or {})
        url = actor_input.url
        model = actor_input.model

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        # The `openai/` prefix selects CrewAI's OpenAI-compatible client.
        llm = LLM(
            model=f'openai/{model}',
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )

        # `ApifyActorsTool` exposes any Apify Actor as a CrewAI tool. Here it wraps the
        # RAG Web Browser to fetch the page as clean Markdown.
        researcher = Agent(
            role='Documentation researcher',
            goal='Read the Crawlee docs and note every crawler it describes.',
            backstory='A researcher who reads technical docs closely.',
            tools=[ApifyActorsTool('apify/rag-web-browser')],
            llm=llm,
        )
        writer = Agent(
            role='Technical writer',
            goal='Turn research notes into a clear, structured crawler guide.',
            backstory='A writer who distills docs into comparison tables.',
            llm=llm,
        )

        research = Task(
            description=f'Scrape {url} and list the crawlers the page covers.',
            expected_output='Notes on each crawler: name, what it builds on, its use.',
            agent=researcher,
        )
        # `context=[research]` feeds the researcher's notes to the writer, and
        # `output_pydantic` makes the final task return a validated `CrawlerGuide`.
        write = Task(
            description=(
                'From the notes, compile each crawler with what it is built on '
                'and what it is best for.'
            ),
            expected_output='A list of crawlers with name, built_on, and best_for.',
            agent=writer,
            context=[research],
            output_pydantic=CrawlerGuide,
        )

        # `kickoff_async` runs the crew without blocking the Actor's event loop.
        crew = Crew(agents=[researcher, writer], tasks=[research, write])
        guide = (await crew.kickoff_async()).pydantic
        if guide is None:
            raise RuntimeError('The crew did not return a structured CrawlerGuide.')
        Actor.log.info(f'Crawler guide:\n{guide.model_dump_json(indent=2)}')
        await Actor.push_data([crawler.model_dump() for crawler in guide.crawlers])


if __name__ == '__main__':
    asyncio.run(main())
