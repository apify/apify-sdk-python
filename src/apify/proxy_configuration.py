import inspect
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict, Union
from urllib.parse import urlparse

import httpx
from pydantic import AnyUrl, Field, validate_arguments
from typing_extensions import Annotated, NotRequired

from apify_client import ApifyClientAsync

from .config import Configuration
from .consts import ApifyEnvVars

APIFY_PROXY_VALUE_REGEX = r'^[\w._~]+$'
COUNTRY_CODE_REGEX = r'^[A-Z]{2}$'
SESSION_ID_MAX_LENGTH = 50
SESSION_ID_PYDANTIC_FIELD = Field(regex=APIFY_PROXY_VALUE_REGEX, max_length=SESSION_ID_MAX_LENGTH)


# TODO: Remove this once Pydantic fixes https://github.com/pydantic/pydantic/issues/4333
def _check(
    value: Any,
    *,
    label: Optional[str],
    regex: Optional[str] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
) -> None:
    error_str = f'Value {value}'
    if label:
        error_str += f' of argument {label}'

    if min_length and len(value) < min_length:
        raise ValueError(f'{error_str} is shorter than minimum allowed length {min_length}')

    if max_length and len(value) > max_length:
        raise ValueError(f'{error_str} is longer than maximum allowed length {max_length}')

    if regex and not re.match(regex, value):
        raise ValueError(f'{error_str} does not match regex {regex}')


class ProxyInfo(TypedDict):
    """Provides information about a proxy connection that is used for requests."""

    url: str
    """The URL of the proxy."""

    hostname: str
    """The hostname of the proxy."""

    port: int
    """The proxy port."""

    username: NotRequired[str]
    """The username for the proxy."""

    password: str
    """The password for the proxy."""

    groups: NotRequired[List[str]]
    """An array of proxy groups to be used by the [Apify Proxy](https://docs.apify.com/proxy).
    If not provided, the proxy will select the groups automatically.
    """

    country_code: NotRequired[str]
    """If set and relevant proxies are available in your Apify account, all proxied requests will
    use IP addresses that are geolocated to the specified country. For example `GB` for IPs
    from Great Britain. Note that online services often have their own rules for handling
    geolocation and thus the country selection is a best attempt at geolocation, rather than
    a guaranteed hit. This parameter is optional, by default, each proxied request is assigned
    an IP address from a random country. The country code needs to be a two letter ISO country code.
    See the [full list of available country codes](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#Officially_assigned_code_elements).
    This parameter is optional, by default, the proxy uses all available proxy servers from all countries.
    """

    session_id: NotRequired[str]
    """The identifier of the used proxy session, if used. Using the same session ID guarantees getting the same proxy URL."""


class ProxyConfiguration:
    """Configures a connection to a proxy server with the provided options.

    Proxy servers are used to prevent target websites from blocking your crawlers based on IP address rate limits or blacklists.
    The default servers used by this class are managed by [Apify Proxy](https://docs.apify.com/proxy).
    To be able to use Apify Proxy, you need an Apify account and access to the selected proxies. If you provide no configuration option,
    the proxies will be managed automatically using a smart algorithm.

    If you want to use your own proxies, use the `proxy_urls` or `new_url_function` constructor options.
    Your list of proxy URLs will be rotated by the configuration, if this option is provided.

    **Example usage:**

    ```python

    proxy_configuration = await Actor.create_proxy_configuration(
      groups=['GROUP1', 'GROUP2']  # List of Apify Proxy groups
      country_code='US',
    )

    proxy_url = await proxy_configuration.new_url()

    with httpx.AsyncClient(proxies=proxy_url) as client:
        response = await client.get(...)
    ```
    """

    is_man_in_the_middle = False

    _next_custom_url_index = 0
    _proxy_urls: List[str] = []
    _used_proxy_urls: Dict[str, str] = {}
    _new_url_function: Optional[Union[Callable[[Optional[str]], str], Callable[[Optional[str]], Awaitable[str]]]] = None
    _groups: List[str] = []
    _country_code: Optional[str] = None
    _password: Optional[str] = None
    _hostname: str
    _port: int
    _uses_apify_proxy: Optional[bool] = None
    _actor_config: Configuration
    _apify_client: Optional[ApifyClientAsync] = None

    @validate_arguments(config=dict(arbitrary_types_allowed=True))
    def __init__(
        self,
        *,
        password: Optional[str] = None,
        groups: Optional[List[Annotated[str, Field(regex=APIFY_PROXY_VALUE_REGEX)]]] = None,
        country_code: Optional[Annotated[str, Field(regex=COUNTRY_CODE_REGEX)]] = None,
        proxy_urls: Optional[List[Annotated[str, AnyUrl]]] = None,
        new_url_function: Optional[Union[Callable[[Optional[str]], str], Callable[[Optional[str]], Awaitable[str]]]] = None,
        actor_config: Optional[Configuration] = None,
        apify_client: Optional[ApifyClientAsync] = None,
    ):
        """Create a ProxyConfiguration instance. It is highly recommended to use `Actor.create_proxy_configuration()` instead of this.

        Args:
            password (str, optional): Password for the Apify Proxy. If not provided, will use os.environ['APIFY_PROXY_PASSWORD'], if available.
            groups (list of str, optional): Proxy groups which the Apify Proxy should use, if provided.
            country_code (str, optional): Country which the Apify Proxy should use, if provided.
            proxy_urls (list of str, optional): Custom proxy server URLs which should be rotated through.
            new_url_function (Callable, optional): Function which returns a custom proxy URL to be used.
        """  # noqa: D417 # we don't want to document the actor_config and apify_client arguments, they're internal
        if groups:
            for group in groups:
                _check(group, label='groups', regex=APIFY_PROXY_VALUE_REGEX)
        if country_code:
            _check(country_code, label='country_code', regex=COUNTRY_CODE_REGEX)

        # Validation
        if proxy_urls and new_url_function:
            raise ValueError('Cannot combine custom proxies in "proxy_urls" with custom generating function in "new_url_function".')

        if (proxy_urls or new_url_function) and (groups or country_code):
            raise ValueError('Cannot combine custom proxies with Apify Proxy!'
                             ' It is not allowed to set "proxy_urls" or "new_url_function" combined with'
                             ' "groups" or "country_code".')

        # mypy has a bug with narrowing types for filter (https://github.com/python/mypy/issues/12682)
        if proxy_urls and next(filter(lambda url: 'apify.com' in url, proxy_urls), None):  # type: ignore
            print('Some Apify proxy features may work incorrectly. Please consider setting up Apify properties instead of `proxy_urls`.\n'
                  'See https://sdk.apify.com/docs/guides/proxy-management#apify-proxy-configuration')

        self._actor_config = actor_config or Configuration._get_default_instance()
        self._apify_client = apify_client

        self._hostname = self._actor_config.proxy_hostname
        self._port = self._actor_config.proxy_port
        self._password = password or self._actor_config.proxy_password

        self._proxy_urls = proxy_urls or []
        self._new_url_function = new_url_function
        self._groups = groups or []
        self._country_code = country_code
        self._uses_apify_proxy = not (proxy_urls or new_url_function)

    async def initialize(self) -> None:
        """Load the Apify Proxy password if the API token is provided and check access to Apify Proxy and provided proxy groups.

        Only called if Apify Proxy configuration is used.
        Also checks if country has access to Apify Proxy groups if the country code is provided.

        You should use the Actor.create_proxy_configuration function
        to create a pre-initialized `ProxyConfiguration` instance instead of calling this manually.
        """
        if self._uses_apify_proxy:
            await self._maybe_fetch_password()
            await self._check_access()

    @validate_arguments
    async def new_url(self, session_id: Optional[Annotated[Union[int, str], SESSION_ID_PYDANTIC_FIELD]] = None) -> str:
        """Return a new proxy URL based on provided configuration options and the `sessionId` parameter.

        Args:
            session_id (int or str, optional): Represents the identifier of a proxy session (https://docs.apify.com/proxy#sessions).
            All the HTTP requests going through the proxy with the same session identifier
            will use the same target proxy server (i.e. the same IP address).
            The identifier must not be longer than 50 characters and include only the following: `0-9`, `a-z`, `A-Z`, `"."`, `"_"` and `"~"`.

        Returns:
            str: A string with a proxy URL, including authentication credentials and port number.
                 For example, `http://bob:password123@proxy.example.com:8000`
        """
        if session_id is not None:
            session_id = f'{session_id}'
            _check(session_id, label='session_id', max_length=SESSION_ID_MAX_LENGTH, regex=APIFY_PROXY_VALUE_REGEX)

        if self._new_url_function:
            try:
                res = self._new_url_function(session_id)
                if inspect.isawaitable(res):
                    res = await res
                return str(res)
            except Exception as e:
                raise ValueError('The provided "new_url_function" did not return a valid URL') from e

        if self._proxy_urls:
            if not session_id:
                index = self._next_custom_url_index
                self._next_custom_url_index = (self._next_custom_url_index + 1) % len(self._proxy_urls)
                return self._proxy_urls[index]
            else:
                if session_id not in self._used_proxy_urls:
                    index = self._next_custom_url_index
                    self._next_custom_url_index = (self._next_custom_url_index + 1) % len(self._proxy_urls)
                    self._used_proxy_urls[session_id] = self._proxy_urls[index]

                return self._used_proxy_urls[session_id]

        username = self._get_username(session_id)

        return f'http://{username}:{self._password}@{self._hostname}:{self._port}'

    @validate_arguments
    async def new_proxy_info(self, session_id: Optional[Annotated[Union[int, str], SESSION_ID_PYDANTIC_FIELD]] = None) -> ProxyInfo:
        """Create a new ProxyInfo object.

        Use it if you want to work with a rich representation of a proxy URL.
        If you need the URL string only, use `ProxyConfiguration.new_url`.

        Args:
            session_id (int or str, optional): Represents the identifier of a proxy session (https://docs.apify.com/proxy#sessions).
            All the HTTP requests going through the proxy with the same session identifier
            will use the same target proxy server (i.e. the same IP address).
            The identifier must not be longer than 50 characters and include only the following: `0-9`, `a-z`, `A-Z`, `"."`, `"_"` and `"~"`.

        Returns:
            ProxyInfo: Dictionary that represents information about the proxy and its configuration.
        """
        if session_id is not None:
            session_id = f'{session_id}'
            _check(session_id, label='session_id', max_length=SESSION_ID_MAX_LENGTH, regex=APIFY_PROXY_VALUE_REGEX)

        url = await self.new_url(session_id)
        res: ProxyInfo
        if self._uses_apify_proxy:
            res = {
                'url': url,
                'hostname': self._hostname,
                'port': self._port,
                'username': self._get_username(session_id),
                'password': self._password or '',
                'groups': self._groups,
            }
            if self._country_code:
                res['country_code'] = self._country_code
            if session_id is not None:
                res['session_id'] = session_id
            return res
        else:
            parsed_url = urlparse(url)
            assert parsed_url.hostname is not None
            assert parsed_url.port is not None
            res = {
                'url': url,
                'hostname': parsed_url.hostname,
                'port': parsed_url.port,
                'password': parsed_url.password or '',
            }
            if parsed_url.username:
                res['username'] = parsed_url.username
        return res

    async def _maybe_fetch_password(self) -> None:
        token = self._actor_config.token

        if token and self._apify_client:
            user_info = await self._apify_client.user().get()
            if user_info:
                password = user_info['proxy']['password']

                if self._password:
                    if self._password != password:
                        print('The Apify Proxy password you provided belongs to'
                              ' a different user than the Apify token you are using. Are you sure this is correct?')
                else:
                    self._password = password

        if not self._password:
            raise ValueError('Apify Proxy password must be provided using the "password" constructor argument'
                             f' or the "{ApifyEnvVars.PROXY_PASSWORD}" environment variable.'
                             f' If you add the "{ApifyEnvVars.TOKEN}" environment variable, the password will be automatically inferred.')

    async def _check_access(self) -> None:
        proxy_status_url = f'{self._actor_config.proxy_status_url}/?format=json'

        status = None
        async with httpx.AsyncClient(proxies=await self.new_url()) as client:
            for _ in range(2):
                try:
                    response = await client.get(proxy_status_url)
                    status = response.json()
                    break
                except Exception:
                    # retry on connection errors
                    pass

        if status:
            if not status['connected']:
                raise ConnectionError(status['connectionError'])

            self.is_man_in_the_middle = status['isManInTheMiddle']
        else:
            print('Apify Proxy access check timed out. Watch out for errors with status code 407. '
                  "If you see some, it most likely means you don't have access to either all or some of the proxies you're trying to use.")

    def _get_username(self, session_id: Optional[Union[int, str]] = None) -> str:
        if session_id is not None:
            session_id = f'{session_id}'

        parts: List[str] = []

        if self._groups:
            parts.append(f'groups-{"+".join(self._groups)}')
        if session_id is not None:
            parts.append(f'session-{session_id}')
        if (self._country_code):
            parts.append(f'country-{self._country_code}')

        if not parts:
            return 'auto'

        return ','.join(parts)
