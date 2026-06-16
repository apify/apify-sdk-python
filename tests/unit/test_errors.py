from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from apify_client._models import Run
from apify_client.errors import (
    ApifyApiError,
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
    ServerError,
    UnauthorizedError,
)
from apify_client.errors import RateLimitError as ClientRateLimitError

import apify
from apify.errors import (
    ActorAuthenticationError,
    ActorChargeLimitExceededError,
    ActorError,
    ActorInputValidationError,
    ActorRateLimitError,
    ActorRunError,
    ActorTimeoutError,
)


class _FakeResponse:
    """Minimal stand-in for `apify_client`'s HTTP response, enough to build its API errors."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = 'error text'

    def json(self) -> dict[str, Any]:
        return {'error': {'message': 'boom', 'type': 'some-error-type'}}


def _client_error(error_cls: type[ApifyApiError], status_code: int) -> ApifyApiError:
    return error_cls(cast('Any', _FakeResponse(status_code)), 1)


def _make_run(*, status: str, exit_code: int | None = None, status_message: str | None = None) -> Run:
    return Run.model_validate(
        {
            'id': 'run123',
            'actId': 'act123',
            'userId': 'user123',
            'startedAt': datetime.now(UTC).isoformat(),
            'status': status,
            'statusMessage': status_message,
            'exitCode': exit_code,
            'meta': {'origin': 'DEVELOPMENT'},
            'buildId': 'build123',
            'defaultDatasetId': 'ds123',
            'defaultKeyValueStoreId': 'kvs123',
            'defaultRequestQueueId': 'rq123',
            'containerUrl': 'https://container',
            'buildNumber': '0.0.1',
            'generalAccess': 'RESTRICTED',
            'stats': {'restartCount': 0, 'resurrectCount': 0, 'computeUnits': 1},
            'options': {'build': 'latest', 'timeoutSecs': 4, 'memoryMbytes': 1024, 'diskMbytes': 1024},
        }
    )


def test_actor_error_defaults() -> None:
    error = ActorError('something went wrong')
    assert error.code == 'apify-error'
    assert error.retryable is False
    assert str(error) == 'something went wrong'


def test_actor_error_overrides_are_instance_scoped() -> None:
    error = ActorError('boom', code='custom', retryable=True)
    assert error.code == 'custom'
    assert error.retryable is True
    # Overriding on an instance must not leak to the class default.
    assert ActorError.code == 'apify-error'
    assert ActorError.retryable is False


@pytest.mark.parametrize(
    ('error_cls', 'expected_code', 'expected_retryable'),
    [
        (ActorRateLimitError, 'rate-limit-exceeded', True),
        (ActorTimeoutError, 'actor-timed-out', True),
        (ActorAuthenticationError, 'authentication-error', False),
        (ActorChargeLimitExceededError, 'charge-limit-exceeded', False),
        (ActorInputValidationError, 'input-validation-error', False),
        (ActorRunError, 'actor-run-failed', False),
    ],
)
def test_subclass_codes_and_retryable(
    error_cls: type[ActorError], expected_code: str, *, expected_retryable: bool
) -> None:
    assert error_cls.code == expected_code
    assert error_cls.retryable is expected_retryable
    assert issubclass(error_cls, ActorError)


def test_input_validation_error_is_value_error() -> None:
    """`except ValueError` must still catch `ActorInputValidationError`."""
    with pytest.raises(ValueError, match='bad input'):
        raise ActorInputValidationError('bad input')


def test_actor_timeout_error_is_actor_run_error() -> None:
    assert issubclass(ActorTimeoutError, ActorRunError)


def test_actor_run_error_carries_run_metadata() -> None:
    run = _make_run(status='FAILED', exit_code=1, status_message='Actor crashed')
    error = ActorRunError(run)
    assert error.run_id == 'run123'
    assert error.status == 'FAILED'
    assert error.exit_code == 1
    assert error.status_message == 'Actor crashed'
    assert error.retryable is False
    assert 'run123' in str(error)
    assert 'Actor crashed' in str(error)


def test_actor_run_error_from_run_failed() -> None:
    error = ActorRunError.from_run(_make_run(status='FAILED'))
    assert type(error) is ActorRunError
    assert not error.retryable


def test_actor_run_error_from_run_timed_out() -> None:
    error = ActorRunError.from_run(_make_run(status='TIMED-OUT'))
    assert isinstance(error, ActorTimeoutError)
    assert error.retryable is True
    assert error.run_id == 'run123'
    assert error.code == 'actor-timed-out'


@pytest.mark.parametrize(
    ('client_error', 'expected_cls', 'expected_retryable'),
    [
        (_client_error(UnauthorizedError, 401), ActorAuthenticationError, False),
        (_client_error(ForbiddenError, 403), ActorAuthenticationError, False),
        (_client_error(ClientRateLimitError, 429), ActorRateLimitError, True),
        (_client_error(ServerError, 500), ActorError, True),
        (_client_error(InvalidRequestError, 400), ActorInputValidationError, False),
        (_client_error(NotFoundError, 404), ActorError, False),
        (_client_error(ConflictError, 409), ActorError, False),
    ],
)
def test_from_client_error_mapping(
    client_error: ApifyApiError,
    expected_cls: type[ActorError],
    *,
    expected_retryable: bool,
) -> None:
    mapped = ActorError.from_client_error(client_error)
    assert type(mapped) is expected_cls
    assert mapped.retryable is expected_retryable


def test_from_client_error_unknown_exception_falls_back() -> None:
    mapped = ActorError.from_client_error(RuntimeError('not a client error'))
    assert type(mapped) is ActorError
    assert mapped.retryable is False
    assert 'not a client error' in str(mapped)


def test_errors_exported_from_top_level() -> None:
    for name in (
        'ActorError',
        'ActorRunError',
        'ActorTimeoutError',
        'ActorAuthenticationError',
        'ActorChargeLimitExceededError',
        'ActorInputValidationError',
        'ActorRateLimitError',
    ):
        assert hasattr(apify, name)
        assert name in apify.__all__
        assert getattr(apify, name) is getattr(apify.errors, name)
