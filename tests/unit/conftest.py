from __future__ import annotations

import asyncio
import inspect
import os
from collections import defaultdict
from logging import getLogger
from typing import TYPE_CHECKING, Any, get_type_hints

import impit
import pytest
from pytest_httpserver import HTTPServer

from apify_client import ApifyClientAsync
from apify_shared.consts import ApifyEnvVars
from crawlee import service_locator

import apify._actor
import apify.log
from apify.storage_clients._apify._alias_resolving import AliasResolver

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from logging import Logger
    from pathlib import Path


@pytest.fixture
def _patch_propagate_logger(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Patch enabling `propagate` for the crawlee logger.

    This is necessary for tests requiring log interception using `caplog`.
    """

    original_configure_logger = apify.log.configure_logger

    def propagate_logger(logger: Logger, **kwargs: Any) -> None:
        original_configure_logger(logger, **kwargs)
        logger.propagate = True

    monkeypatch.setattr('crawlee._log_config.configure_logger', propagate_logger)
    monkeypatch.setattr(apify.log, 'configure_logger', propagate_logger)
    yield
    monkeypatch.undo()


@pytest.fixture
def prepare_test_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[[], None]:
    """Prepare the testing environment by resetting the global state before each test.

    This fixture ensures that the global state of the package is reset to a known baseline before each test runs.
    It also configures a temporary storage directory for test isolation.

    Args:
        monkeypatch: Test utility provided by pytest for patching.
        tmp_path: A unique temporary directory path provided by pytest for test isolation.

    Returns:
        A callable that prepares the test environment.
    """

    def _prepare_test_env() -> None:
        if hasattr(apify._actor.Actor, '__wrapped__'):
            delattr(apify._actor.Actor, '__wrapped__')
        apify._actor.Actor._is_initialized = False

        # Set the environment variable for the local storage directory to the temporary path.
        monkeypatch.setenv(ApifyEnvVars.LOCAL_STORAGE_DIR, str(tmp_path))

        # Reset the services in the service locator.
        service_locator._configuration = None
        service_locator._event_manager = None
        service_locator._storage_client = None
        service_locator.storage_instance_manager.clear_cache()

        # Reset the AliasResolver class state.
        AliasResolver._alias_map = {}
        AliasResolver._alias_init_lock = None

        # Verify that the test environment was set up correctly.
        assert os.environ.get(ApifyEnvVars.LOCAL_STORAGE_DIR) == str(tmp_path)

    return _prepare_test_env


@pytest.fixture(autouse=True)
def _isolate_test_environment(
    prepare_test_env: Callable[[], None],
    _patch_propagate_logger: None,
) -> None:
    """Isolate the testing environment by resetting global state before and after each test.

    This fixture ensures that each test starts with a clean slate and that any modifications during the test
    do not affect subsequent tests. It runs automatically for all tests.

    Args:
        prepare_test_env: Fixture to prepare the environment before each test.
    """

    prepare_test_env()


# This class is used to patch the ApifyClientAsync methods to return a fixed value or be replaced with another method.
class ApifyClientAsyncPatcher:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.calls: dict[str, dict[str, list[tuple[Any, Any]]]] = defaultdict(lambda: defaultdict(list))

    def patch(
        self,
        method: str,
        submethod: str,
        *,
        return_value: Any = None,
        replacement_method: Callable | None = None,
        is_async: bool | None = None,
    ) -> None:
        """
        Patch a method in ApifyClientAsync.

        Patches a submethod in ApifyClientAsync (e.g. `apify_client_async.user().get`)
        to either return a fixed value, or be replaced with another method.
        The patches will be reverted after the test is over.

        One of `return_value` and `replacement_method` arguments must be specified.

        Args:
            method: Which root method to patch in the ApifyClientAsync.
            submethod: Which submethod to patch in the root method's result.
            return_value: What should the patched method return.
            replacement_method: What method should the original method be replaced by.
            is_async: Whether the return value or replacement method should be wrapped by an async wrapper,
                in order to not break any `await` statements.
                If not passed, it is automatically detected from the type of the method which is being replaced.
        """

        client_method = getattr(ApifyClientAsync, method, None)
        if not client_method:
            raise ValueError(f'ApifyClientAsync does not contain method "{method}"!')

        client_method_return_type = get_type_hints(client_method)['return']
        original_submethod = getattr(client_method_return_type, submethod, None)

        if not original_submethod:
            raise ValueError(
                f'apify_client.{client_method_return_type.__name__} does not contain method "{submethod}"!'
            )

        if is_async is None:
            is_async = inspect.iscoroutinefunction(original_submethod)

        if is_async:
            if replacement_method:
                if not inspect.iscoroutinefunction(replacement_method):
                    original_replacement_method = replacement_method

                    async def replacement_method(*args: Any, **kwargs: Any) -> Any:
                        return original_replacement_method(*args, **kwargs)
            else:
                original_return_value = return_value
                return_value = asyncio.Future()
                return_value.set_result(original_return_value)

        if not replacement_method:

            def replacement_method(*_args: Any, **_kwargs: Any) -> Any:
                return return_value

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.calls[method][submethod].append((args, kwargs))

            assert replacement_method is not None
            return replacement_method(*args, **kwargs)

        self.monkeypatch.setattr(client_method_return_type, submethod, wrapper, raising=False)

        original_getattr = getattr(ApifyClientAsync, '__getattr__', None)

        def getattr_override(apify_client_instance: Any, attr_name: str) -> Any:
            if attr_name == 'calls':
                return self.calls

            if original_getattr:
                return original_getattr(apify_client_instance, attr_name)

            return object.__getattribute__(apify_client_instance, attr_name)

        self.monkeypatch.setattr(ApifyClientAsync, '__getattr__', getattr_override, raising=False)


@pytest.fixture
def apify_client_async_patcher(monkeypatch: pytest.MonkeyPatch) -> ApifyClientAsyncPatcher:
    return ApifyClientAsyncPatcher(monkeypatch)


@pytest.fixture(scope='session')
def make_httpserver() -> Iterator[HTTPServer]:
    werkzeug_logger = getLogger('werkzeug')
    werkzeug_logger.disabled = True

    server = HTTPServer(threaded=True, host='127.0.0.1')
    server.start()
    yield server
    server.clear()  # type: ignore[no-untyped-call]
    if server.is_running():
        server.stop()  # type: ignore[no-untyped-call]


@pytest.fixture
def httpserver(make_httpserver: HTTPServer) -> Iterator[HTTPServer]:
    server = make_httpserver
    yield server
    server.clear()  # type: ignore[no-untyped-call]


@pytest.fixture
def patched_impit_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Patch impit client to drop proxy settings."""

    original_async_client = impit.AsyncClient

    def proxyless_async_client(*args: Any, **kwargs: Any) -> impit.AsyncClient:
        kwargs.pop('proxy', None)
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(impit, 'AsyncClient', proxyless_async_client)
    yield
    monkeypatch.undo()
