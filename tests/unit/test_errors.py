from __future__ import annotations

from datetime import UTC, datetime

import apify_client.errors as client_errors
from apify_client._models import Run

from apify.errors import ActorError, ActorRunError, ActorTimeoutError


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


# Base error.


def test_actor_error_defaults() -> None:
    error = ActorError('something went wrong')
    assert error.code == 'actor-error'
    assert error.retryable is False
    assert str(error) == 'something went wrong'


def test_actor_error_overrides_are_instance_scoped() -> None:
    error = ActorError('boom', code='custom', retryable=True)
    assert error.code == 'custom'
    assert error.retryable is True
    # Overriding on an instance must not leak to the class default.
    assert ActorError.code == 'actor-error'
    assert ActorError.retryable is False


# Run errors.


def test_actor_run_error_is_actor_error() -> None:
    assert issubclass(ActorRunError, ActorError)
    assert ActorRunError.code == 'actor-run-failed'
    assert ActorRunError.retryable is False


def test_actor_timeout_error_is_actor_run_error() -> None:
    assert issubclass(ActorTimeoutError, ActorRunError)
    assert ActorTimeoutError.code == 'actor-timed-out'
    assert ActorTimeoutError.retryable is True


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


# Re-exported API client errors.


def test_client_errors_are_re_exported() -> None:
    """`apify.errors` re-exports the API client error hierarchy so callers have a single import location."""
    from apify.errors import ApifyApiError, ApifyClientError, NotFoundError, RateLimitError

    assert ApifyApiError is client_errors.ApifyApiError
    assert ApifyClientError is client_errors.ApifyClientError
    assert NotFoundError is client_errors.NotFoundError
    assert RateLimitError is client_errors.RateLimitError
    # The re-exported API errors are independent of the SDK's own `ActorError` tree.
    assert not issubclass(client_errors.ApifyApiError, ActorError)
