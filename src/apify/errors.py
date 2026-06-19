from __future__ import annotations

from typing import TYPE_CHECKING

# Re-export the Apify API client's error hierarchy so callers have a single import location for every error the SDK
# can surface. Any operation that talks to the Apify API raises these as-is; the SDK does not wrap them in its own
# types. See https://docs.apify.com/api/client/python for the full client error reference.
from apify_client.errors import (
    ApifyApiError,
    ApifyClientError,
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    InvalidResponseBodyError,
    NotFoundError,
    RateLimitError,
    ServerError,
    UnauthorizedError,
)

from apify._utils import docs_group

if TYPE_CHECKING:
    from apify_client._models import Run


@docs_group('Errors')
class ActorError(Exception):
    """Base class for the Apify SDK's own domain-level errors.

    These describe outcomes that the Apify API client cannot express on its own, such as a finished Actor run that
    ended in a failure state. Errors that originate from the Apify API surface as `apify_client` exceptions (e.g.
    `ApifyApiError` and its subclasses), which the SDK re-exports from this module but does not wrap.

    Carries a machine-readable `code` and a `retryable` flag so callers can branch on a failure without parsing the
    human-readable error message.
    """

    code: str = 'actor-error'
    """Stable, machine-readable identifier of the error category."""

    retryable: bool = False
    """Whether retrying the same operation might succeed (e.g. an Actor run that timed out)."""

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


@docs_group('Errors')
class ActorRunError(ActorError):
    """Represents an Actor run that reached a terminal failure state (e.g. `FAILED` or `ABORTED`).

    Exposes the run metadata needed to decide what to do next. The SDK does not raise this automatically. `Actor.call`
    and `Actor.call_task` return the finished run regardless of its status, mirroring the Apify API client. Build this
    error from a finished run with `from_run` when you want a failed run to surface as an exception in your own code.
    """

    code = 'actor-run-failed'

    def __init__(self, run: Run) -> None:
        self.run_id = run.id
        self.status = run.status
        self.exit_code = run.exit_code
        self.status_message = run.status_message

        message = f'Actor run {run.id!r} ended with status {run.status!r}'
        if run.status_message:
            message = f'{message}: {run.status_message}'

        super().__init__(message)

    @classmethod
    def from_run(cls, run: Run) -> ActorRunError:
        """Build the most specific run error for a terminal Actor run.

        Args:
            run: The terminal Actor run.

        Returns:
            An `ActorTimeoutError` for a timed-out run, otherwise an `ActorRunError`.
        """
        if run.status == 'TIMED-OUT':
            return ActorTimeoutError(run)
        return ActorRunError(run)


@docs_group('Errors')
class ActorTimeoutError(ActorRunError):
    """Represents an Actor run that exceeded its timeout (`TIMED-OUT`). Retrying with a longer timeout may help."""

    code = 'actor-timed-out'
    retryable = True


__all__ = [
    'ActorError',
    'ActorRunError',
    'ActorTimeoutError',
    'ApifyApiError',
    'ApifyClientError',
    'ConflictError',
    'ForbiddenError',
    'InvalidRequestError',
    'InvalidResponseBodyError',
    'NotFoundError',
    'RateLimitError',
    'ServerError',
    'UnauthorizedError',
]
