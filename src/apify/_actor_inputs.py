from __future__ import annotations

import asyncio
import re
from asyncio import Task
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from crawlee import Request
from crawlee._types import HttpMethod  #  TODO: Make public in Crawlee?
from crawlee.http_clients import BaseHttpClient, HttpxHttpClient
from crawlee.storages import RequestList

URL_NO_COMMAS_REGEX = re.compile(
    r'https?:\/\/(www\.)?([a-zA-Z0-9]|[a-zA-Z0-9][-a-zA-Z0-9@:%._+~#=]{0,254}[a-zA-Z0-9])\.[a-z]{2,63}(:\d{1,5})?(\/[-a-zA-Z0-9@:%_+.~#?&/=()]*)?'
)

class _RequestDetails(BaseModel):
    method: HttpMethod
    payload: str = ''
    headers: dict[str, str] = Field(default_factory=dict)
    user_data: dict[str, str]= Field(default_factory=dict, alias='user_data')

class _RequestsFromUrlInput(_RequestDetails):
    requests_from_url: str = Field(alias='requests_from_url')

class _SimpleUrlInput(_RequestDetails):
    url: str


@staticmethod
async def _create_request_list(
    *, actor_start_urls_input: list[dict[str, Any]], http_client: BaseHttpClient | None = None
) -> RequestList:
    if not http_client:
        http_client = HttpxHttpClient()
    simple_url_requests_inputs = [
        _SimpleUrlInput(**request_input) for request_input in actor_start_urls_input
        if 'url' in request_input]
    remote_url_requests_inputs = [
        _RequestsFromUrlInput(**request_input) for request_input in actor_start_urls_input
        if 'requests_from_url' in request_input
    ]

    simple_url_requests = _create_requests_from_input(simple_url_requests_inputs)
    remote_url_requests = await _create_requests_from_url(remote_url_requests_inputs, http_client=http_client)

    return RequestList(requests=simple_url_requests + remote_url_requests)


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
async def _create_requests_from_url(
    remote_url_requests_inputs: list[_RequestsFromUrlInput], http_client: BaseHttpClient
) -> list[Request]:
    """Crete list of requests from url.

    Send GET requests to urls defined in each requests_from_url of remote_url_requests_inputs. Run extracting
    callback on each response body and use URL_NO_COMMAS_REGEX regexp to find all links. Create list of Requests from
    collected links and additional inputs stored in other attributes of each remote_url_requests_inputs.
    """
    created_requests: list[Request] = []

    def create_requests_from_response(request_input: _SimpleUrlInput, task: Task) -> list[Request]:
        """Callback to scrape response body with regexp and create Requests from macthes."""
        matches = re.finditer(URL_NO_COMMAS_REGEX, task.result().read().decode('utf-8'))
        created_requests.extend([Request.from_url(
            match.group(0),
            method=request_input.method,
            payload=request_input.payload.encode('utf-8'),
            headers=request_input.headers,
            user_data=request_input.user_data) for match in matches])

    remote_url_requests = []
    for remote_url_requests_input in remote_url_requests_inputs:
        task = asyncio.create_task(
            http_client.send_request(
                method='GET',
                url=remote_url_requests_input.requests_from_url,
            )
        )

        task.add_done_callback(partial(create_requests_from_response, remote_url_requests_input))
        remote_url_requests.append(task)

    await asyncio.gather(*remote_url_requests)
    return created_requests
