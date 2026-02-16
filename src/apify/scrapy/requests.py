from __future__ import annotations

import base64
import json
import pickle
from enum import Enum
from logging import getLogger
from typing import Any, cast

from pydantic import BaseModel
from scrapy import Request as ScrapyRequest
from scrapy import Spider
from scrapy.http.headers import Headers
from scrapy.utils.request import request_from_dict

from crawlee._types import HttpHeaders

from apify import Request as ApifyRequest

logger = getLogger(__name__)


def _prepare_for_json(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable values to JSON-safe representations.

    Bytes values are converted to dicts with a `__bytes_b64__` key. Bytes dict keys
    are decoded to UTF-8 strings. Pydantic models are converted via `model_dump(mode='json')`.
    Enum values are converted to their underlying value.
    """
    if isinstance(obj, bytes):
        return {'__bytes_b64__': base64.b64encode(obj).decode('ascii')}
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode='json')
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {(k.decode('utf-8') if isinstance(k, bytes) else k): _prepare_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_prepare_for_json(item) for item in obj]
    return obj


def _restore_from_json(obj: Any) -> Any:
    """Recursively restore bytes values from their base64-encoded JSON representations."""
    if isinstance(obj, dict):
        if '__bytes_b64__' in obj and len(obj) == 1:
            return base64.b64decode(obj['__bytes_b64__'])
        return {k: _restore_from_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_restore_from_json(item) for item in obj]
    return obj


def to_apify_request(scrapy_request: ScrapyRequest, spider: Spider) -> ApifyRequest | None:
    """Convert a Scrapy request to an Apify request.

    Args:
        scrapy_request: The Scrapy request to be converted.
        spider: The Scrapy spider that the request is associated with.

    Returns:
        The converted Apify request if the conversion was successful, otherwise None.
    """
    if not isinstance(scrapy_request, ScrapyRequest):
        logger.warning('Failed to convert to Apify request: Scrapy request must be a ScrapyRequest instance.')
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
            logger.warning(
                f'Invalid scrapy_request.headers type, not scrapy.http.headers.Headers: {scrapy_request.headers}'
            )

        apify_request = ApifyRequest.from_url(**request_kwargs)

        # Serialize the Scrapy ScrapyRequest and store it in the apify_request.
        #   - This process involves converting the Scrapy ScrapyRequest object into a dictionary,
        #     JSON-encoding it (with bytes fields base64-encoded), then base64-encoding the result,
        #     and storing it as 'scrapy_request' within the 'userData' dictionary of the apify_request.
        scrapy_request_dict = scrapy_request.to_dict(spider=spider)
        json_safe_dict = _prepare_for_json(scrapy_request_dict)
        scrapy_request_json = json.dumps(json_safe_dict)
        scrapy_request_dict_encoded = base64.b64encode(scrapy_request_json.encode('utf-8')).decode('ascii')
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

        raw_bytes = base64.b64decode(scrapy_request_dict_encoded)
        try:
            scrapy_request_dict = _restore_from_json(json.loads(raw_bytes.decode('utf-8')))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning('Scrapy request uses legacy pickle format. Re-storing will convert it to JSON.')
            scrapy_request_dict = pickle.loads(raw_bytes)

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
