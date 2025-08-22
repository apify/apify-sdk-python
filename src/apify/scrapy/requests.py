from __future__ import annotations

import codecs
import pickle
from logging import getLogger
from typing import Any, cast

from scrapy import Request as ScrapyRequest
from scrapy import Spider
from scrapy.http.headers import Headers
from scrapy.utils.request import request_from_dict

from crawlee._types import HttpHeaders

from apify import Request as ApifyRequest

logger = getLogger(__name__)


def to_apify_request(scrapy_request: ScrapyRequest, spider: Spider) -> ApifyRequest | None:
    """Convert a Scrapy request to an Apify request.

    Args:
        scrapy_request: The Scrapy request to be converted.
        spider: The Scrapy spider that the request is associated with.

    Returns:
        The converted Apify request if the conversion was successful, otherwise None.
    """
    if not isinstance(scrapy_request, ScrapyRequest):
        logger.warning('Failed to convert to Apify request: Scrapy request must be a ScrapyRequest instance.')  # type: ignore[unreachable]
        return None

    logger.debug(f'to_apify_request was called (scrapy_request={scrapy_request})...')

    # Configuration to behave as similarly as possible to Scrapy's default RFPDupeFilter.
    request_kwargs: dict[str, Any] = {
        'url': scrapy_request.url,
        'method': scrapy_request.method,
        'payload': scrapy_request.body,
        'use_extended_unique_key': True,
        'keep_url_fragment': False,
    }

    try:
        if scrapy_request.dont_filter:
            request_kwargs['always_enqueue'] = True
        else:
            if scrapy_request.meta.get('apify_request_unique_key'):
                request_kwargs['unique_key'] = scrapy_request.meta['apify_request_unique_key']

            if scrapy_request.meta.get('apify_request_id'):
                request_kwargs['id'] = scrapy_request.meta['apify_request_id']

        request_kwargs['user_data'] = scrapy_request.meta.get('userData', {})

        # Convert Scrapy's headers to a HttpHeaders and store them in the apify_request
        if isinstance(scrapy_request.headers, Headers):
            request_kwargs['headers'] = HttpHeaders(dict(scrapy_request.headers.to_unicode_dict()))
        else:
            logger.warning(  # type: ignore[unreachable]
                f'Invalid scrapy_request.headers type, not scrapy.http.headers.Headers: {scrapy_request.headers}'
            )

        apify_request = ApifyRequest.from_url(**request_kwargs)

        # Serialize the Scrapy ScrapyRequest and store it in the apify_request.
        #   - This process involves converting the Scrapy ScrapyRequest object into a dictionary, encoding it to base64,
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


def to_scrapy_request(apify_request: ApifyRequest, spider: Spider) -> ScrapyRequest:
    """Convert an Apify request to a Scrapy request.

    Args:
        apify_request: The Apify request to be converted.
        spider: The Scrapy spider that the request is associated with.

    Raises:
        TypeError: If the Apify request is not an instance of the `ApifyRequest` class.
        ValueError: If the Apify request does not contain the required keys.

    Returns:
        The converted Scrapy request.
    """
    if not isinstance(cast('Any', apify_request), ApifyRequest):
        raise TypeError('apify_request must be a crawlee.ScrapyRequest instance')

    logger.debug(f'to_scrapy_request was called (apify_request={apify_request})...')

    # If the apify_request comes from the Scrapy
    if 'scrapy_request' in apify_request.user_data:
        # Deserialize the Scrapy ScrapyRequest from the apify_request.
        #   - This process involves decoding the base64-encoded request data and reconstructing
        #     the Scrapy ScrapyRequest object from its dictionary representation.
        logger.debug('Restoring the Scrapy ScrapyRequest from the apify_request...')

        scrapy_request_dict_encoded = apify_request.user_data['scrapy_request']
        if not isinstance(scrapy_request_dict_encoded, str):
            raise TypeError('scrapy_request_dict_encoded must be a string')

        scrapy_request_dict = pickle.loads(codecs.decode(scrapy_request_dict_encoded.encode(), 'base64'))
        if not isinstance(scrapy_request_dict, dict):
            raise TypeError('scrapy_request_dict must be a dictionary')

        scrapy_request = request_from_dict(scrapy_request_dict, spider=spider)
        if not isinstance(scrapy_request, ScrapyRequest):
            raise TypeError('scrapy_request must be an instance of the ScrapyRequest class')

        logger.debug(f'Scrapy ScrapyRequest successfully reconstructed (scrapy_request={scrapy_request})...')

        # Update the meta field with the meta field from the apify_request
        meta = scrapy_request.meta or {}
        meta.update({'apify_request_unique_key': apify_request.unique_key})
        # scrapy_request.meta is a property, so we have to set it like this
        scrapy_request._meta = meta  # noqa: SLF001

    # If the apify_request comes directly from the Scrapy, typically start URLs.
    else:
        logger.debug('Gonna create a new Scrapy ScrapyRequest (cannot be restored)')

        scrapy_request = ScrapyRequest(
            url=apify_request.url,
            method=apify_request.method,
            meta={
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
