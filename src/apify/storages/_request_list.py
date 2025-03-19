from __future__ import annotations

import asyncio
import re
from asyncio import Task
from functools import partial
from typing import Annotated, Any, Union

from pydantic import BaseModel, Field, TypeAdapter

from crawlee import Request
from crawlee._types import HttpMethod
from crawlee.http_clients import HttpClient, HttpxHttpClient
from crawlee.request_loaders import RequestList as CrawleeRequestList

from apify._utils import docs_group

URL_NO_COMMAS_REGEX = re.compile(
    r'https?:\/\/(www\.)?([^\W_]|[^\W_][-\w0-9@:%._+~#=]{0,254}[^\W_])\.[a-z]{2,63}(:\d{1,5})?(\/[-\w@:%+.~#?&/=()]*)?'
)


class _RequestDetails(BaseModel):
    method: HttpMethod = 'GET'
    payload: str = ''
    headers: Annotated[dict[str, str], Field(default_factory=dict)] = {}
    user_data: Annotated[dict[str, str], Field(default_factory=dict, alias='userData')] = {}


class _RequestsFromUrlInput(_RequestDetails):
    requests_from_url: str = Field(alias='requestsFromUrl')


class _SimpleUrlInput(_RequestDetails):
    url: str


url_input_adapter = TypeAdapter(list[Union[_RequestsFromUrlInput, _SimpleUrlInput]])


@docs_group('Classes')
class RequestList(CrawleeRequestList):
    """Extends crawlee RequestList.

    Method open is used to create RequestList from actor's requestListSources input.
    """

    @staticmethod
    async def open(
        name: str | None = None,
        request_list_sources_input: list[dict[str, Any]] | None = None,
        http_client: HttpClient | None = None,
    ) -> RequestList:
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
        return await RequestList._create_request_list(name, request_list_sources_input, http_client)

    @staticmethod
    async def _create_request_list(
        name: str | None, request_list_sources_input: list[dict[str, Any]], http_client: HttpClient | None
    ) -> RequestList:
        if not http_client:
            http_client = HttpxHttpClient()

        url_inputs = url_input_adapter.validate_python(request_list_sources_input)

        simple_url_inputs = [url_input for url_input in url_inputs if isinstance(url_input, _SimpleUrlInput)]
        remote_url_inputs = [url_input for url_input in url_inputs if isinstance(url_input, _RequestsFromUrlInput)]

        simple_url_requests = RequestList._create_requests_from_input(simple_url_inputs)
        remote_url_requests = await RequestList._fetch_requests_from_url(remote_url_inputs, http_client=http_client)

        return RequestList(name=name, requests=simple_url_requests + remote_url_requests)

    @staticmethod
    def _create_requests_from_input(simple_url_inputs: list[_SimpleUrlInput]) -> list[Request]:
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
    async def _fetch_requests_from_url(
        remote_url_requests_inputs: list[_RequestsFromUrlInput],
        http_client: HttpClient,
    ) -> list[Request]:
        """Create list of requests from url.

        Send GET requests to urls defined in each requests_from_url of remote_url_requests_inputs. Run extracting
        callback on each response body and use URL_NO_COMMAS_REGEX regex to find all links. Create list of Requests from
        collected links and additional inputs stored in other attributes of each remote_url_requests_inputs.
        """
        created_requests: list[Request] = []

        def create_requests_from_response(request_input: _RequestsFromUrlInput, task: Task) -> None:
            """Extract links from response body and use them to create `Request` objects.

            Use the regular expression to find all matching links in the response body, then create `Request`
            objects from these links and the provided input attributes.
            """
            matches = re.finditer(URL_NO_COMMAS_REGEX, task.result().read().decode('utf-8'))
            created_requests.extend(
                [
                    Request.from_url(
                        match.group(0),
                        method=request_input.method,
                        payload=request_input.payload.encode('utf-8'),
                        headers=request_input.headers,
                        user_data=request_input.user_data,
                    )
                    for match in matches
                ]
            )

        remote_url_requests = []
        for remote_url_requests_input in remote_url_requests_inputs:
            get_response_task = asyncio.create_task(
                http_client.send_request(
                    method='GET',
                    url=remote_url_requests_input.requests_from_url,
                )
            )

            get_response_task.add_done_callback(partial(create_requests_from_response, remote_url_requests_input))
            remote_url_requests.append(get_response_task)

        await asyncio.gather(*remote_url_requests)
        return created_requests
