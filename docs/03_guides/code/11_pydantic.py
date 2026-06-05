import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from apify import Actor


class ActorInput(BaseModel):
    """Typed and validated representation of the Actor input.

    The field names follow Python's `snake_case`, while the aliases match the
    `camelCase` keys produced by the Apify input schema editor. With
    `populate_by_name`, the model accepts either form, and unknown fields are
    ignored (`extra='ignore'`) so that adding a field to the input schema never
    breaks an older Actor build.
    """

    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    # Required: a non-empty list of search terms. The validator below trims
    # each entry and drops the empty ones.
    search_terms: list[str] = Field(alias='searchTerms', min_length=1)

    # Optional: defaults to 10 and must fall within the inclusive 1-100 range.
    max_results: int = Field(alias='maxResults', default=10, ge=1, le=100)

    # Optional: restricted to a fixed set of choices, like an input schema enum.
    output_format: Literal['json', 'csv'] = Field(alias='outputFormat', default='json')

    @field_validator('search_terms')
    @classmethod
    def _normalize_terms(cls, value: list[str]) -> list[str]:
        # Trim whitespace and drop empty terms, then ensure something is left.
        cleaned = [term.strip() for term in value if term.strip()]
        if not cleaned:
            raise ValueError('searchTerms must contain at least one non-empty term')
        return cleaned


async def main() -> None:
    # Enter the context of the Actor.
    async with Actor:
        # Read the raw input record from the default key-value store. It's a
        # plain dict (or None) - no validation has happened yet.
        raw_input = await Actor.get_input() or {}

        # Validate the raw input against the model. On success, `actor_input` is
        # a fully typed `ActorInput` with defaults filled in and every field
        # guaranteed to be valid.
        try:
            actor_input = ActorInput.model_validate(raw_input)
        except ValidationError as exc:
            # Log a readable, per-field summary, then re-raise so the context
            # manager marks the run as FAILED. Failing fast here beats crashing
            # later with an obscure error deep in the code.
            Actor.log.error('The Actor input is invalid:\n%s', exc)
            raise

        # From here on, work with typed attributes instead of dict lookups.
        Actor.log.info('Input passed validation: %s', actor_input.model_dump())

        max_results = actor_input.max_results
        for term in actor_input.search_terms:
            Actor.log.info('Processing %r (max %d results)', term, max_results)

        # Store the normalized input as the Actor's output.
        await Actor.set_value('OUTPUT', actor_input.model_dump())


if __name__ == '__main__':
    asyncio.run(main())
