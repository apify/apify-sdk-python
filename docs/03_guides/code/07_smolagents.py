import asyncio
import os

from smolagents import CodeAgent, OpenAIServerModel, WebSearchTool

from apify import Actor

# Default topics, used when the input doesn't provide any.
DEFAULT_INTERESTS = ['Artificial intelligence', 'Open source']


async def main() -> None:
    async with Actor:
        # Read the Actor input.
        actor_input = await Actor.get_input() or {}
        interests = actor_input.get('interests', DEFAULT_INTERESTS)
        model_name = actor_input.get('model', 'gpt-4o-mini')

        # Read the LLM API key from the environment (set it as a secret on Apify).
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError('The OPENAI_API_KEY environment variable is not set.')

        # Build the model and an agent equipped with a web search tool.
        model = OpenAIServerModel(
            model_id=model_name,
            api_base='https://api.openai.com/v1',
            api_key=api_key,
        )
        agent = CodeAgent(tools=[WebSearchTool()], model=model)

        # Run the agent: first search for news, then summarize what it found.
        topics = ', '.join(interests)
        Actor.log.info(f'Searching for the latest news on: {topics}')
        news = agent.run(f'Find the latest news about {topics}.')
        summary = agent.run(f'Summarize these news articles:\n{news}')

        # Store the summary in the default dataset.
        Actor.log.info('Storing the summary in the dataset.')
        await Actor.push_data({'interests': interests, 'summary': summary})


if __name__ == '__main__':
    asyncio.run(main())
