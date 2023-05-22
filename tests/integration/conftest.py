import base64
import inspect
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, Dict, List, Mapping, Optional, Protocol, Union

import pytest
from filelock import FileLock

from apify import Actor
from apify.config import Configuration
from apify.storages import Dataset, KeyValueStore, RequestQueue, StorageClientManager
from apify_client import ApifyClientAsync
from apify_client.clients.resource_clients import ActorClientAsync
from apify_client.consts import ActorJobStatus, ActorSourceType

from ._utils import generate_unique_resource_name

TOKEN_ENV_VAR = 'APIFY_TEST_USER_API_TOKEN'
API_URL_ENV_VAR = 'APIFY_INTEGRATION_TESTS_API_URL'
SDK_ROOT_PATH = Path(__file__).parent.parent.parent.resolve()


# To isolate the tests, we need to reset the used singletons before each test case
# We also patch the default storage client with a tmp_path
@pytest.fixture(autouse=True)
def _reset_and_patch_default_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Actor, '_default_instance', None)
    monkeypatch.setattr(Configuration, '_default_instance', None)
    monkeypatch.setattr(Dataset, '_cache_by_id', None)
    monkeypatch.setattr(Dataset, '_cache_by_name', None)
    monkeypatch.setattr(KeyValueStore, '_cache_by_id', None)
    monkeypatch.setattr(KeyValueStore, '_cache_by_name', None)
    monkeypatch.setattr(RequestQueue, '_cache_by_id', None)
    monkeypatch.setattr(RequestQueue, '_cache_by_name', None)
    monkeypatch.setattr(StorageClientManager, '_default_instance', None)


# This fixture can't be session-scoped,
# because then you start getting `RuntimeError: Event loop is closed` errors,
# because `httpx.AsyncClient` in `ApifyClientAsync` tries to reuse the same event loop across requests,
# but `pytest-asyncio` closes the event loop after each test,
# and uses a new one for the next test.
@pytest.fixture
def apify_client_async() -> ApifyClientAsync:
    api_token = os.getenv(TOKEN_ENV_VAR)
    api_url = os.getenv(API_URL_ENV_VAR)

    if not api_token:
        raise RuntimeError(f'{TOKEN_ENV_VAR} environment variable is missing, cannot run tests!')

    return ApifyClientAsync(api_token, api_url=api_url)


# Build the package wheel if it hasn't been built yet, and return the path to the wheel
@pytest.fixture(scope='session')
def sdk_wheel_path(tmp_path_factory: pytest.TempPathFactory, testrun_uid: str) -> Path:
    # Make sure the wheel is not being built concurrently across all the pytest-xdist runners,
    # through locking the building process with a temp file
    with FileLock(tmp_path_factory.getbasetemp().parent / 'sdk_wheel_build.lock'):
        # Make sure the wheel is built exactly once across across all the pytest-xdist runners,
        # through an indicator file saying that the wheel was already built
        was_wheel_built_this_test_run_file = tmp_path_factory.getbasetemp() / f'wheel_was_built_in_run_{testrun_uid}'
        if not was_wheel_built_this_test_run_file.exists():
            subprocess.run('python -m build', cwd=SDK_ROOT_PATH, shell=True, check=True, capture_output=True)
            was_wheel_built_this_test_run_file.touch()

        # Read the current package version, necessary for getting the right wheel filename
        pyproject_toml_file = (SDK_ROOT_PATH / 'pyproject.toml').read_text(encoding='utf-8')
        for line in pyproject_toml_file:
            if line.startswith('version = '):
                delim = '"' if '"' in line else "'"
                sdk_version = line.split(delim)[1]
                break
        else:
            raise RuntimeError('Unable to find version string.')

        wheel_path = SDK_ROOT_PATH / 'dist' / f'apify-{sdk_version}-py3-none-any.whl'

        # Just to be sure
        assert wheel_path.exists()

        return wheel_path


@pytest.fixture(scope='session')
def actor_base_source_files(sdk_wheel_path: Path) -> Dict[str, Union[str, bytes]]:
    """Create a dictionary of the base source files for a testing actor.

    It takes the files from `tests/integration/actor_source_base`,
    builds the Apify SDK wheel from the current codebase,
    and adds them all together in a dictionary.
    """
    source_files: Dict[str, Union[str, bytes]] = {}

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

    source_files['requirements.txt'] = str(source_files['requirements.txt']).replace('APIFY_SDK_WHEEL_PLACEHOLDER', f'./{sdk_wheel_file_name}')

    current_major_minor_python_version = '.'.join([str(x) for x in sys.version_info[:2]])
    integration_tests_python_version = os.getenv('INTEGRATION_TESTS_PYTHON_VERSION') or current_major_minor_python_version
    source_files['Dockerfile'] = str(source_files['Dockerfile']).replace('BASE_IMAGE_VERSION_PLACEHOLDER', integration_tests_python_version)

    return source_files


# Just a type for the make_actor result, so that we can import it in tests
class ActorFactory(Protocol):
    def __call__(
        self,
        actor_label: str,
        *,
        main_func: Optional[Callable] = None,
        main_py: Optional[str] = None,
        source_files: Optional[Mapping[str, Union[str, bytes]]] = None,
    ) -> Awaitable[ActorClientAsync]:
        ...


@pytest.fixture
async def make_actor(actor_base_source_files: Dict[str, Union[str, bytes]], apify_client_async: ApifyClientAsync) -> AsyncIterator[ActorFactory]:
    """A fixture for returning a temporary actor factory."""
    actor_clients_for_cleanup: List[ActorClientAsync] = []

    async def _make_actor(
        actor_label: str,
        *,
        main_func: Optional[Callable] = None,
        main_py: Optional[str] = None,
        source_files: Optional[Mapping[str, Union[str, bytes]]] = None,
    ) -> ActorClientAsync:
        """Create a temporary actor from the given main function or source file(s).

        The actor will be uploaded to the Apify Platform, built there, and after the test finishes, it will be automatically deleted.

        You have to pass exactly one of the `main_func`, `main_py` and `source_files` arguments.

        Args:
            actor_label (str): The label which will be a part of the generated actor name
            main_func (Callable, optional): The main function of the actor.
            main_py (str, optional): The `src/main.py` file of the actor.
            source_files (dict, optional): A dictionary of the source files of the actor.

        Returns:
            ActorClientAsync: A resource client for the created actor.
        """
        if not (main_func or main_py or source_files):
            raise TypeError('One of `main_func`, `main_py` or `source_files` arguments must be specified')

        if (main_func and main_py) or (main_func and source_files) or (main_py and source_files):
            raise TypeError('Cannot specify more than one of `main_func`, `main_py` and `source_files` arguments')

        actor_name = generate_unique_resource_name(actor_label)

        # Get the source of main_func and convert it into a reasonable main_py file.
        if main_func:
            func_source = textwrap.dedent(inspect.getsource(main_func))
            func_source = func_source.replace(f'def {main_func.__name__}(', 'def main(')
            main_py = f'import asyncio\n\nfrom apify import Actor\n\n\n{func_source}'

        if main_py:
            source_files = {'src/main.py': main_py}

        assert source_files is not None

        # Copy the source files dict from the fixture so that we're not overwriting it, and merge the passed argument in it
        actor_source_files = actor_base_source_files.copy()
        actor_source_files.update(source_files)

        # Reformat the source files in a format that the Apify API understands
        source_files_for_api = []
        for file_name, file_contents in actor_source_files.items():
            if isinstance(file_contents, str):
                file_format = 'TEXT'
                if file_name.endswith('.py'):
                    file_contents = textwrap.dedent(file_contents).lstrip()
            else:
                file_format = 'BASE64'
                file_contents = base64.b64encode(file_contents).decode('utf-8')

            source_files_for_api.append({
                'name': file_name,
                'format': file_format,
                'content': file_contents,
            })

        print(f'Creating actor {actor_name}...')
        created_actor = await apify_client_async.actors().create(
            name=actor_name,
            default_run_build='latest',
            default_run_memory_mbytes=256,
            default_run_timeout_secs=300,
            versions=[{
                'versionNumber': '0.0',
                'buildTag': 'latest',
                'sourceType': ActorSourceType.SOURCE_FILES,
                'sourceFiles': source_files_for_api,
            }],
        )

        actor_client = apify_client_async.actor(created_actor['id'])

        print(f'Building actor {actor_name}...')
        build = await actor_client.build(version_number='0.0', wait_for_finish=300)

        assert build['status'] == ActorJobStatus.SUCCEEDED

        # We only mark the client for cleanup if the build succeeded,
        # so that if something goes wrong here,
        # you have a chance to check the error
        actor_clients_for_cleanup.append(actor_client)

        return actor_client

    yield _make_actor

    # Delete all the generated actors
    for actor_client in actor_clients_for_cleanup:
        await actor_client.delete()
