import asyncio
from itertools import chain
import re

from crawlee import Request
from crawlee.http_clients import BaseHttpClient, HttpxHttpClient, HttpResponse
from crawlee.storages import RequestList

URL_NO_COMMAS_REGEX = re.compile(
    r'https?:\/\/(www\.)?([a-zA-Z0-9]|[a-zA-Z0-9][-a-zA-Z0-9@:%._+~#=]{0,254}[a-zA-Z0-9])\.[a-z]{2,63}(:\d{1,5})?(\/[-a-zA-Z0-9@:%_+.~#?&/=()]*)?'
)

@staticmethod
async def _create_request_list(
    *, actor_start_urls_input: dict, http_client: BaseHttpClient | None = None
) -> RequestList:
    if not http_client:
        http_client = HttpxHttpClient()
    simple_url_requests_inputs = [
        request_input for request_input in actor_start_urls_input if 'url' in request_input
    ]
    remote_url_requests_inputs = [
        request_input for request_input in actor_start_urls_input if 'requestsFromUrl' in request_input
    ]

    simple_url_requests = _create_requests_from_input(simple_url_requests_inputs)
    remote_url_requests = await _create_requests_from_url(remote_url_requests_inputs, http_client=http_client)

    return RequestList(requests=simple_url_requests + remote_url_requests)


@staticmethod
def _create_requests_from_input(simple_url_requests_inputs: list[dict[str, str]]) -> list[Request]:
    return [
        Request.from_url(
            method=request_input.get('method'),
            url=request_input.get('url'),
            payload=request_input.get('payload', '').encode('utf-8'),
            headers=request_input.get('headers', {}),
            user_data=request_input.get('userData', {}),
        )
        for request_input in simple_url_requests_inputs
    ]


@staticmethod
async def _create_requests_from_url(
    remote_url_requests_inputs: list[dict[str, str]], http_client: BaseHttpClient
) -> list[Request]:
    remote_url_requests = []
    for request_input in remote_url_requests_inputs:
        remote_url_requests.append(
            asyncio.create_task(
                http_client.send_request(
                    method=request_input['method'],
                    url=request_input['requestsFromUrl'],
                    headers=request_input.get('headers', {}),
                    payload=request_input.get('payload', '').encode('utf-8'),
                )
            )
        )
    await asyncio.gather(*remote_url_requests)
    # TODO as callbacks
    a = list(
        extract_requests_from_response(finished_request.result()) for finished_request in remote_url_requests
    )
    return list(chain.from_iterable(a))


@staticmethod
def extract_requests_from_response(response: HttpResponse) -> list[Request]:
    matches = list(re.finditer(URL_NO_COMMAS_REGEX, response.read().decode('utf-8')))
    return [Request.from_url(match.group(0)) for match in matches]
