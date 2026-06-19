from __future__ import annotations

from copy import deepcopy
from logging import getLogger
from typing import Any, cast

from scrapy import Request as ScrapyRequest
from scrapy import Spider
from scrapy.http.headers import Headers
from scrapy.utils.misc import load_object
from scrapy.utils.request import request_from_dict

from crawlee._request import UserData
from crawlee._types import HttpHeaders

from ._serialization import decode_from_json, encode_to_json
from apify import Request as ApifyRequest

logger = getLogger(__name__)


def _ensure_known_request_class(request_dict: dict[str, Any]) -> None:
    """Validate the optional `_class` entry before `request_from_dict` instantiates it.

    `request_from_dict` resolves `_class` with `load_object` and calls it with the request kwargs. The dotted path
    is resolved here first and rejected unless it is a `scrapy.Request` subclass, so a payload can never coerce
    reconstruction into instantiating an arbitrary callable. Resolving may import the class's module (the same
    import `request_from_dict` would do, and far safer than the arbitrary code execution the previous pickle
    format allowed). That import is what lets a custom `Request` subclass be rebuilt in a fresh process after
    an Actor migration, before the spider has lazily imported it.
    """
    class_path = request_dict.get('_class')
    if class_path is None:
        return

    if not isinstance(class_path, str):
        raise TypeError(f'Invalid scrapy_request `_class`, expected a string, got {type(class_path)}')

    try:
        request_cls = load_object(class_path)
    except (ImportError, AttributeError, ValueError, NameError) as exc:
        raise TypeError(f'Refusing to reconstruct a Scrapy request: cannot resolve `_class` {class_path!r}.') from exc

    if not (isinstance(request_cls, type) and issubclass(request_cls, ScrapyRequest)):
        raise TypeError(
            f'Refusing to reconstruct a Scrapy request of type {class_path!r}: it is not a scrapy.Request subclass.'
        )


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
    #
    # The body is stored twice on purpose: as `payload` (used for the extended unique key) and inside the serialized
    # Scrapy request below (used to reconstruct it). Both come from `scrapy_request.body`.
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
        elif scrapy_request.meta.get('apify_request_unique_key'):
            request_kwargs['unique_key'] = scrapy_request.meta['apify_request_unique_key']

        # Serialize the Scrapy request now, before `Request.from_url()` runs below. `from_url()` mutates the
        # `user_data` dict it receives in place (it injects a live `CrawleeRequestData` under `__crawlee`), and that
        # dict can be the spider's own `meta['userData']`. Capturing `to_dict()` first keeps the stored blob free of
        # those injected internals, and copying `user_data` below leaves the spider's request untouched.
        scrapy_request_dict = scrapy_request.to_dict(spider=spider)

        user_data = scrapy_request.meta.get('userData', {})

        # Convert UserData Pydantic model to a plain dict to prevent CrawleeRequestData objects from leaking
        # into Request.from_url() during Scrapy-Apify roundtrips. `model_dump()` already returns a fresh, fully
        # detached dict; the plain-dict case is deep-copied so that neither the `pop` and `from_url()` mutations
        # below nor any mutation of a nested value can ever reach back into the spider's meta.
        if isinstance(user_data, UserData):
            user_data = user_data.model_dump(by_alias=True)
        elif isinstance(user_data, dict):
            user_data = deepcopy(user_data)

        # Remove internal Crawlee data since it's managed by Request.from_url() and values from previous roundtrips
        # cause incorrect state.
        if isinstance(user_data, dict):
            user_data.pop('__crawlee', None)

        request_kwargs['user_data'] = user_data if isinstance(user_data, dict) else {}

        # Store an Apify-platform view of the headers. The authoritative copy with exact bytes travels in
        # the serialized scrapy_request below, so non-UTF-8 headers (which make `to_unicode_dict()` raise) are
        # tolerated rather than dropping the whole request.
        #
        # Trade-off: with `use_extended_unique_key=True` the unique key includes the headers, so when non-UTF-8
        # headers are omitted here two requests differing only in those headers share a unique key and one is
        # deduplicated away. This is rare (header values are normally ASCII/UTF-8) and still strictly better than
        # the old behavior, which dropped such requests entirely.
        if isinstance(scrapy_request.headers, Headers):
            try:
                headers = cast('dict[str, str]', dict(scrapy_request.headers.to_unicode_dict()))
                request_kwargs['headers'] = HttpHeaders(headers)
            except UnicodeDecodeError:
                logger.warning(
                    'Could not represent Scrapy request headers as Apify request headers (non-UTF-8 values); '
                    'they are preserved in the serialized request instead.'
                )
        else:
            logger.warning(
                f'Invalid scrapy_request.headers type, not scrapy.http.headers.Headers: {scrapy_request.headers}'
            )

        apify_request = ApifyRequest.from_url(**request_kwargs)

    except Exception:
        logger.exception(f'Conversion of Scrapy request {scrapy_request} to Apify request failed; skipping it.')
        return None

    # Serialize the Scrapy request as JSON under 'scrapy_request'. Kept outside the broad except above so
    # a non-JSON-serializable `meta`/`cb_kwargs` is logged with a traceback and the request skipped (returning
    # None per this function's contract), rather than crashing the crawl.
    try:
        scrapy_request_json = encode_to_json(scrapy_request_dict)
    except (TypeError, ValueError):
        logger.exception(
            f'Failed to serialize Scrapy request {scrapy_request} for storage on the Apify platform; skipping it. '
            'Ensure all values in `meta` and `cb_kwargs` are JSON-serializable.'
        )
        return None

    # `scrapy_request_json` is already JSON-safe text (binary fields are base64-encoded inside it), so it is stored
    # as-is. The request queue serializes `user_data` to JSON, which escapes the string correctly; wrapping it in
    # a second base64 layer would only add ~33% overhead on the enqueue path.
    apify_request.user_data['scrapy_request'] = scrapy_request_json

    logger.debug(f'scrapy_request was converted to the apify_request={apify_request}')
    return apify_request


def to_scrapy_request(apify_request: ApifyRequest, spider: Spider) -> ScrapyRequest:
    """Convert an Apify request to a Scrapy request.

    Args:
        apify_request: The Apify request to be converted.
        spider: The Scrapy spider that the request is associated with.

    Raises:
        TypeError: If `apify_request` is not an `ApifyRequest`, if the stored Scrapy request payload is malformed,
        or if its `_class` cannot be resolved to a `scrapy.Request` subclass.

    Returns:
        The converted Scrapy request.
    """
    if not isinstance(cast('Any', apify_request), ApifyRequest):
        raise TypeError('apify_request must be an apify.Request instance')

    logger.debug(f'to_scrapy_request was called (apify_request={apify_request})...')

    # If the apify_request comes from the Scrapy
    if 'scrapy_request' in apify_request.user_data:
        # Deserialize the Scrapy ScrapyRequest from the apify_request by parsing the stored JSON and reconstructing
        # the Scrapy ScrapyRequest object from its dictionary representation.
        logger.debug('Restoring the Scrapy ScrapyRequest from the apify_request...')

        scrapy_request_json = apify_request.user_data['scrapy_request']
        if not isinstance(scrapy_request_json, str):
            raise TypeError('the stored scrapy_request must be a string')

        scrapy_request_dict = decode_from_json(scrapy_request_json)
        if not isinstance(scrapy_request_dict, dict):
            raise TypeError('scrapy_request_dict must be a dictionary')

        # Validate any `_class` entry before request_from_dict resolves and imports it.
        _ensure_known_request_class(scrapy_request_dict)

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
