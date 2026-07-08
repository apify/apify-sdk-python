import asyncio
import os

import impit
from pydantic import BaseModel, ValidationError
from smolagents import CodeAgent, OpenAIServerModel, tool

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'
HN_FRONT_PAGE_URL = 'https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50'
TOP_DOMAINS = 5


class ActorInput(BaseModel):
    """The Actor input, validated with default values."""

    model: str = 'openai/gpt-5.4-mini'


class DomainStat(BaseModel):
    """One domain's slice of the Hacker News front page."""

    domain: str
    story_count: int
    average_points: float


class FrontPageReport(BaseModel):
    """The structured analysis the agent computes from the front page."""

    total_stories: int
    top_domains: list[DomainStat]


@tool
def fetch_front_page() -> list[dict]:
    """Fetch the Hacker News front page as story dicts with title, url, and points."""
    with impit.Client(browser='firefox', follow_redirects=True, timeout=30) as client:
        hits = client.get(HN_FRONT_PAGE_URL).json()['hits']

    return [
        {'title': hit['title'], 'url': hit['url'], 'points': hit['points']}
        for hit in hits
        if hit.get('url') and hit.get('points') is not None
    ]


def is_valid_report(final_answer: object, *_: object, **__: object) -> bool:
    """Check the agent's answer against `FrontPageReport` so the schema is enforced."""
    try:
        FrontPageReport.model_validate(final_answer)
    except ValidationError:
        return False
    return True


async def main() -> None:
    async with Actor:
        # Parse the Actor input into the typed model, filling in defaults.
        actor_input = ActorInput.model_validate(await Actor.get_input() or {})
        model = actor_input.model

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        llm = OpenAIServerModel(
            model_id=model,
            api_base=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )

        # A `CodeAgent` solves the task by writing and running Python, so it groups
        # and averages the stories in code. `final_answer_checks` re-runs
        # `is_valid_report` on each answer until the output validates.
        agent = CodeAgent(
            tools=[fetch_front_page],
            model=llm,
            additional_authorized_imports=['collections', 'statistics', 'urllib.parse'],
            final_answer_checks=[is_valid_report],
        )

        prompt = (
            'Analyze the current Hacker News front page. Call `fetch_front_page`, '
            'then use code to take the domain of each story URL, group the stories '
            f'by domain, and find the {TOP_DOMAINS} domains with the most stories. '
            'Call `final_answer` with a dict shaped like {"total_stories": int, '
            '"top_domains": [{"domain": str, "story_count": int, '
            '"average_points": float}]}.'
        )
        # `CodeAgent.run` is synchronous, so `asyncio.to_thread` keeps it off the
        # Actor's event loop.
        result = await asyncio.to_thread(agent.run, prompt)

        report = FrontPageReport.model_validate(result)
        Actor.log.info(f'Front page report:\n{report.model_dump_json(indent=2)}')
        await Actor.push_data(report.model_dump())


if __name__ == '__main__':
    asyncio.run(main())
