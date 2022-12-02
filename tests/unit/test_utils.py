import asyncio
import datetime
import os
import unittest

from apify._utils import (
    _fetch_and_parse_env_var,
    _get_cpu_usage_percent,
    _get_memory_usage_bytes,
    _maybe_parse_bool,
    _maybe_parse_datetime,
    _maybe_parse_int,
    _run_func_at_interval_async,
)


class UtilsTest(unittest.IsolatedAsyncioTestCase):
    def test__fetch_and_parse_env_var(self) -> None:
        os.environ['APIFY_IS_AT_HOME'] = 'True'
        os.environ['APIFY_MEMORY_MBYTES'] = '1024'
        os.environ['APIFY_META_ORIGIN'] = 'API'
        os.environ['APIFY_STARTED_AT'] = '2022-12-02T15:19:34.907Z'
        os.environ['DUMMY_BOOL'] = '1'
        os.environ['DUMMY_DATETIME'] = '2022-12-02T15:19:34.907Z'
        os.environ['DUMMY_INT'] = '1'
        os.environ['DUMMY_STRING'] = 'DUMMY'

        self.assertEqual(_fetch_and_parse_env_var('APIFY_IS_AT_HOME'), True)
        self.assertEqual(_fetch_and_parse_env_var('APIFY_MEMORY_MBYTES'), 1024)
        self.assertEqual(_fetch_and_parse_env_var('APIFY_META_ORIGIN'), 'API')
        self.assertEqual(
            _fetch_and_parse_env_var('APIFY_STARTED_AT'),
            datetime.datetime(2022, 12, 2, 15, 19, 34, 907000, tzinfo=datetime.timezone.utc),
        )

        self.assertEqual(_fetch_and_parse_env_var('DUMMY_BOOL'), '1')
        self.assertEqual(_fetch_and_parse_env_var('DUMMY_DATETIME'), '2022-12-02T15:19:34.907Z')
        self.assertEqual(_fetch_and_parse_env_var('DUMMY_INT'), '1')
        self.assertEqual(_fetch_and_parse_env_var('DUMMY_STRING'), 'DUMMY')
        self.assertEqual(_fetch_and_parse_env_var('NONEXISTENT_ENV_VAR'), None)
        self.assertEqual(_fetch_and_parse_env_var('NONEXISTENT_ENV_VAR', 'default'), 'default')

    def test__get_cpu_usage_percent(self) -> None:
        self.assertGreaterEqual(_get_cpu_usage_percent(), 0)
        self.assertLessEqual(_get_cpu_usage_percent(), 100)

    def test__get_memory_usage_bytes(self) -> None:
        self.assertGreaterEqual(_get_memory_usage_bytes(), 0)
        self.assertLessEqual(_get_memory_usage_bytes(), 1024 * 1024 * 1024 * 1024)

    def test__maybe_parse_bool(self) -> None:
        self.assertEqual(_maybe_parse_bool('True'), True)
        self.assertEqual(_maybe_parse_bool('true'), True)
        self.assertEqual(_maybe_parse_bool('1'), True)
        self.assertEqual(_maybe_parse_bool('False'), False)
        self.assertEqual(_maybe_parse_bool('false'), False)
        self.assertEqual(_maybe_parse_bool('0'), False)
        self.assertEqual(_maybe_parse_bool(None), False)
        self.assertEqual(_maybe_parse_bool('bflmpsvz'), False)

    def test__maybe_parse_datetime(self) -> None:
        self.assertEqual(
            _maybe_parse_datetime('2022-12-02T15:19:34.907Z'),
            datetime.datetime(2022, 12, 2, 15, 19, 34, 907000, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(_maybe_parse_datetime('2022-12-02T15:19:34.907'), '2022-12-02T15:19:34.907')
        self.assertEqual(_maybe_parse_datetime('anything'), 'anything')
        self.assertEqual(_maybe_parse_datetime(None), None)

    def test__maybe_parse_int(self) -> None:
        self.assertEqual(_maybe_parse_int('0'), 0)
        self.assertEqual(_maybe_parse_int('1'), 1)
        self.assertEqual(_maybe_parse_int('-1'), -1)
        self.assertEqual(_maybe_parse_int('136749825'), 136749825)
        self.assertEqual(_maybe_parse_int(''), None)
        self.assertEqual(_maybe_parse_int(None), None)

    async def test__run_func_at_interval_async(self) -> None:
        # Test that it works with a synchronous functions
        test_var = 0

        def sync_increment() -> None:
            nonlocal test_var
            test_var += 1

        sync_increment_task = asyncio.create_task(_run_func_at_interval_async(sync_increment, 0.3))

        await asyncio.sleep(0.2)
        self.assertEqual(test_var, 0)
        await asyncio.sleep(0.3)
        self.assertEqual(test_var, 1)
        await asyncio.sleep(0.3)
        self.assertEqual(test_var, 2)
        await asyncio.sleep(0.3)
        self.assertEqual(test_var, 3)

        sync_increment_task.cancel()

        await asyncio.sleep(1)
        self.assertEqual(test_var, 3)

        # Test that it works with an asynchronous functions
        test_var = 0

        async def async_increment() -> None:
            nonlocal test_var
            await asyncio.sleep(0.1)
            test_var += 1

        async_increment_task = asyncio.create_task(_run_func_at_interval_async(async_increment, 0.3))

        await asyncio.sleep(0.2)
        self.assertEqual(test_var, 0)
        await asyncio.sleep(0.3)
        self.assertEqual(test_var, 1)
        await asyncio.sleep(0.3)
        self.assertEqual(test_var, 2)
        await asyncio.sleep(0.3)
        self.assertEqual(test_var, 3)

        async_increment_task.cancel()

        await asyncio.sleep(1)
        self.assertEqual(test_var, 3)
