from __future__ import annotations

import asyncio
import codecs
import pickle
from base64 import b64encode
from urllib.parse import unquote

from scrapy.utils.python import to_bytes

try:
    from scrapy import Request, Spider
    from scrapy.utils.request import request_from_dict
except ImportError as exc:
    raise ImportError(
        'To use this module, you need to install the "scrapy" extra. Run "pip install apify[scrapy]".',
    ) from exc

from .._crypto import crypto_random_object_id
from ..actor import Actor
from ..storages import RequestQueue, StorageClientManager

nested_event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()


def get_basic_auth_header(username: str, password: str, auth_encoding: str = 'latin-1') -> bytes:
    """Generate a basic authentication header for the given username and password."""
    string = f'{unquote(username)}:{unquote(password)}'
    user_pass = to_bytes(string, encoding=auth_encoding)
    return b'Basic ' + b64encode(user_pass)


def get_running_event_loop_id() -> int:
    """Get the ID of the currently running event loop.

    It could be useful mainly for debugging purposes.

    Returns:
        The ID of the event loop.
    """
    return id(asyncio.get_running_loop())


def to_apify_request(scrapy_request: Request, spider: Spider) -> dict:
    """Convert a Scrapy request to an Apify request.

    Args:
        scrapy_request: The Scrapy request to be converted.
        spider: The Scrapy spider that the request is associated with.

    Returns:
        The converted Apify request.
    """
    assert isinstance(scrapy_request, Request)  # noqa: S101

    call_id = crypto_random_object_id(8)
    Actor.log.debug(f'[{call_id}]: to_apify_request was called (scrapy_request={scrapy_request})...')

    apify_request = {
        'url': scrapy_request.url,
        'method': scrapy_request.method,
    }

    # Add 'id' to the apify_request
    if scrapy_request.meta.get('apify_request_id'):
        apify_request['id'] = scrapy_request.meta['apify_request_id']

    # Add 'uniqueKey' to the apify_request
    if scrapy_request.meta.get('apify_request_unique_key'):
        apify_request['uniqueKey'] = scrapy_request.meta['apify_request_unique_key']

    # Serialize the Scrapy Request and store it in the apify_request.
    #   - This process involves converting the Scrapy Request object into a dictionary, encoding it to base64,
    #     and storing it as 'scrapy_request' within the 'userData' dictionary of the apify_request.
    #   - The serialization process can be referenced at: https://stackoverflow.com/questions/30469575/.
    scrapy_request_dict = scrapy_request.to_dict(spider=spider)
    scrapy_request_dict_encoded = codecs.encode(pickle.dumps(scrapy_request_dict), 'base64').decode()
    apify_request['userData'] = {'scrapy_request': scrapy_request_dict_encoded}

    Actor.log.debug(f'[{call_id}]: scrapy_request was converted to the apify_request={apify_request}')
    return apify_request


def to_scrapy_request(apify_request: dict, spider: Spider) -> Request:
    """Convert an Apify request to a Scrapy request.

    Args:
        apify_request: The Apify request to be converted.
        spider: The Scrapy spider that the request is associated with.

    Returns:
        The converted Scrapy request.
    """
    assert isinstance(apify_request, dict)  # noqa: S101
    assert 'url' in apify_request  # noqa: S101
    assert 'method' in apify_request  # noqa: S101
    assert 'id' in apify_request  # noqa: S101
    assert 'uniqueKey' in apify_request  # noqa: S101

    call_id = crypto_random_object_id(8)
    Actor.log.debug(f'[{call_id}]: to_scrapy_request was called (apify_request={apify_request})...')

    # If the apify_request comes from the Scrapy
    if 'userData' in apify_request and 'scrapy_request' in apify_request['userData']:
        # Deserialize the Scrapy Request from the apify_request.
        #   - This process involves decoding the base64-encoded request data and reconstructing
        #     the Scrapy Request object from its dictionary representation.
        Actor.log.debug(f'[{call_id}]: Restoring the Scrapy Request from the apify_request...')
        scrapy_request_dict_encoded = apify_request['userData']['scrapy_request']
        assert isinstance(scrapy_request_dict_encoded, str)  # noqa: S101

        scrapy_request_dict = pickle.loads(codecs.decode(scrapy_request_dict_encoded.encode(), 'base64'))
        assert isinstance(scrapy_request_dict, dict)  # noqa: S101

        scrapy_request = request_from_dict(scrapy_request_dict, spider=spider)
        assert isinstance(scrapy_request, Request)  # noqa: S101
        Actor.log.debug(f'[{call_id}]: Scrapy Request successfully reconstructed (scrapy_request={scrapy_request})...')

        # Update the meta field with the meta field from the apify_request
        meta = scrapy_request.meta or {}
        meta.update({'apify_request_id': apify_request['id'], 'apify_request_unique_key': apify_request['uniqueKey']})
        scrapy_request._meta = meta  # scrapy_request.meta is a property, so we have to set it like this

    # If the apify_request comes directly from the Request Queue, typically start URLs
    else:
        Actor.log.debug(f'[{call_id}]: gonna create a new Scrapy Request (cannot be restored)')

        scrapy_request = Request(
            url=apify_request['url'],
            method=apify_request['method'],
            meta={
                'apify_request_id': apify_request['id'],
                'apify_request_unique_key': apify_request['uniqueKey'],
            },
        )

    Actor.log.debug(f'[{call_id}]: an apify_request was converted to the scrapy_request={scrapy_request}')
    return scrapy_request


async def open_queue_with_custom_client() -> RequestQueue:
    """Open a Request Queue with custom Apify Client.

    TODO: add support for custom client to Actor.open_request_queue(), so that
    we don't have to do this hacky workaround
    """
    # Create a new Apify Client with its httpx client in the custom event loop
    custom_loop_apify_client = Actor.new_client()

    # Set the new Apify Client as the default client, back up the old client
    old_client = Actor.apify_client
    StorageClientManager.set_cloud_client(custom_loop_apify_client)

    # Create a new Request Queue in the custom event loop,
    # replace its Apify client with the custom loop's Apify client
    rq = await Actor.open_request_queue()

    if Actor.config.is_at_home:
        rq._request_queue_client = custom_loop_apify_client.request_queue(
            rq._id,
            client_key=rq._client_key,
        )

    # Restore the old Apify Client as the default client
    StorageClientManager.set_cloud_client(old_client)
    return rq
