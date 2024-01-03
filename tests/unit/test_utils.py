from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pytest
from aiofiles.os import mkdir

from apify_shared.consts import ActorEnvVars, ApifyEnvVars

from apify._utils import (
    budget_ow,
    fetch_and_parse_env_var,
    force_remove,
    force_rename,
    get_cpu_usage_percent,
    get_memory_usage_bytes,
    guess_file_extension,
    maybe_parse_bool,
    maybe_parse_datetime,
    maybe_parse_int,
    raise_on_duplicate_storage,
    raise_on_non_existing_storage,
    run_func_at_interval_async,
    unique_key_to_request_id,
)
from apify.consts import StorageTypes

if TYPE_CHECKING:
    from pathlib import Path


def test__fetch_and_parse_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, 'True')
    monkeypatch.setenv(ActorEnvVars.MEMORY_MBYTES, '1024')
    monkeypatch.setenv(ApifyEnvVars.META_ORIGIN, 'API')
    monkeypatch.setenv(ActorEnvVars.STARTED_AT, '2022-12-02T15:19:34.907Z')
    monkeypatch.setenv('DUMMY_BOOL', '1')
    monkeypatch.setenv('DUMMY_DATETIME', '2022-12-02T15:19:34.907Z')
    monkeypatch.setenv('DUMMY_INT', '1')
    monkeypatch.setenv('DUMMY_STRING', 'DUMMY')

    assert fetch_and_parse_env_var(ApifyEnvVars.IS_AT_HOME) is True
    assert fetch_and_parse_env_var(ActorEnvVars.MEMORY_MBYTES) == 1024
    assert fetch_and_parse_env_var(ApifyEnvVars.META_ORIGIN) == 'API'
    assert fetch_and_parse_env_var(ActorEnvVars.STARTED_AT) == datetime(2022, 12, 2, 15, 19, 34, 907000, tzinfo=timezone.utc)

    assert fetch_and_parse_env_var('DUMMY_BOOL') == '1'  # type: ignore
    assert fetch_and_parse_env_var('DUMMY_DATETIME') == '2022-12-02T15:19:34.907Z'  # type: ignore
    assert fetch_and_parse_env_var('DUMMY_INT') == '1'  # type: ignore
    assert fetch_and_parse_env_var('DUMMY_STRING') == 'DUMMY'  # type: ignore
    assert fetch_and_parse_env_var('NONEXISTENT_ENV_VAR') is None  # type: ignore
    assert fetch_and_parse_env_var('NONEXISTENT_ENV_VAR', 'default') == 'default'  # type: ignore


def test__get_cpu_usage_percent() -> None:
    assert get_cpu_usage_percent() >= 0
    assert get_cpu_usage_percent() <= 100


def test__get_memory_usage_bytes() -> None:
    assert get_memory_usage_bytes() >= 0
    assert get_memory_usage_bytes() <= 1024 * 1024 * 1024 * 1024


def test__maybe_parse_bool() -> None:
    assert maybe_parse_bool('True') is True
    assert maybe_parse_bool('true') is True
    assert maybe_parse_bool('1') is True
    assert maybe_parse_bool('False') is False
    assert maybe_parse_bool('false') is False
    assert maybe_parse_bool('0') is False
    assert maybe_parse_bool(None) is False
    assert maybe_parse_bool('bflmpsvz') is False


def test__maybe_parse_datetime() -> None:
    assert maybe_parse_datetime('2022-12-02T15:19:34.907Z') == datetime(2022, 12, 2, 15, 19, 34, 907000, tzinfo=timezone.utc)
    assert maybe_parse_datetime('2022-12-02T15:19:34.907') == '2022-12-02T15:19:34.907'
    assert maybe_parse_datetime('anything') == 'anything'


def test__maybe_parse_int() -> None:
    assert maybe_parse_int('0') == 0
    assert maybe_parse_int('1') == 1
    assert maybe_parse_int('-1') == -1
    assert maybe_parse_int('136749825') == 136749825
    assert maybe_parse_int('') is None
    assert maybe_parse_int('abcd') is None


async def test__run_func_at_interval_async__sync_function() -> None:
    # Test that it works with a synchronous functions
    interval = 1.0
    initial_delay = 0.5
    increments = 3

    test_var = 0

    def sync_increment() -> None:
        nonlocal test_var
        test_var += 1

    started_at = time.perf_counter()
    sync_increment_task = asyncio.create_task(run_func_at_interval_async(sync_increment, interval))

    try:
        await asyncio.sleep(initial_delay)

        for i in range(increments):
            assert test_var == i

            now = time.perf_counter()
            sleep_until = started_at + initial_delay + (i + 1) * interval
            sleep_for_secs = sleep_until - now
            await asyncio.sleep(sleep_for_secs)

        assert test_var == increments
    finally:
        sync_increment_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sync_increment_task

    await asyncio.sleep(1.5)
    assert test_var == increments


async def test__run_func_at_interval_async_async__function() -> None:
    # Test that it works with an asynchronous functions
    interval = 1.0
    initial_delay = 0.5
    increments = 3

    test_var = 0

    async def async_increment() -> None:
        nonlocal test_var
        await asyncio.sleep(0.1)
        test_var += 1

    started_at = time.perf_counter()
    async_increment_task = asyncio.create_task(run_func_at_interval_async(async_increment, interval))

    try:
        await asyncio.sleep(initial_delay)

        for i in range(increments):
            assert test_var == i

            now = time.perf_counter()
            sleep_until = started_at + initial_delay + (i + 1) * interval
            sleep_for_secs = sleep_until - now
            await asyncio.sleep(sleep_for_secs)

        assert test_var == increments
    finally:
        async_increment_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await async_increment_task

    await asyncio.sleep(1.5)
    assert test_var == increments


async def test__force_remove(tmp_path: Path) -> None:
    test_file_path = os.path.join(tmp_path, 'test.txt')
    # Does not crash/raise when the file does not exist
    assert os.path.exists(test_file_path) is False
    await force_remove(test_file_path)
    assert os.path.exists(test_file_path) is False

    # Removes the file if it exists
    with open(test_file_path, 'a', encoding='utf-8'):  # noqa: ASYNC101
        pass
    assert os.path.exists(test_file_path) is True
    await force_remove(test_file_path)
    assert os.path.exists(test_file_path) is False


def test__raise_on_non_existing_storage() -> None:
    with pytest.raises(ValueError, match='Dataset with id "kckxQw6j6AtrgyA09" does not exist.'):
        raise_on_non_existing_storage(StorageTypes.DATASET, 'kckxQw6j6AtrgyA09')


def test__raise_on_duplicate_storage() -> None:
    with pytest.raises(ValueError, match='Dataset with name "test" already exists.'):
        raise_on_duplicate_storage(StorageTypes.DATASET, 'name', 'test')


def test__guess_file_extension() -> None:
    # Can guess common types properly
    assert guess_file_extension('application/json') == 'json'
    assert guess_file_extension('application/xml') == 'xml'
    assert guess_file_extension('text/plain') == 'txt'

    # Can handle unusual formats
    assert guess_file_extension(' application/json ') == 'json'
    assert guess_file_extension('APPLICATION/JSON') == 'json'
    assert guess_file_extension('application/json;charset=utf-8') == 'json'

    # Returns None for non-existent content types
    assert guess_file_extension('clearly not a content type') is None
    assert guess_file_extension('') is None


def test__unique_key_to_request_id() -> None:
    # Right side from `uniqueKeyToRequestId` in Crawlee
    assert unique_key_to_request_id('abc') == 'ungWv48BzpBQUDe'
    assert unique_key_to_request_id('test') == 'n4bQgYhMfWWaLqg'


async def test__force_rename(tmp_path: Path) -> None:
    src_dir = os.path.join(tmp_path, 'src')
    dst_dir = os.path.join(tmp_path, 'dst')
    src_file = os.path.join(src_dir, 'src_dir.txt')
    dst_file = os.path.join(dst_dir, 'dst_dir.txt')
    # Won't crash if source directory does not exist
    assert os.path.exists(src_dir) is False
    await force_rename(src_dir, dst_dir)

    # Will remove dst_dir if it exists (also covers normal case)
    # Create the src_dir with a file in it
    await mkdir(src_dir)
    with open(src_file, 'a', encoding='utf-8'):  # noqa: ASYNC101
        pass
    # Create the dst_dir with a file in it
    await mkdir(dst_dir)
    with open(dst_file, 'a', encoding='utf-8'):  # noqa: ASYNC101
        pass
    assert os.path.exists(src_file) is True
    assert os.path.exists(dst_file) is True
    await force_rename(src_dir, dst_dir)
    assert os.path.exists(src_dir) is False
    assert os.path.exists(dst_file) is False
    # src_dir.txt should exist in dst_dir
    assert os.path.exists(os.path.join(dst_dir, 'src_dir.txt')) is True


def test__budget_ow() -> None:
    budget_ow(
        {
            'a': 123,
            'b': 'string',
            'c': datetime.now(timezone.utc),
        },
        {
            'a': (int, True),
            'b': (str, False),
            'c': (datetime, True),
        },
    )
    with pytest.raises(ValueError, match='required'):
        budget_ow({}, {'id': (str, True)})
    with pytest.raises(ValueError, match='must be of type'):
        budget_ow({'id': 123}, {'id': (str, True)})
    # Check if subclasses pass the check
    budget_ow(
        {
            'ordered_dict': OrderedDict(),
        },
        {
            'ordered_dict': (dict, False),
        },
    )
