import asyncio
import os
from http import HTTPStatus

import impit
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from apify import Actor

OPENROUTER_BASE_URL = 'https://openrouter.apify.actor/api/v1'
PYPI_JSON_URL = 'https://pypi.org/pypi/{name}/json'


class ActorInput(BaseModel):
    """The Actor input, validated with default values."""

    package: str = 'crawlee'
    model: str = 'openai/gpt-5.4-mini'


class PackageFacts(BaseModel):
    """The metadata the tool pulls from the PyPI JSON API."""

    name: str
    version: str
    summary: str | None
    requires_python: str | None


class PackageReport(BaseModel):
    """The agent's typed verdict on a PyPI package."""

    name: str
    latest_version: str
    summary: str
    recommendation: str


async def fetch_pypi_metadata(name: str) -> PackageFacts:
    """Fetch a package's metadata from the PyPI JSON API."""
    async with impit.AsyncClient(
        browser='firefox', follow_redirects=True, timeout=30
    ) as client:
        response = await client.get(PYPI_JSON_URL.format(name=name))

    if response.status_code != HTTPStatus.OK:
        raise RuntimeError(f'PyPI has no package named "{name}".')

    info = response.json()['info']
    return PackageFacts(
        name=info['name'],
        version=info['version'],
        summary=info['summary'],
        requires_python=info['requires_python'],
    )


async def main() -> None:
    async with Actor:
        # Parse the Actor input into the typed model, filling in defaults.
        actor_input = ActorInput.model_validate(await Actor.get_input() or {})
        package = actor_input.package
        model = actor_input.model

        # Route the LLM through the Apify OpenRouter proxy (no provider key needed).
        provider = OpenAIProvider(
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ['APIFY_TOKEN'],
        )

        # `output_type` makes the agent return a validated `PackageReport`. Passing
        # `fetch_pypi_metadata` in `tools` registers it as a tool from its signature.
        agent = Agent(
            OpenAIChatModel(model, provider=provider),
            output_type=PackageReport,
            tools=[fetch_pypi_metadata],
            system_prompt=(
                'You advise Python developers on packages. Always call '
                '`fetch_pypi_metadata` for facts instead of guessing.'
            ),
        )

        prompt = f'Evaluate the "{package}" package and recommend whether to use it.'
        report = (await agent.run(user_prompt=prompt)).output
        Actor.log.info(f'Package report:\n{report.model_dump_json(indent=2)}')
        await Actor.push_data(report.model_dump())


if __name__ == '__main__':
    asyncio.run(main())
