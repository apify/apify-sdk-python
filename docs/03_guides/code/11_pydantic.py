import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic.alias_generators import to_camel

from apify import Actor


class ActorInput(BaseModel):
    """Typed and validated representation of the Actor input."""

    # Derive each field's camelCase alias (searchTerms, maxResults, ...) automatically;
    # accept both spellings and ignore extras.
    model_config = ConfigDict(
        populate_by_name=True, extra='ignore', alias_generator=to_camel
    )

    # Required: non-empty list of search terms (normalized below).
    search_terms: list[str] = Field(min_length=1)

    # Optional: 1-100, defaults to 10.
    max_results: int = Field(default=10, ge=1, le=100)

    # Optional: restricted to a fixed set of choices.
    output_format: Literal['json', 'csv'] = Field(default='json')

    @field_validator('search_terms')
    @classmethod
    def _normalize_terms(cls, value: list[str]) -> list[str]:
        # Trim whitespace and drop empty terms.
        cleaned = [term.strip() for term in value if term.strip()]
        if not cleaned:
            raise ValueError('searchTerms must contain at least one non-empty term')
        return cleaned


async def main() -> None:
    async with Actor:
        # Read the raw input (a plain dict, not yet validated).
        raw_input = await Actor.get_input() or {}

        # Validate the raw input against the model.
        try:
            actor_input = ActorInput.model_validate(raw_input)
        except ValidationError as exc:
            # Log a per-field summary, then re-raise to fail the run.
            Actor.log.error('The Actor input is invalid:\n%s', exc)
            raise

        # Work with typed attributes from here on.
        Actor.log.info('Input passed validation: %s', actor_input.model_dump())

        max_results = actor_input.max_results
        for term in actor_input.search_terms:
            Actor.log.info('Processing %r (max %d results)', term, max_results)

        # Store the normalized input as output.
        await Actor.set_value('OUTPUT', actor_input.model_dump())


if __name__ == '__main__':
    asyncio.run(main())
