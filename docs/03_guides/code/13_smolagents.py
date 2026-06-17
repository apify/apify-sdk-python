import asyncio
import os

from smolagents import CodeAgent, OpenAIServerModel

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        task = actor_input.get('task', 'Compute the 12th Fibonacci number.')
        model = actor_input.get('model', 'openai/gpt-4o-mini')

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        llm = OpenAIServerModel(
            model_id=model,
            api_base=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )
        # A `CodeAgent` writes and runs Python code to solve the task.
        agent = CodeAgent(tools=[], model=llm)

        result = agent.run(task)
        Actor.log.info(f'Agent result:\n{result}')
        await Actor.push_data({'task': task, 'result': str(result)})


if __name__ == '__main__':
    asyncio.run(main())
