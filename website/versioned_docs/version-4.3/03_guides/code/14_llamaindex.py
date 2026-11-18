import asyncio
import os

from llama_index.core import Document, VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai_like import OpenAILike
from pydantic import BaseModel

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'
EMBED_MODEL = 'BAAI/bge-small-en-v1.5'


class ActorInput(BaseModel):
    """The Actor input, validated with default values."""

    urls: list[str] = [
        'https://docs.apify.com/platform/actors',
        'https://docs.apify.com/platform/storage/dataset',
        'https://docs.apify.com/platform/proxy',
    ]
    question: str = 'How does Apify proxy work?'
    model: str = 'openai/gpt-5.4-mini'


class Answer(BaseModel):
    """The grounded answer the query engine returns."""

    answer: str
    key_facts: list[str]


async def scrape_documents(urls: list[str]) -> list[Document]:
    """Scrape the pages with the Website Content Crawler and wrap them as `Document`s."""
    run_input = {'startUrls': [{'url': url} for url in urls], 'maxCrawlDepth': 0}
    run = await Actor.call('apify/website-content-crawler', run_input=run_input)
    dataset = Actor.apify_client.dataset(run.default_dataset_id)
    items = (await dataset.list_items()).items
    return [Document(text=item['text'], metadata={'url': item['url']}) for item in items]


async def main() -> None:
    async with Actor:
        # Parse the Actor input into the typed model, filling in defaults.
        actor_input = ActorInput.model_validate(await Actor.get_input() or {})
        urls = actor_input.urls
        question = actor_input.question
        model = actor_input.model

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        llm = OpenAILike(
            model=model,
            api_base=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
            is_chat_model=True,
        )

        # Embeddings run locally, so the proxy needs no embeddings endpoint. Loading the
        # model blocks, so offload it with `asyncio.to_thread`.
        embed_model = await asyncio.to_thread(
            HuggingFaceEmbedding, model_name=EMBED_MODEL
        )

        # Scrape the pages and wrap each result as a `Document` for the vector index.
        documents = await scrape_documents(urls)

        # Chunking and embedding every document blocks too, so offload it the same way.
        index = await asyncio.to_thread(
            VectorStoreIndex.from_documents, documents, embed_model=embed_model
        )

        # `output_cls` returns a validated `Answer`. The response still carries the
        # retrieved `source_nodes`, so the answer can cite the pages it came from.
        query_engine = index.as_query_engine(
            llm=llm,
            output_cls=Answer,
            response_mode='compact',
            similarity_top_k=4,
        )
        response = await query_engine.aquery(question)

        answer = response.response
        sources = [node.node.metadata['url'] for node in response.source_nodes]
        record = {'question': question, **answer.model_dump(), 'sources': sources}
        Actor.log.info(f'Answer:\n{answer.model_dump_json(indent=2)}')
        await Actor.push_data(record)


if __name__ == '__main__':
    asyncio.run(main())
