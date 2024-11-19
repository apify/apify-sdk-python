from __future__ import annotations

import asyncio
import re
from asyncio import Task
from functools import partial
from typing import Any, Union

from pydantic import BaseModel, Field, TypeAdapter

from crawlee import Request
from crawlee._types import HttpMethod
from crawlee.http_clients import BaseHttpClient, HttpxHttpClient
from crawlee.storages import RequestList as CrawleeRequestList

URL_NO_COMMAS_REGEX = re.compile(
    r'https?:\/\/(www\.)?([^\W_]|[^\W_][-\w0-9@:%._+~#=]{0,254}[^\W_])\.[a-z]{2,63}(:\d{1,5})?(\/[-\w@:%+.~#?&/=()]*)?'
)


class _RequestDetails(BaseModel):
    method: HttpMethod = 'GET'
    payload: str = ''
    headers: dict[str, str] = Field(default_factory=dict)
    user_data: dict[str, str] = Field(default_factory=dict, alias='userData')


class _RequestsFromUrlInput(_RequestDetails):
    requests_from_url: str = Field(alias='requestsFromUrl')


class _SimpleUrlInput(_RequestDetails):
    url: str


url_input_adapter = TypeAdapter(list[Union[_RequestsFromUrlInput, _SimpleUrlInput]])


class RequestList(CrawleeRequestList):
    """Extends crawlee RequestList."""

    @classmethod
    async def open(
        cls,
        name: str | None = None,
        actor_start_urls_input: list[dict[str, Any]] | None = None,
        http_client: BaseHttpClient | None = None,
    ) -> RequestList:
        """Creates RequestList from Actor input requestListSources.

        name is name of the returned RequestList
        actor_start_urls_input  can contain list dicts with either url or requestsFromUrl key
        http_client is client that will be used to send get request to url defined in requestsFromUrl

        Example actor_start_urls_input:
            [
                # Gather urls from response body.
                {'requestsFromUrl': 'https://crawlee.dev/file.txt', 'method': 'GET'},
                # Directly include this url.
                {'url': 'https://crawlee.dev', 'method': 'GET'}
            ]
        """
        actor_start_urls_input = actor_start_urls_input or []
        return await _create_request_list(name, actor_start_urls_input, http_client)


async def _create_request_list(
    name: str | None, actor_start_urls_input: list[dict[str, Any]], http_client: BaseHttpClient | None
) -> RequestList:
    if not http_client:
        http_client = HttpxHttpClient()

    ulr_inputs = url_input_adapter.validate_python(actor_start_urls_input)  # instance of list[Union[...]]

    simple_url_inputs = [url_input for url_input in ulr_inputs if type(url_input) is _SimpleUrlInput]
    remote_url_inputs = [url_input for url_input in ulr_inputs if type(url_input) is _RequestsFromUrlInput]

    simple_url_requests = _create_requests_from_input(simple_url_inputs)
    remote_url_requests = await _create_requests_from_url(remote_url_inputs, http_client=http_client)

    return RequestList(name=name, requests=simple_url_requests + remote_url_requests)


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


async def _create_requests_from_url(
    remote_url_requests_inputs: list[_RequestsFromUrlInput], http_client: BaseHttpClient
) -> list[Request]:
    """Crete list of requests from url.

    Send GET requests to urls defined in each requests_from_url of remote_url_requests_inputs. Run extracting
    callback on each response body and use URL_NO_COMMAS_REGEX regex to find all links. Create list of Requests from
    collected links and additional inputs stored in other attributes of each remote_url_requests_inputs.
    """
    created_requests: list[Request] = []

    def create_requests_from_response(request_input: _RequestsFromUrlInput, task: Task) -> None:
        """Callback to scrape response body with regexp and create Requests from matches."""
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
