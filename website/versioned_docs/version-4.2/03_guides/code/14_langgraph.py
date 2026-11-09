import asyncio
import os
from functools import partial
from typing import TypedDict

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'
MIN_KEY_POINTS = 3
MAX_REVISIONS = 2


class ActorInput(BaseModel):
    """The Actor input, validated with default values."""

    url: str = 'https://crawlee.dev'
    model: str = 'openai/gpt-5.4-mini'


class PageSummary(BaseModel):
    """The structured summary the agent extracts from a web page."""

    title: str
    summary: str
    key_points: list[str]
    target_audience: str


class State(TypedDict):
    """The state that flows between the graph's nodes."""

    url: str
    page_text: str
    summary: PageSummary
    revisions: int


async def fetch(state: State) -> dict:
    """A node that scrapes the page to clean Markdown with the RAG Web Browser Actor."""
    run_input = {'query': state['url'], 'outputFormats': ['markdown']}
    run = await Actor.call('apify/rag-web-browser', run_input=run_input)
    dataset = Actor.apify_client.dataset(run.default_dataset_id)
    items = (await dataset.list_items()).items
    if not items or not items[0].get('markdown'):
        raise RuntimeError(f'RAG Web Browser returned no content for {state["url"]}.')
    return {'page_text': items[0]['markdown']}


async def summarize(state: State, structured_llm: Runnable) -> dict:
    """A node that summarizes the page, asking for more depth on a re-run."""
    hint = ''
    if state['revisions']:
        hint = f' List at least {MIN_KEY_POINTS} distinct key points.'
    prompt = f'Summarize this page.{hint}\n\n{state["page_text"]}'
    summary = await structured_llm.ainvoke(prompt)
    return {'summary': summary, 'revisions': state['revisions'] + 1}


def route(state: State) -> str:
    """A conditional edge that loops back for another pass while the summary is thin."""
    thin = len(state['summary'].key_points) < MIN_KEY_POINTS
    if thin and state['revisions'] < MAX_REVISIONS:
        return 'summarize'
    return END


async def main() -> None:
    async with Actor:
        # Parse the Actor input into the typed model, filling in defaults.
        actor_input = ActorInput.model_validate(await Actor.get_input() or {})
        url = actor_input.url
        model = actor_input.model

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        llm = ChatOpenAI(
            model=model,
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )

        # `with_structured_output` makes the node return a validated `PageSummary`.
        structured_llm = llm.with_structured_output(PageSummary)

        # Wire the nodes into a graph. Its conditional edge loops back into `summarize`
        # until the summary is detailed enough. `partial` binds `structured_llm` to it.
        graph = StateGraph(State)
        graph.add_node('fetch', fetch)
        graph.add_node('summarize', partial(summarize, structured_llm=structured_llm))
        graph.add_edge(START, 'fetch')
        graph.add_edge('fetch', 'summarize')
        graph.add_conditional_edges('summarize', route)
        agent = graph.compile()

        result = await agent.ainvoke({'url': url, 'revisions': 0})
        summary = result['summary']
        Actor.log.info(f'Page summary:\n{summary.model_dump_json(indent=2)}')
        await Actor.push_data({'url': url, **summary.model_dump()})


if __name__ == '__main__':
    asyncio.run(main())
