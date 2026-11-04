import asyncio
import os

from crewai import LLM, Agent, Crew, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'

# On a fresh container, CrewAI shows a one-time trace-consent prompt that blocks on
# stdin. `CREWAI_TESTING=true` suppresses it.
os.environ.setdefault('CREWAI_TESTING', 'true')


class ActorInput(BaseModel):
    """The Actor input, validated with default values."""

    url: str = 'https://crawlee.dev/python/docs/guides/architecture-overview'
    model: str = 'openai/gpt-5.4-mini'


class Crawler(BaseModel):
    """One crawler class that Crawlee provides."""

    name: str
    built_on: str
    best_for: str


class CrawlerGuide(BaseModel):
    """The structured guide the crew distills from the docs page."""

    crawlers: list[Crawler]


class WebBrowserToolInput(BaseModel):
    """The single argument the agent passes to the web browser tool."""

    url: str = Field(description='The URL of the web page to fetch.')


class WebBrowserTool(BaseTool):
    """A minimal CrewAI tool that runs an Apify Actor to fetch a page as Markdown."""

    name: str = 'web_browser'
    description: str = 'Fetch a web page and return its content as clean Markdown.'
    args_schema: type[BaseModel] = WebBrowserToolInput

    async def _run(self, url: str) -> str:
        run = await Actor.call(
            actor_id='apify/rag-web-browser',
            run_input={'query': url, 'maxResults': 1},
        )
        dataset = Actor.apify_client.dataset(run.default_dataset_id)
        items = (await dataset.list_items()).items
        return '\n\n'.join(item.get('markdown') or '' for item in items)


async def main() -> None:
    async with Actor:
        # Parse the Actor input into the typed model, filling in defaults.
        actor_input = ActorInput.model_validate(await Actor.get_input() or {})
        url = actor_input.url
        model = actor_input.model

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        llm = LLM(
            model=model,
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
            provider='openai',
        )

        # `WebBrowserTool` is our own Actor-backed tool, wrapping the RAG Web Browser
        # to fetch the page as clean Markdown.
        researcher = Agent(
            role='Documentation researcher',
            goal=(
                'Fetch the page with the web_browser tool and note every crawler '
                'it describes.'
            ),
            backstory=(
                'A researcher who never answers from memory. Before writing '
                'anything, always read the actual page with the web_browser tool '
                'and report only what it says.'
            ),
            tools=[WebBrowserTool()],
            llm=llm,
        )

        writer = Agent(
            role='Technical writer',
            goal='Turn research notes into a clear, structured crawler guide.',
            backstory='A writer who distills docs into comparison tables.',
            llm=llm,
        )

        research = Task(
            description=(
                f'Use the web_browser tool to fetch {url}. Based only on the returned '
                'Markdown, list the crawlers the page covers. Do not use prior knowledge.'
            ),
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

        crew = Crew(agents=[researcher, writer], tasks=[research, write])
        guide = (await crew.kickoff_async()).pydantic

        if guide is None:
            raise RuntimeError('The crew did not return a structured CrawlerGuide.')

        Actor.log.info(f'Crawler guide:\n{guide.model_dump_json(indent=2)}')
        await Actor.push_data([crawler.model_dump() for crawler in guide.crawlers])


if __name__ == '__main__':
    asyncio.run(main())
