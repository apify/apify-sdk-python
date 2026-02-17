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
    """Extends crawlee RequestList.

    Method open is used to create RequestList from actor's requestListSources input.
    """

    @classmethod
    async def open(
        cls,
        *,
        name: str | None = None,
        request_list_sources_input: list[dict[str, Any]] | None = None,
        http_client: HttpClient | None = None,
    ) -> ApifyRequestList:
        """Initialize a new instance from request list source input.

        Args:
            name: Name of the returned RequestList.
            request_list_sources_input: List of dicts with either url key or requestsFromUrl key.
            http_client: Client that will be used to send get request to urls defined by value of requestsFromUrl keys.

        Returns:
            RequestList created from request_list_sources_input.

        ### Usage

        ```python
        example_input = [
            # Gather urls from response body.
            {'requestsFromUrl': 'https://crawlee.dev/file.txt', 'method': 'GET'},
            # Directly include this url.
            {'url': 'https://crawlee.dev', 'method': 'GET'}
        ]
        request_list = await RequestList.open(request_list_sources_input=example_input)
        ```
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
        """Create list of requests from url.

        Send GET requests to urls defined in each requests_from_url of remote_url_requests_inputs. Extract links from
        each response body using URL_NO_COMMAS_REGEX regex. Create list of Requests from collected links and additional
        inputs stored in other attributes of each remote_url_requests_inputs.
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
        matches = re.finditer(URL_NO_COMMAS_REGEX, response_body.decode('utf-8'))

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
