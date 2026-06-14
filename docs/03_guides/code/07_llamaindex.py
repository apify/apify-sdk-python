import asyncio

from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.llms.openai import OpenAI

from apify import Actor

CONTACT_SCRAPER = 'vdrmota/contact-info-scraper'


async def scrape_contact_details(url: str) -> list[dict]:
    """Scrape contact details (emails, phones, social profiles) from a website."""
    run_input = {'startUrls': [{'url': url}], 'maxDepth': 1}
    # Call the Contact Details Scraper Actor from the Apify Store.
    run = await Actor.apify_client.actor(CONTACT_SCRAPER).call(run_input=run_input)
    if run is None:
        raise RuntimeError('Failed to start the Contact Details Scraper Actor.')

    dataset = Actor.apify_client.dataset(run.default_dataset_id)
    return (await dataset.list_items(clean=True)).items


async def main() -> None:
    async with Actor:
        # Charge a flat fee for starting the run (pay-per-event).
        await Actor.charge('actor-start')

        # Read the Actor input.
        actor_input = await Actor.get_input() or {}
        query = actor_input.get('query')
        if not query:
            raise ValueError('Missing "query" attribute in the Actor input!')
        model_name = actor_input.get('modelName', 'gpt-4o-mini')

        # Build a ReAct agent with the Apify Actor wrapped as a tool.
        agent = ReActAgent(
            tools=[FunctionTool.from_defaults(fn=scrape_contact_details)],
            llm=OpenAI(model=model_name),
        )

        # Run the agent to completion and store its answer.
        response = await agent.run(user_msg=query)
        Actor.log.info(f'Agent answer: {response}')
        await Actor.push_data({'query': query, 'answer': str(response)})

        # Charge a flat fee once the task is done.
        await Actor.charge('task-completed')


if __name__ == '__main__':
    asyncio.run(main())
