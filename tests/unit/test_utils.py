import asyncio
import contextlib
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiofiles.os import mkdir

from apify._utils import (
    _budget_ow,
    _fetch_and_parse_env_var,
    _force_remove,
    _force_rename,
    _get_cpu_usage_percent,
    _get_memory_usage_bytes,
    _guess_file_extension,
    _maybe_parse_bool,
    _maybe_parse_datetime,
    _maybe_parse_int,
    _raise_on_duplicate_storage,
    _raise_on_non_existing_storage,
    _run_func_at_interval_async,
    _unique_key_to_request_id,
)
from apify.consts import _StorageTypes
from apify_shared.consts import ApifyEnvVars


def test__fetch_and_parse_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, 'True')
    monkeypatch.setenv(ApifyEnvVars.MEMORY_MBYTES, '1024')
    monkeypatch.setenv(ApifyEnvVars.META_ORIGIN, 'API')
    monkeypatch.setenv(ApifyEnvVars.STARTED_AT, '2022-12-02T15:19:34.907Z')
    monkeypatch.setenv('DUMMY_BOOL', '1')
    monkeypatch.setenv('DUMMY_DATETIME', '2022-12-02T15:19:34.907Z')
    monkeypatch.setenv('DUMMY_INT', '1')
    monkeypatch.setenv('DUMMY_STRING', 'DUMMY')

    assert _fetch_and_parse_env_var(ApifyEnvVars.IS_AT_HOME) is True
    assert _fetch_and_parse_env_var(ApifyEnvVars.MEMORY_MBYTES) == 1024
    assert _fetch_and_parse_env_var(ApifyEnvVars.META_ORIGIN) == 'API'
    assert _fetch_and_parse_env_var(ApifyEnvVars.STARTED_AT) == \
        datetime(2022, 12, 2, 15, 19, 34, 907000, tzinfo=timezone.utc)

    assert _fetch_and_parse_env_var('DUMMY_BOOL') == '1'  # type: ignore
    assert _fetch_and_parse_env_var('DUMMY_DATETIME') == '2022-12-02T15:19:34.907Z'  # type: ignore
    assert _fetch_and_parse_env_var('DUMMY_INT') == '1'  # type: ignore
    assert _fetch_and_parse_env_var('DUMMY_STRING') == 'DUMMY'  # type: ignore
    assert _fetch_and_parse_env_var('NONEXISTENT_ENV_VAR') is None  # type: ignore
    assert _fetch_and_parse_env_var('NONEXISTENT_ENV_VAR', 'default') == 'default'  # type: ignore


def test__get_cpu_usage_percent() -> None:
    assert _get_cpu_usage_percent() >= 0
    assert _get_cpu_usage_percent() <= 100


def test__get_memory_usage_bytes() -> None:
    assert _get_memory_usage_bytes() >= 0
    assert _get_memory_usage_bytes() <= 1024 * 1024 * 1024 * 1024


def test__maybe_parse_bool() -> None:
    assert _maybe_parse_bool('True') is True
    assert _maybe_parse_bool('true') is True
    assert _maybe_parse_bool('1') is True
    assert _maybe_parse_bool('False') is False
    assert _maybe_parse_bool('false') is False
    assert _maybe_parse_bool('0') is False
    assert _maybe_parse_bool(None) is False
    assert _maybe_parse_bool('bflmpsvz') is False


def test__maybe_parse_datetime() -> None:
    assert _maybe_parse_datetime('2022-12-02T15:19:34.907Z') == \
        datetime(2022, 12, 2, 15, 19, 34, 907000, tzinfo=timezone.utc)
    assert _maybe_parse_datetime('2022-12-02T15:19:34.907') == '2022-12-02T15:19:34.907'
    assert _maybe_parse_datetime('anything') == 'anything'


def test__maybe_parse_int() -> None:
    assert _maybe_parse_int('0') == 0
    assert _maybe_parse_int('1') == 1
    assert _maybe_parse_int('-1') == -1
    assert _maybe_parse_int('136749825') == 136749825
    assert _maybe_parse_int('') is None
    assert _maybe_parse_int('abcd') is None


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
    sync_increment_task = asyncio.create_task(_run_func_at_interval_async(sync_increment, interval))

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
    async_increment_task = asyncio.create_task(_run_func_at_interval_async(async_increment, interval))

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
    await _force_remove(test_file_path)
    assert os.path.exists(test_file_path) is False

    # Removes the file if it exists
    open(test_file_path, 'a', encoding='utf-8').close()
    assert os.path.exists(test_file_path) is True
    await _force_remove(test_file_path)
    assert os.path.exists(test_file_path) is False


def test__raise_on_non_existing_storage() -> None:
    with pytest.raises(ValueError, match='Dataset with id "kckxQw6j6AtrgyA09" does not exist.'):
        _raise_on_non_existing_storage(_StorageTypes.DATASET, 'kckxQw6j6AtrgyA09')


def test__raise_on_duplicate_storage() -> None:
    with pytest.raises(ValueError, match='Dataset with name "test" already exists.'):
        _raise_on_duplicate_storage(_StorageTypes.DATASET, 'name', 'test')


def test__guess_file_extension() -> None:
    # Can guess common types properly
    assert _guess_file_extension('application/json') == 'json'
    assert _guess_file_extension('application/xml') == 'xml'
    assert _guess_file_extension('text/plain') == 'txt'

    # Can handle unusual formats
    assert _guess_file_extension(' application/json ') == 'json'
    assert _guess_file_extension('APPLICATION/JSON') == 'json'
    assert _guess_file_extension('application/json;charset=utf-8') == 'json'

    # Returns None for non-existent content types
    assert _guess_file_extension('clearly not a content type') is None
    assert _guess_file_extension('') is None


def test__unique_key_to_request_id() -> None:
    # Right side from `uniqueKeyToRequestId` in Crawlee
    assert _unique_key_to_request_id('abc') == 'ungWv48BzpBQUDe'
    assert _unique_key_to_request_id('test') == 'n4bQgYhMfWWaLqg'


async def test__force_rename(tmp_path: Path) -> None:
    src_dir = os.path.join(tmp_path, 'src')
    dst_dir = os.path.join(tmp_path, 'dst')
    src_file = os.path.join(src_dir, 'src_dir.txt')
    dst_file = os.path.join(dst_dir, 'dst_dir.txt')
    # Won't crash if source directory does not exist
    assert os.path.exists(src_dir) is False
    await _force_rename(src_dir, dst_dir)

    # Will remove dst_dir if it exists (also covers normal case)
    # Create the src_dir with a file in it
    await mkdir(src_dir)
    open(src_file, 'a', encoding='utf-8').close()
    # Create the dst_dir with a file in it
    await mkdir(dst_dir)
    open(dst_file, 'a', encoding='utf-8').close()
    assert os.path.exists(src_file) is True
    assert os.path.exists(dst_file) is True
    await _force_rename(src_dir, dst_dir)
    assert os.path.exists(src_dir) is False
    assert os.path.exists(dst_file) is False
    # src_dir.txt should exist in dst_dir
    assert os.path.exists(os.path.join(dst_dir, 'src_dir.txt')) is True


def test__budget_ow() -> None:
    _budget_ow({
        'a': 123,
        'b': 'string',
        'c': datetime.now(timezone.utc),
    }, {
        'a': (int, True),
        'b': (str, False),
        'c': (datetime, True),
    })
    with pytest.raises(ValueError, match='required'):
        _budget_ow({}, {'id': (str, True)})
    with pytest.raises(ValueError, match='must be of type'):
        _budget_ow({'id': 123}, {'id': (str, True)})
    # Check if subclasses pass the check
    _budget_ow({
        'ordered_dict': OrderedDict(),
    }, {
        'ordered_dict': (dict, False),
    })
