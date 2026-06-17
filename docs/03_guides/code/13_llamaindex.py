import asyncio
import os

from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.llms.openai_like import OpenAILike

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'


def word_count(text: str) -> int:
    """Return the number of words in the given text."""
    return len(text.split())


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        query = actor_input.get('query', 'How many words are in "Apify runs Actors"?')
        model = actor_input.get('model', 'openai/gpt-4o-mini')

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        # `OpenAILike` is the LlamaIndex class for OpenAI-compatible endpoints.
        llm = OpenAILike(
            model=model,
            api_base=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
            is_chat_model=True,
        )
        agent = ReActAgent(tools=[FunctionTool.from_defaults(fn=word_count)], llm=llm)

        response = await agent.run(user_msg=query)
        Actor.log.info(f'Agent answer:\n{response}')
        await Actor.push_data({'query': query, 'answer': str(response)})


if __name__ == '__main__':
    asyncio.run(main())
