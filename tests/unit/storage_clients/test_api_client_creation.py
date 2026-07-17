from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import brotli
import pytest

from apify import Actor
from apify._configuration import Configuration
from apify.storage_clients._apify._api_client_creation import _create_api_client, create_storage_api_client

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_httpserver import HTTPServer
    from werkzeug import Request, Response

    from apify_client import ApifyClientAsync


def test_create_api_client_without_token() -> None:
    """Test that _create_api_client raises ValueError when no token is set."""
    config = Configuration(token=None)
    with pytest.raises(ValueError, match='requires a valid token'):
        _create_api_client(config)


def test_create_api_client_without_api_url() -> None:
    """Test that _create_api_client raises ValueError when API URL is empty."""
    config = Configuration(token='test-token')
    # Force the api_base_url to be empty
    object.__setattr__(config, 'api_base_url', '')
    with pytest.raises(ValueError, match='requires a valid API URL'):
        _create_api_client(config)


def test_create_api_client_without_public_api_url() -> None:
    """Test that _create_api_client raises ValueError when public API URL is empty."""
    config = Configuration(token='test-token')
    object.__setattr__(config, 'api_public_base_url', '')
    with pytest.raises(ValueError, match='requires a valid API public base URL'):
        _create_api_client(config)


async def test_create_storage_multiple_identifiers() -> None:
    """Test that create_storage_api_client raises ValueError for multiple identifiers."""
    config = Configuration(token='test-token')
    with pytest.raises(ValueError, match='Only one of'):
        await create_storage_api_client(
            storage_type='Dataset',
            configuration=config,
            id='some-id',
            name='some-name',
        )


async def test_create_storage_unknown_type() -> None:
    """Test that create_storage_api_client raises ValueError for unknown storage type."""
    config = Configuration(token='test-token')
    with pytest.raises(ValueError, match='Unknown storage type'):
        await create_storage_api_client(  # ty: ignore[no-matching-overload]
            storage_type='UnknownType',
            configuration=config,
        )


def _client_from_configuration(api_url: str) -> ApifyClientAsync:
    """Build an API client the way storage clients do, via `_create_api_client`."""
    config = Configuration(token='test-token', api_base_url=api_url, api_public_base_url=api_url)
    return _create_api_client(config)


def _client_from_new_client(api_url: str) -> ApifyClientAsync:
    """Build an API client the way user code does, via `Actor.new_client`."""
    return Actor.new_client(token='test-token', api_url=api_url)


@pytest.mark.parametrize(
    'client_factory',
    [
        pytest.param(_client_from_configuration, id='storage_api_client'),
        pytest.param(_client_from_new_client, id='actor_new_client'),
    ],
)
async def test_sdk_client_compresses_request_body_with_brotli(
    httpserver: HTTPServer,
    client_factory: Callable[[str], ApifyClientAsync],
) -> None:
    """API clients created by the SDK compress request bodies with brotli (Content-Encoding: br)."""
    api_url = str(httpserver.url_for('/')).removesuffix('/')
    client = client_factory(api_url)

    captured: dict[str, Any] = {}

    def request_handler(request: Request, response: Response) -> Response:
        captured['content_encoding'] = request.headers.get('Content-Encoding')
        captured['body'] = request.get_data()
        return response

    httpserver.expect_request('/v2/datasets/test-dataset/items', method='POST').with_post_hook(
        request_handler
    ).respond_with_json({'data': {}}, status=201)

    items = [{'hello': 'world'}, {'answer': 42}]
    await client.dataset(dataset_id='test-dataset').push_items(items)

    assert captured['content_encoding'] == 'br'
    # The body must be genuinely brotli-compressed and round-trip back to the original items.
    assert json.loads(brotli.decompress(captured['body'])) == items
