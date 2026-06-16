from __future__ import annotations

from typing import TYPE_CHECKING

from apify_client.errors import ForbiddenError as _ForbiddenError
from apify_client.errors import InvalidRequestError as _InvalidRequestError
from apify_client.errors import RateLimitError as _RateLimitError
from apify_client.errors import ServerError as _ServerError
from apify_client.errors import UnauthorizedError as _UnauthorizedError

from apify._utils import docs_group

if TYPE_CHECKING:
    from apify_client._models import Run


@docs_group('Errors')
class ActorError(Exception):
    """Base class for all domain-level Apify SDK errors.

    Carries a machine-readable `code` and a `retryable` flag so callers can branch on a failure without reading
    the human-readable error message.
    """

    code: str = 'actor-error'
    """Stable, machine-readable identifier of the error category."""

    retryable: bool = False
    """Whether retrying the same operation might succeed (e.g. a transient rate limit or server error)."""

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

    @classmethod
    def from_client_error(cls, error: Exception) -> ActorError:
        """Map an `apify_client` exception to the matching domain-level error.

        The mapping is driven by the client's typed, HTTP-status-based exceptions. Unmapped client errors (and any
        other exception) fall back to a plain `ActorError`. The original exception is not chained automatically;
        callers should use `raise ActorError.from_client_error(err) from err`.

        Args:
            error: The exception raised by `apify_client`.

        Returns:
            The corresponding domain-level error.
        """
        if isinstance(error, (_UnauthorizedError, _ForbiddenError)):
            return ActorAuthenticationError(str(error))

        if isinstance(error, _RateLimitError):
            return ActorRateLimitError(str(error))

        if isinstance(error, _ServerError):
            return ActorError(str(error), retryable=True)

        if isinstance(error, _InvalidRequestError):
            return ActorInputValidationError(str(error))

        return ActorError(str(error))


@docs_group('Errors')
class ActorRunError(ActorError):
    """Raised when an Actor run reaches a terminal failure state (e.g. `FAILED` or `ABORTED`).

    Unlike the HTTP-derived errors, this one is derived from the run itself, so it exposes the run metadata needed
    to decide what to do next.
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
    """Raised when an Actor run exceeds its timeout (`TIMED-OUT`). Retrying with a longer timeout may help."""

    code = 'actor-timed-out'
    retryable = True


@docs_group('Errors')
class ActorInputValidationError(ActorError, ValueError):
    """Raised when input fails validation.

    Subclasses `ValueError` so existing `except ValueError` handlers keep catching it.
    """

    code = 'input-validation-error'


@docs_group('Errors')
class ActorChargeLimitExceededError(ActorError):
    """Raised when an Actor run hits its configured maximum total charge (`max_total_charge_usd`)."""

    code = 'charge-limit-exceeded'


@docs_group('Errors')
class ActorAuthenticationError(ActorError):
    """Raised when an API request is unauthorized or forbidden (HTTP 401 / 403)."""

    code = 'authentication-error'


@docs_group('Errors')
class ActorRateLimitError(ActorError):
    """Raised when the Apify API rate limit is exceeded (HTTP 429). Retryable after a backoff."""

    code = 'rate-limit-exceeded'
    retryable = True


__all__ = [
    'ActorAuthenticationError',
    'ActorChargeLimitExceededError',
    'ActorError',
    'ActorInputValidationError',
    'ActorRateLimitError',
    'ActorRunError',
    'ActorTimeoutError',
]
