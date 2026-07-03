import asyncio
import os

from smolagents import CodeAgent, OpenAIServerModel, WebSearchTool

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        topic = actor_input.get('topic', 'open source AI')
        model = actor_input.get('model', 'openai/gpt-4o-mini')

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        llm = OpenAIServerModel(
            model_id=model,
            api_base=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )
        # A `CodeAgent` writes and runs Python code to solve the task. Here it uses
        # `WebSearchTool` to gather the latest news before summarizing it.
        agent = CodeAgent(tools=[WebSearchTool()], model=llm)

        result = agent.run(f'Find and summarize the latest news about {topic}.')
        Actor.log.info(f'Summary:\n{result}')
        await Actor.push_data({'topic': topic, 'summary': str(result)})


if __name__ == '__main__':
    asyncio.run(main())
