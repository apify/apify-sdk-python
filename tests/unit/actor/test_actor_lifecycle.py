from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from apify_shared.consts import ActorExitCodes, ApifyEnvVars
from crawlee.events._types import Event

from apify import Actor

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from apify._actor import _ActorType


@pytest.fixture(
    params=[
        pytest.param(('instance', 'manual'), id='instance-manual'),
        pytest.param(('instance', 'async_with'), id='instance-async-with'),
        pytest.param(('class', 'manual'), id='class-manual'),
        pytest.param(('class', 'async_with'), id='class-async-with'),
    ]
)
async def actor(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[_ActorType, None]:
    """Yield Actor instance or class in different initialization modes.

    - instance-manual: Actor() with manual init()/exit()
    - instance-async-with: Actor() used as async context manager
    - class-manual: Actor class with manual init()/exit()
    - class-async-with: Actor class used as async context manager

    Each Actor is properly initialized before yielding and cleaned up after.
    """
    scope, mode = request.param

    if scope == 'instance':
        if mode == 'manual':
            instance = Actor()
            await instance.init()
            yield instance
            await instance.exit()
        else:
            async with Actor() as instance:
                yield instance

    elif scope == 'class':
        if mode == 'manual':
            await Actor.init()
            yield Actor
            await Actor.exit()
        else:
            async with Actor:
                yield Actor

    else:
        raise ValueError(f'Unknown scope: {scope}')


async def test_actor_init_instance_manual() -> None:
    """Test that Actor instance can be properly initialized and cleaned up manually."""
    actor = Actor()
    await actor.init()
    assert actor._is_initialized is True
    await actor.exit()
    assert actor._is_initialized is False


async def test_actor_init_instance_async_with() -> None:
    """Test that Actor instance can be properly initialized and cleaned up using async context manager."""
    actor = Actor()
    async with actor:
        assert actor._is_initialized is True

    assert actor._is_initialized is False


async def test_actor_init_class_manual() -> None:
    """Test that Actor class can be properly initialized and cleaned up manually."""
    await Actor.init()
    assert Actor._is_initialized is True
    await Actor.exit()
    assert not Actor._is_initialized


async def test_actor_init_class_async_with() -> None:
    """Test that Actor class can be properly initialized and cleaned up using async context manager."""
    async with Actor:
        assert Actor._is_initialized is True

    assert not Actor._is_initialized


async def test_fail_properly_deinitializes_actor(actor: _ActorType) -> None:
    """Test that fail() method properly deinitializes the Actor."""
    assert actor._is_initialized
    await actor.fail()
    assert actor._is_initialized is False


async def test_actor_handles_exceptions_and_cleans_up_properly() -> None:
    """Test that Actor properly cleans up when an exception occurs in the async context manager."""
    actor = None

    with contextlib.suppress(Exception):
        async with Actor() as actor:
            assert actor._is_initialized
            raise Exception('Failed')  # noqa: TRY002

    assert actor is not None
    assert actor._is_initialized is False


async def test_double_init_raises_runtime_error(actor: _ActorType) -> None:
    """Test that attempting to initialize an already initialized Actor raises RuntimeError."""
    assert actor._is_initialized
    with pytest.raises(RuntimeError):
        await actor.init()


async def test_exit_without_init_raises_runtime_error() -> None:
    """Test that calling exit() on an uninitialized Actor raises RuntimeError."""
    with pytest.raises(RuntimeError):
        await Actor.exit()

    with pytest.raises(RuntimeError):
        await Actor().exit()


async def test_fail_without_init_raises_runtime_error() -> None:
    """Test that calling fail() on an uninitialized Actor raises RuntimeError."""
    with pytest.raises(RuntimeError):
        await Actor.fail()

    with pytest.raises(RuntimeError):
        await Actor().fail()


async def test_reboot_in_local_environment_logs_error_message(
    actor: _ActorType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that reboot() logs an error when not running on the Apify platform."""
    await actor.reboot()

    # Check that the error message was logged
    assert 'Actor.reboot() is only supported when running on the Apify platform.' in caplog.text


async def test_exit_sets_custom_exit_code_and_status_message(actor: _ActorType) -> None:
    """Test that exit() properly sets custom exit code and status message."""
    await actor.exit(exit_code=42, status_message='Exiting with code 42')
    assert actor.exit_code == 42
    assert actor.status_message == 'Exiting with code 42'


async def test_fail_sets_custom_exit_code_and_status_message(actor: _ActorType) -> None:
    """Test that fail() properly sets custom exit code and status message."""
    await actor.fail(exit_code=99, status_message='Failing with code 99')
    assert actor.exit_code == 99
    assert actor.status_message == 'Failing with code 99'


async def test_unhandled_exception_sets_error_exit_code() -> None:
    """Test that unhandled exceptions in context manager set the error exit code."""
    actor = Actor(exit_process=False)
    with pytest.raises(RuntimeError):
        async with actor:
            raise RuntimeError('Test error')

    assert actor.exit_code == ActorExitCodes.ERROR_USER_FUNCTION_THREW.value


async def test_actor_stops_periodic_events_after_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that periodic events (PERSIST_STATE and SYSTEM_INFO) stop emitting after Actor exits."""
    monkeypatch.setenv(ApifyEnvVars.SYSTEM_INFO_INTERVAL_MILLIS, '100')
    monkeypatch.setenv(ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS, '100')
    on_persist = []
    on_system_info = []

    def on_event(event_type: Event) -> Callable:
        nonlocal on_persist
        nonlocal on_system_info
        if event_type == Event.PERSIST_STATE:
            return on_persist.append
        if event_type == Event.SYSTEM_INFO:
            return on_system_info.append
        return print

    actor = Actor()
    async with actor:
        assert actor._is_initialized
        actor.on(Event.PERSIST_STATE, on_event(Event.PERSIST_STATE))
        actor.on(Event.SYSTEM_INFO, on_event(Event.SYSTEM_INFO))
        await asyncio.sleep(1)

    on_persist_count = len(on_persist)
    on_system_info_count = len(on_system_info)
    assert on_persist_count != 0
    assert on_system_info_count != 0

    # Check if events stopped emitting.
    await asyncio.sleep(0.2)
    assert on_persist_count == len(on_persist)
    assert on_system_info_count == len(on_system_info)


async def test_actor_fail_prevents_further_execution(caplog: pytest.LogCaptureFixture) -> None:
    """Test that calling Actor.fail() prevents further code execution in the Actor context."""
    caplog.set_level(logging.INFO)
    try:
        # Explicitly set exit_process=True since in Pytest env it defaults to False.
        async with Actor(exit_process=True) as actor:
            await actor.fail(exit_code=2, exception=Exception('abc'), status_message='cde')
            raise RuntimeError('This should not trigger')
    except SystemExit:
        fail_records = [r for r in caplog.records if r.msg == 'Actor failed with an exception']
        assert len(fail_records) == 1
        assert fail_records[0].levelno == logging.ERROR
        assert fail_records[0].exc_text == 'Exception: abc'

        exit_records = [r for r in caplog.records if r.msg == 'Exiting Actor']
        assert len(exit_records) == 1
        assert exit_records[0].levelno == logging.INFO

        status_records = [r for r in caplog.records if r.msg == '[Terminal status message]: cde']
        assert len(status_records) == 1
        assert status_records[0].levelno == logging.INFO


@pytest.mark.parametrize(
    ('first_with_call', 'second_with_call'),
    [
        pytest.param(False, False, id='both_without_call'),
        pytest.param(False, True, id='first_without_call'),
        pytest.param(True, False, id='second_without_call'),
        pytest.param(True, True, id='both_with_call'),
    ],
)
async def test_actor_sequential_contexts(*, first_with_call: bool, second_with_call: bool) -> None:
    """Test that Actor and Actor() can be used in two sequential async context manager blocks."""
    mock = AsyncMock()
    async with Actor(exit_process=False) if first_with_call else Actor as actor:
        await mock()
        assert actor._is_initialized is True

    # After exiting the context, new Actor instance can be created without conflicts.
    async with Actor() if second_with_call else Actor as actor:
        await mock()
        assert actor._is_initialized is True

    # The mock should have been called twice, once in each context.
    assert mock.call_count == 2
