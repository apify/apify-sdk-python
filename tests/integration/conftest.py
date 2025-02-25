from __future__ import annotations

import base64
import inspect
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

import pytest
from filelock import FileLock

from apify_client import ApifyClient, ApifyClientAsync
from apify_shared.consts import ActorJobStatus, ActorSourceType, ApifyEnvVars
from crawlee import service_locator
from crawlee.storages import _creation_management

import apify._actor
from ._utils import generate_unique_resource_name
from apify._models import ActorRun

if TYPE_CHECKING:
    from collections.abc import Awaitable, Coroutine, Iterator, Mapping
    from decimal import Decimal

    from apify_client.clients.resource_clients import ActorClientAsync

_TOKEN_ENV_VAR = 'APIFY_TEST_USER_API_TOKEN'
_API_URL_ENV_VAR = 'APIFY_INTEGRATION_TESTS_API_URL'
_SDK_ROOT_PATH = Path(__file__).parent.parent.parent.resolve()


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
        delattr(apify._actor.Actor, '__wrapped__')

        # Set the environment variable for the local storage directory to the temporary path.
        monkeypatch.setenv(ApifyEnvVars.LOCAL_STORAGE_DIR, str(tmp_path))

        # Reset the flags in the service locator to indicate that no services are explicitly set. This ensures
        # a clean state, as services might have been set during a previous test and not reset properly.
        service_locator._configuration_was_retrieved = False
        service_locator._storage_client_was_retrieved = False
        service_locator._event_manager_was_retrieved = False

        # Reset the services in the service locator.
        service_locator._configuration = None
        service_locator._event_manager = None
        service_locator._storage_client = None

        # Clear creation-related caches to ensure no state is carried over between tests.
        monkeypatch.setattr(_creation_management, '_cache_dataset_by_id', {})
        monkeypatch.setattr(_creation_management, '_cache_dataset_by_name', {})
        monkeypatch.setattr(_creation_management, '_cache_kvs_by_id', {})
        monkeypatch.setattr(_creation_management, '_cache_kvs_by_name', {})
        monkeypatch.setattr(_creation_management, '_cache_rq_by_id', {})
        monkeypatch.setattr(_creation_management, '_cache_rq_by_name', {})

        # Verify that the test environment was set up correctly.
        assert os.environ.get(ApifyEnvVars.LOCAL_STORAGE_DIR) == str(tmp_path)
        assert service_locator._configuration_was_retrieved is False
        assert service_locator._storage_client_was_retrieved is False
        assert service_locator._event_manager_was_retrieved is False

    return _prepare_test_env


@pytest.fixture(autouse=True)
def _isolate_test_environment(prepare_test_env: Callable[[], None]) -> None:
    """Isolate the testing environment by resetting global state before and after each test.

    This fixture ensures that each test starts with a clean slate and that any modifications during the test
    do not affect subsequent tests. It runs automatically for all tests.

    Args:
        prepare_test_env: Fixture to prepare the environment before each test.
    """

    prepare_test_env()


@pytest.fixture(scope='session')
def apify_token() -> str:
    api_token = os.getenv(_TOKEN_ENV_VAR)

    if not api_token:
        raise RuntimeError(f'{_TOKEN_ENV_VAR} environment variable is missing, cannot run tests!')

    return api_token


@pytest.fixture
def apify_client_async(apify_token: str) -> ApifyClientAsync:
    """Create an instance of the ApifyClientAsync.

    This fixture can't be session-scoped, because then you start getting `RuntimeError: Event loop is closed` errors,
    because `httpx.AsyncClient` in `ApifyClientAsync` tries to reuse the same event loop across requests,
    but `pytest-asyncio` closes the event loop after each test, and uses a new one for the next test.
    """
    api_url = os.getenv(_API_URL_ENV_VAR)

    return ApifyClientAsync(apify_token, api_url=api_url)


@pytest.fixture(scope='session')
def sdk_wheel_path(tmp_path_factory: pytest.TempPathFactory, testrun_uid: str) -> Path:
    """Build the package wheel if it hasn't been built yet, and return the path to the wheel."""
    # Make sure the wheel is not being built concurrently across all the pytest-xdist runners,
    # through locking the building process with a temp file.
    with FileLock(tmp_path_factory.getbasetemp().parent / 'sdk_wheel_build.lock'):
        # Make sure the wheel is built exactly once across across all the pytest-xdist runners,
        # through an indicator file saying that the wheel was already built.
        was_wheel_built_this_test_run_file = tmp_path_factory.getbasetemp() / f'wheel_was_built_in_run_{testrun_uid}'
        if not was_wheel_built_this_test_run_file.exists():
            subprocess.run(
                args='python -m build',
                cwd=_SDK_ROOT_PATH,
                shell=True,
                check=True,
                capture_output=True,
            )
            was_wheel_built_this_test_run_file.touch()

        # Read the current package version, necessary for getting the right wheel filename.
        pyproject_toml_file = (_SDK_ROOT_PATH / 'pyproject.toml').read_text(encoding='utf-8')
        for line in pyproject_toml_file.splitlines():
            if line.startswith('version = '):
                delim = '"' if '"' in line else "'"
                sdk_version = line.split(delim)[1]
                break
        else:
            raise RuntimeError('Unable to find version string.')

        wheel_path = _SDK_ROOT_PATH / 'dist' / f'apify-{sdk_version}-py3-none-any.whl'

        # Just to be sure.
        assert wheel_path.exists()

        return wheel_path


@pytest.fixture(scope='session')
def actor_base_source_files(sdk_wheel_path: Path) -> dict[str, str | bytes]:
    """Create a dictionary of the base source files for a testing Actor.

    It takes the files from `tests/integration/actor_source_base`, builds the Apify SDK wheel from
    the current codebase, and adds them all together in a dictionary.
    """
    source_files: dict[str, str | bytes] = {}

    # First read the actor_source_base files
    sdk_root_path = Path(__file__).parent.parent.parent.resolve()
    actor_source_base_path = sdk_root_path / 'tests/integration/actor_source_base'

    for path in actor_source_base_path.glob('**/*'):
        if not path.is_file():
            continue
        relative_path = str(path.relative_to(actor_source_base_path))
        try:
            source_files[relative_path] = path.read_text(encoding='utf-8')
        except ValueError:
            source_files[relative_path] = path.read_bytes()

    sdk_wheel_file_name = sdk_wheel_path.name
    source_files[sdk_wheel_file_name] = sdk_wheel_path.read_bytes()

    source_files['requirements.txt'] = str(source_files['requirements.txt']).replace(
        'APIFY_SDK_WHEEL_PLACEHOLDER', f'./{sdk_wheel_file_name}'
    )

    current_major_minor_python_version = '.'.join([str(x) for x in sys.version_info[:2]])
    integration_tests_python_version = (
        os.getenv('INTEGRATION_TESTS_PYTHON_VERSION') or current_major_minor_python_version
    )
    source_files['Dockerfile'] = str(source_files['Dockerfile']).replace(
        'BASE_IMAGE_VERSION_PLACEHOLDER', integration_tests_python_version
    )

    return source_files


class MakeActorFunction(Protocol):
    """A type for the `make_actor` fixture."""

    def __call__(
        self,
        label: str,
        *,
        main_func: Callable | None = None,
        main_py: str | None = None,
        source_files: Mapping[str, str | bytes] | None = None,
        additional_requirements: list[str] | None = None,
    ) -> Awaitable[ActorClientAsync]:
        """Create a temporary Actor from the given main function or source files.

        The Actor will be uploaded to the Apify Platform, built there, and after the test finishes, it will
        be automatically deleted.

        You have to pass exactly one of the `main_func`, `main_py` and `source_files` arguments.

        Args:
            label: The label which will be a part of the generated Actor name.
            main_func: The main function of the Actor.
            main_py: The `src/main.py` file of the Actor.
            source_files: A dictionary of the source files of the Actor.
            additional_requirements: A list of additional requirements to be added to the `requirements.txt`.

        Returns:
            A resource client for the created Actor.
        """


@pytest.fixture(scope='session')
def make_actor(
    actor_base_source_files: dict[str, str | bytes],
    apify_token: str,
) -> Iterator[MakeActorFunction]:
    """Fixture for creating temporary Actors for testing purposes.

    This returns a function that creates a temporary Actor from the given main function or source files. The Actor
    will be uploaded to the Apify Platform, built there, and after the test finishes, it will be automatically deleted.
    """
    actors_for_cleanup: list[str] = []

    async def _make_actor(
        label: str,
        *,
        main_func: Callable | None = None,
        main_py: str | None = None,
        source_files: Mapping[str, str | bytes] | None = None,
        additional_requirements: list[str] | None = None,
    ) -> ActorClientAsync:
        if not (main_func or main_py or source_files):
            raise TypeError('One of `main_func`, `main_py` or `source_files` arguments must be specified')

        if (main_func and main_py) or (main_func and source_files) or (main_py and source_files):
            raise TypeError('Cannot specify more than one of `main_func`, `main_py` and `source_files` arguments')

        client = ApifyClientAsync(token=apify_token, api_url=os.getenv(_API_URL_ENV_VAR))
        actor_name = generate_unique_resource_name(label)

        # Get the source of main_func and convert it into a reasonable main_py file.
        if main_func:
            func_source = textwrap.dedent(inspect.getsource(main_func))
            func_source = func_source.replace(f'def {main_func.__name__}(', 'def main(')
            main_py = '\n'.join(  # noqa: FLY002
                [
                    'import asyncio',
                    '',
                    'from apify import Actor',
                    '',
                    '',
                    '',
                    func_source,
                ]
            )

        if main_py:
            source_files = {'src/main.py': main_py}

        assert source_files is not None

        # Copy the source files dict from the fixture so that we're not overwriting it, and merge the passed
        # argument in it.
        actor_source_files = actor_base_source_files.copy()
        actor_source_files.update(source_files)

        if additional_requirements:
            # Get the current requirements.txt content (as a string).
            req_content = actor_source_files.get('requirements.txt', '')
            if isinstance(req_content, bytes):
                req_content = req_content.decode('utf-8')
            # Append the additional requirements, each on a new line.
            additional_reqs = '\n'.join(additional_requirements)
            req_content = req_content.strip() + '\n' + additional_reqs + '\n'
            actor_source_files['requirements.txt'] = req_content

        # Reformat the source files in a format that the Apify API understands.
        source_files_for_api = []
        for file_name, file_contents in actor_source_files.items():
            if isinstance(file_contents, str):
                file_format = 'TEXT'
                if file_name.endswith('.py'):
                    file_contents = textwrap.dedent(file_contents).lstrip()  # noqa: PLW2901
            else:
                file_format = 'BASE64'
                file_contents = base64.b64encode(file_contents).decode('utf-8')  # noqa: PLW2901

            source_files_for_api.append(
                {
                    'name': file_name,
                    'format': file_format,
                    'content': file_contents,
                }
            )

        print(f'Creating Actor {actor_name}...')
        created_actor = await client.actors().create(
            name=actor_name,
            default_run_build='latest',
            default_run_memory_mbytes=256,
            default_run_timeout_secs=600,
            versions=[
                {
                    'versionNumber': '0.0',
                    'buildTag': 'latest',
                    'sourceType': ActorSourceType.SOURCE_FILES,
                    'sourceFiles': source_files_for_api,
                }
            ],
        )

        actor_client = client.actor(created_actor['id'])

        print(f'Building Actor {actor_name}...')
        build_result = await actor_client.build(version_number='0.0')
        build_client = client.build(build_result['id'])
        build_client_result = await build_client.wait_for_finish(wait_secs=600)

        assert build_client_result is not None
        assert build_client_result['status'] == ActorJobStatus.SUCCEEDED

        # We only mark the client for cleanup if the build succeeded, so that if something goes wrong here,
        # you have a chance to check the error.
        actors_for_cleanup.append(created_actor['id'])

        return actor_client

    yield _make_actor

    client = ApifyClient(token=apify_token, api_url=os.getenv(_API_URL_ENV_VAR))

    # Delete all the generated Actors.
    for actor_id in actors_for_cleanup:
        actor_client = client.actor(actor_id)

        if (actor := actor_client.get()) is not None:
            actor_client.update(
                pricing_infos=[
                    *actor.get('pricingInfos', []),
                    {
                        'pricingModel': 'FREE',
                    },
                ]
            )

        actor_client.delete()


class RunActorFunction(Protocol):
    """A type for the `run_actor` fixture."""

    def __call__(
        self,
        actor: ActorClientAsync,
        *,
        run_input: Any = None,
        max_total_charge_usd: Decimal | None = None,
    ) -> Coroutine[None, None, ActorRun]:
        """Initiate an Actor run and wait for its completion.

        Args:
            actor: Actor async client, in testing context usually created by `make_actor` fixture.
            run_input: Optional input for the Actor run.

        Returns:
            Actor run result.
        """


@pytest.fixture(scope='session')
def run_actor(apify_token: str) -> RunActorFunction:
    """Fixture for calling an Actor run and waiting for its completion.

    This fixture returns a function that initiates an Actor run with optional run input, waits for its completion,
    and retrieves the final result. It uses the `wait_for_finish` method with a timeout of 10 minutes.
    """

    async def _run_actor(
        actor: ActorClientAsync,
        *,
        run_input: Any = None,
        max_total_charge_usd: Decimal | None = None,
    ) -> ActorRun:
        call_result = await actor.call(
            run_input=run_input,
            max_total_charge_usd=max_total_charge_usd,
        )

        assert isinstance(call_result, dict), 'The result of ActorClientAsync.call() is not a dictionary.'
        assert 'id' in call_result, 'The result of ActorClientAsync.call() does not contain an ID.'

        client = ApifyClientAsync(token=apify_token, api_url=os.getenv(_API_URL_ENV_VAR))
        run_client = client.run(call_result['id'])
        run_result = await run_client.wait_for_finish(wait_secs=600)

        return ActorRun.model_validate(run_result)

    return _run_actor
