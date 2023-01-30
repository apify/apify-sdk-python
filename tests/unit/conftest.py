import asyncio
import inspect
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple, get_type_hints

import pytest

from apify import Actor
from apify.config import Configuration
from apify.memory_storage import MemoryStorage
from apify.storage_client_manager import StorageClientManager
from apify.storages import StorageManager
from apify_client.client import ApifyClientAsync


# To isolate the tests, we need to reset the used singletons before each test case
# We also patch the default storage client with a tmp_path
@pytest.fixture(autouse=True)
def reset_and_patch_default_instances(monkeypatch: pytest.MonkeyPatch, tmp_path: str) -> None:
    monkeypatch.setattr(Actor, '_default_instance', None)
    monkeypatch.setattr(Configuration, '_default_instance', None)
    monkeypatch.setattr(StorageManager, '_default_instance', None)
    monkeypatch.setattr(StorageClientManager, '_default_instance', None)
    patched_memory_storage = MemoryStorage(local_data_directory=tmp_path)

    def get_storage_client() -> 'MemoryStorage':
        return patched_memory_storage
    monkeypatch.setattr(StorageClientManager, 'get_storage_client', get_storage_client)


# TODO: decide if this is worth maintaining
# We could just mock the Apify API HTTP responses with respx and get the same results
# (but this was fun to write!)
class ApifyClientAsyncPatcher:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.calls: Dict[str, Dict[str, List[Tuple[Any, Any]]]] = defaultdict(lambda: defaultdict(list))

    def patch(
        self,
        method: str,
        submethod: str,
        *,
        return_value: Optional[Any] = None,
        replacement_method: Optional[Callable] = None,
        is_async: Optional[bool] = None,
    ) -> None:
        """
        Patch a method in ApifyClientAsync.

        Patches a submethod in ApifyClientAsync (e.g. `apify_client_async.user().get`)
        to either return a fixed value, or be replaced with another method.
        The patches will be reverted after the test is over.

        One of `return_value` and `replacement_method` arguments must be specified.

        Args:
            method (str): Which root method to patch in the ApifyClientAsync.
            submethod (str): Which submethod to patch in the root method's result.
            return_value (optional, Any): What should the patched method return.
            replacement_method (optional, Callable): What method should the original method be replaced by.
            is_async (optional, bool): Whether the return value or replacement method should be wrapped by an async wrapper,
                                       in order to not break any `await` statements.
                                       If not passed, it is automatically detected from the type of the method which is being replaced.
        """

        client_method = getattr(ApifyClientAsync, method, None)
        if not client_method:
            raise ValueError(f'ApifyClientAsync does not contain method "{method}"!')

        client_method_return_type = get_type_hints(client_method)['return']
        original_submethod = getattr(client_method_return_type, submethod, None)

        if not original_submethod:
            raise ValueError(f'apify_client.{client_method_return_type.__name__} does not contain method "{submethod}"!')

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
            def replacement_method(*_args: Any, **_kwargs: Any) -> Optional[Any]:
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


@pytest.fixture()
def memory_storage(tmp_path: str) -> MemoryStorage:
    return MemoryStorage(local_data_directory=tmp_path)
