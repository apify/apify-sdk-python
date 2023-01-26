import base64
import inspect
import os
import subprocess
import textwrap
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, Dict, List, Mapping, Optional, Protocol, Union

import pytest

from apify_client import ApifyClientAsync
from apify_client.clients.resource_clients import ActorClientAsync
from apify_client.consts import ActorJobStatus, ActorSourceType

from ._utils import generate_unique_resource_name

TOKEN_ENV_VAR = 'APIFY_TEST_USER_API_TOKEN'
API_URL_ENV_VAR = 'APIFY_INTEGRATION_TESTS_API_URL'


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


@pytest.fixture(scope='session')
def actor_base_source_files() -> Dict[str, Union[str, bytes]]:
    """Create a dictionary of the base source files for a testing actor.

    It takes the files from `tests/integration/actor_source_base`,
    builds the Apify SDK wheel from the current codebase,
    and adds them all together in a dictionary.
    """
    source_files: Dict[str, Union[str, bytes]] = dict()

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

    # Then build the SDK and the wheel to the source files
    subprocess.run('python setup.py bdist_wheel', cwd=sdk_root_path, shell=True, check=True, capture_output=True)

    version_file = (sdk_root_path / 'src/apify/_version.py').read_text(encoding='utf-8')
    sdk_version = None
    for line in version_file.splitlines():
        if line.startswith('__version__'):
            delim = '"' if '"' in line else "'"
            sdk_version = line.split(delim)[1]
            break
    else:
        raise RuntimeError('Unable to find version string.')

    wheel_file_name = f'apify-{sdk_version}-py3-none-any.whl'
    wheel_path = sdk_root_path / 'dist' / wheel_file_name

    source_files[wheel_file_name] = wheel_path.read_bytes()
    source_files['requirements.txt'] = str(source_files['requirements.txt']).replace('APIFY_SDK_WHEEL_PLACEHOLDER', f'./{wheel_file_name}')

    return source_files


# Just a type for the make_actor result, so that we can import it in tests
class ActorFactory(Protocol):
    def __call__(
        self,
        actor_label: str,  # noqa: U100
        *,
        main_func: Optional[Callable] = None,  # noqa: U100
        main_py: Optional[str] = None,  # noqa: U100
        source_files: Optional[Mapping[str, Union[str, bytes]]] = None,  # noqa: U100
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
