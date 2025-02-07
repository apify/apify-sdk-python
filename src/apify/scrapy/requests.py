from __future__ import annotations

import codecs
import pickle
from logging import getLogger
from typing import Any, cast

from scrapy import Request, Spider
from scrapy.http.headers import Headers
from scrapy.utils.request import request_from_dict

from crawlee import Request as CrawleeRequest
from crawlee._types import HttpHeaders
from crawlee._utils.crypto import crypto_random_object_id
from crawlee._utils.requests import compute_unique_key, unique_key_to_request_id

logger = getLogger(__name__)


def _is_request_produced_by_middleware(scrapy_request: Request) -> bool:
    """Returns True if the Scrapy request was produced by a downloader middleware, otherwise False.

    Works for RetryMiddleware and RedirectMiddleware.
    """
    return bool(scrapy_request.meta.get('redirect_times')) or bool(scrapy_request.meta.get('retry_times'))


def to_apify_request(scrapy_request: Request, spider: Spider) -> CrawleeRequest | None:
    """Convert a Scrapy request to an Apify request.

    Args:
        scrapy_request: The Scrapy request to be converted.
        spider: The Scrapy spider that the request is associated with.

    Returns:
        The converted Apify request if the conversion was successful, otherwise None.
    """
    if not isinstance(scrapy_request, Request):
        logger.warning('Failed to convert to Apify request: Scrapy request must be a Request instance.')  # type: ignore[unreachable]
        return None

    logger.debug(f'to_apify_request was called (scrapy_request={scrapy_request})...')

    try:
        if _is_request_produced_by_middleware(scrapy_request):
            unique_key = compute_unique_key(
                url=scrapy_request.url,
                method=scrapy_request.method,  # type: ignore[arg-type]  # str vs literal
                payload=scrapy_request.body,
                use_extended_unique_key=True,
            )
        elif scrapy_request.dont_filter:
            unique_key = crypto_random_object_id(8)
        elif scrapy_request.meta.get('apify_request_unique_key'):
            unique_key = scrapy_request.meta['apify_request_unique_key']
        else:
            unique_key = crypto_random_object_id(8)

        if scrapy_request.meta.get('apify_request_id'):
            request_id = scrapy_request.meta['apify_request_id']
        else:
            request_id = unique_key_to_request_id(unique_key)

        apify_request = CrawleeRequest(
            url=scrapy_request.url,
            method=scrapy_request.method,
            payload=scrapy_request.body,
            user_data=scrapy_request.meta.get('userData', {}),
            unique_key=unique_key,
            id=request_id,
        )

        # Convert Scrapy's headers to a HttpHeaders and store them in the apify_request
        if isinstance(scrapy_request.headers, Headers):
            apify_request.headers = HttpHeaders(dict(scrapy_request.headers.to_unicode_dict()))
        else:
            logger.warning(  # type: ignore[unreachable]
                f'Invalid scrapy_request.headers type, not scrapy.http.headers.Headers: {scrapy_request.headers}'
            )

        # Serialize the Scrapy Request and store it in the apify_request.
        #   - This process involves converting the Scrapy Request object into a dictionary, encoding it to base64,
        #     and storing it as 'scrapy_request' within the 'userData' dictionary of the apify_request.
        #   - The serialization process can be referenced at: https://stackoverflow.com/questions/30469575/.
        scrapy_request_dict = scrapy_request.to_dict(spider=spider)
        scrapy_request_dict_encoded = codecs.encode(pickle.dumps(scrapy_request_dict), 'base64').decode()
        apify_request.user_data['scrapy_request'] = scrapy_request_dict_encoded

    except Exception as exc:
        logger.warning(f'Conversion of Scrapy request {scrapy_request} to Apify request failed; {exc}')
        return None

    logger.debug(f'scrapy_request was converted to the apify_request={apify_request}')
    return apify_request


def to_scrapy_request(apify_request: CrawleeRequest, spider: Spider) -> Request:
    """Convert an Apify request to a Scrapy request.

    Args:
        apify_request: The Apify request to be converted.
        spider: The Scrapy spider that the request is associated with.

    Raises:
        TypeError: If the apify_request is not a crawlee request.
        ValueError: If the apify_request does not contain the required keys.

    Returns:
        The converted Scrapy request.
    """
    if not isinstance(cast(Any, apify_request), CrawleeRequest):
        raise TypeError('apify_request must be a crawlee.Request instance')

    logger.debug(f'to_scrapy_request was called (apify_request={apify_request})...')

    # If the apify_request comes from the Scrapy
    if 'scrapy_request' in apify_request.user_data:
        # Deserialize the Scrapy Request from the apify_request.
        #   - This process involves decoding the base64-encoded request data and reconstructing
        #     the Scrapy Request object from its dictionary representation.
        logger.debug('Restoring the Scrapy Request from the apify_request...')

        scrapy_request_dict_encoded = apify_request.user_data['scrapy_request']
        if not isinstance(scrapy_request_dict_encoded, str):
            raise TypeError('scrapy_request_dict_encoded must be a string')

        scrapy_request_dict = pickle.loads(codecs.decode(scrapy_request_dict_encoded.encode(), 'base64'))
        if not isinstance(scrapy_request_dict, dict):
            raise TypeError('scrapy_request_dict must be a dictionary')

        scrapy_request = request_from_dict(scrapy_request_dict, spider=spider)
        if not isinstance(scrapy_request, Request):
            raise TypeError('scrapy_request must be an instance of the Request class')

        logger.debug(f'Scrapy Request successfully reconstructed (scrapy_request={scrapy_request})...')

        # Update the meta field with the meta field from the apify_request
        meta = scrapy_request.meta or {}
        meta.update({'apify_request_id': apify_request.id, 'apify_request_unique_key': apify_request.unique_key})
        # scrapy_request.meta is a property, so we have to set it like this
        scrapy_request._meta = meta  # noqa: SLF001

    # If the apify_request comes directly from the Request Queue, typically start URLs
    else:
        logger.debug('Gonna create a new Scrapy Request (cannot be restored)')

        scrapy_request = Request(
            url=apify_request.url,
            method=apify_request.method,
            meta={
                'apify_request_id': apify_request.id,
                'apify_request_unique_key': apify_request.unique_key,
            },
        )

    # Add optional 'headers' field
    if apify_request.headers:
        scrapy_request.headers |= Headers(apify_request.headers)

    # Add optional 'userData' field
    if apify_request.user_data:
        scrapy_request.meta['userData'] = apify_request.user_data

    logger.debug(f'an apify_request was converted to the scrapy_request={scrapy_request}')
    return scrapy_request
