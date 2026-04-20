from __future__ import annotations

import asyncio
import re
from itertools import chain
from typing import Annotated, Any

from pydantic import BaseModel, Field, TypeAdapter

from crawlee._types import HttpMethod
from crawlee.http_clients import HttpClient, ImpitHttpClient
from crawlee.request_loaders import RequestList

from apify import Request
from apify._utils import docs_group

URL_NO_COMMAS_REGEX = re.compile(
    r'https?:\/\/(www\.)?([^\W_]|[^\W_][-\w0-9@:%._+~#=]{0,254}[^\W_])\.[a-z]{2,63}(:\d{1,5})?(\/[-\w@:%+.~#?&/=()]*)?'
)


class _RequestDetails(BaseModel):
    method: HttpMethod = 'GET'
    payload: str = ''
    headers: Annotated[dict[str, str], Field(default_factory=dict)]
    user_data: Annotated[dict[str, str], Field(default_factory=dict, alias='userData')]


class _RequestsFromUrlInput(_RequestDetails):
    requests_from_url: str = Field(alias='requestsFromUrl')


class _SimpleUrlInput(_RequestDetails):
    url: str


url_input_adapter = TypeAdapter(list[_RequestsFromUrlInput | _SimpleUrlInput])


@docs_group('Request loaders')
class ApifyRequestList(RequestList):
    """A request list that can be constructed from the standard Apify `requestListSources` Actor input format.

    This extends the Crawlee `RequestList` with the ability to parse the request list sources input commonly
    used in Apify Actors. It supports two kinds of entries:

    - **Direct URLs** - entries with a `url` key are converted to requests directly.
    - **Remote URL lists** - entries with a `requestsFromUrl` key point to a remote resource (e.g. a plain-text
      file). The resource is fetched and all URLs found in the response body are extracted and converted to requests.

    Both kinds of entries can optionally specify `method`, `payload`, `headers`, and `userData` fields that will be
    applied to every request created from that entry.

    ### Usage

    ```python
    from apify import Actor
    from apify.request_loaders import ApifyRequestList

    async with Actor:
        actor_input = await Actor.get_input() or {}
        request_list = await ApifyRequestList.open(
            request_list_sources_input=actor_input.get('requestListSources', []),
        )
    ```
    """

    @classmethod
    async def open(
        cls,
        *,
        name: str | None = None,
        request_list_sources_input: list[dict[str, Any]] | None = None,
        http_client: HttpClient | None = None,
    ) -> ApifyRequestList:
        """Create a new `ApifyRequestList` from the standard Apify request list sources input.

        Each entry in `request_list_sources_input` is a dict with either a `url` key (for a direct URL) or
        a `requestsFromUrl` key (for a remote resource whose response body is scanned for URLs). Optional keys
        `method`, `payload`, `headers`, and `userData` are applied to every request produced from that entry.

        Args:
            name: An optional name for the request list, used for state persistence.
            request_list_sources_input: A list of request source dicts in the standard Apify format. Each dict must
                contain either a `url` key or a `requestsFromUrl` key. If `None` or empty, an empty request list
                is returned.
            http_client: HTTP client used to fetch remote URL lists (entries with `requestsFromUrl`). Defaults to
                `ImpitHttpClient` if not provided.

        Returns:
            A new `ApifyRequestList` populated with the resolved requests.
        """
        request_list_sources_input = request_list_sources_input or []

        if not http_client:
            http_client = ImpitHttpClient()

        url_inputs = url_input_adapter.validate_python(request_list_sources_input)

        simple_url_inputs = [url_input for url_input in url_inputs if isinstance(url_input, _SimpleUrlInput)]
        remote_url_inputs = [url_input for url_input in url_inputs if isinstance(url_input, _RequestsFromUrlInput)]

        simple_url_requests = cls._create_requests_from_input(simple_url_inputs)
        remote_url_requests = await cls._fetch_requests_from_url(remote_url_inputs, http_client)

        return ApifyRequestList(name=name, requests=simple_url_requests + remote_url_requests)

    @classmethod
    async def _fetch_requests_from_url(
        cls,
        remote_url_requests_inputs: list[_RequestsFromUrlInput],
        http_client: HttpClient,
    ) -> list[Request]:
        """Fetch all remote URL sources concurrently and return the extracted requests.

        For each entry, a GET request is sent to the `requests_from_url` URL. All URLs matching `URL_NO_COMMAS_REGEX`
        are extracted from the response body and turned into `Request` objects, inheriting `method`, `payload`,
        `headers`, and `user_data` from the source entry.
        """
        tasks = [cls._process_remote_url(request_input, http_client) for request_input in remote_url_requests_inputs]
        results = await asyncio.gather(*tasks)
        return list(chain.from_iterable(results))

    @staticmethod
    def _create_requests_from_input(simple_url_inputs: list[_SimpleUrlInput]) -> list[Request]:
        """Create `Request` objects from simple URL inputs."""
        return [
            Request.from_url(
                method=request_input.method,
                url=request_input.url,
                payload=request_input.payload.encode('utf-8'),
                headers=request_input.headers,
                user_data=request_input.user_data,
            )
            for request_input in simple_url_inputs
        ]

    @staticmethod
    async def _process_remote_url(request_input: _RequestsFromUrlInput, http_client: HttpClient) -> list[Request]:
        """Fetch a remote URL and extract links from the response body."""
        http_response = await http_client.send_request(method='GET', url=request_input.requests_from_url)
        response_body = await http_response.read()
        matches = re.finditer(URL_NO_COMMAS_REGEX, response_body.decode('utf-8', errors='replace'))

        return [
            Request.from_url(
                url=match.group(0),
                method=request_input.method,
                payload=request_input.payload.encode('utf-8'),
                headers=request_input.headers,
                user_data=request_input.user_data,
            )
            for match in matches
        ]
