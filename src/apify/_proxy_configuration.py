from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from re import Pattern
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

import httpx

from apify_shared.consts import ApifyEnvVars
from apify_shared.utils import ignore_docs
from crawlee.proxy_configuration import ProxyConfiguration as CrawleeProxyConfiguration
from crawlee.proxy_configuration import ProxyInfo as CrawleeProxyInfo
from crawlee.proxy_configuration import _NewUrlFunction

from apify._configuration import Configuration
from apify._utils import docs_group
from apify.log import logger

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync
    from crawlee import Request

APIFY_PROXY_VALUE_REGEX = re.compile(r'^[\w._~]+$')
COUNTRY_CODE_REGEX = re.compile(r'^[A-Z]{2}$')
SESSION_ID_MAX_LENGTH = 50


@ignore_docs
def is_url(url: str) -> bool:
    """Check if the given string is a valid URL."""
    try:
        parsed_url = urlparse(urljoin(url, '/'))
        has_all_parts = all([parsed_url.scheme, parsed_url.netloc, parsed_url.path])
        is_domain = '.' in parsed_url.netloc
        is_localhost = parsed_url.netloc == 'localhost'
        try:
            ipaddress.ip_address(parsed_url.netloc)
            is_ip_address = True
        except Exception:
            is_ip_address = False

        return has_all_parts and any([is_domain, is_localhost, is_ip_address])
    except Exception:
        return False


def _check(
    value: Any,
    *,
    label: str | None,
    pattern: Pattern | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
) -> None:
    error_str = f'Value {value}'
    if label:
        error_str += f' of argument {label}'

    if min_length and len(value) < min_length:
        raise ValueError(f'{error_str} is shorter than minimum allowed length {min_length}')

    if max_length and len(value) > max_length:
        raise ValueError(f'{error_str} is longer than maximum allowed length {max_length}')

    if pattern and not re.fullmatch(pattern, value):
        raise ValueError(f'{error_str} does not match pattern {pattern.pattern!r}')


@docs_group('Classes')
@dataclass
class ProxyInfo(CrawleeProxyInfo):
    """Provides information about a proxy connection that is used for requests."""

    groups: list[str] = field(default_factory=list)
    """An array of proxy groups to be used by the [Apify Proxy](https://docs.apify.com/proxy). If not provided,
    the proxy will select the groups automatically."""

    country_code: str | None = None
    """If set and relevant proxies are available in your Apify account, all proxied requests will use IP addresses
    that are geolocated to the specified country. For example `GB` for IPs from Great Britain. Note that online
    services often have their own rules for handling geolocation and thus the country selection is a best attempt
    at geolocation, rather than a guaranteed hit. This parameter is optional, by default, each proxied request is
    assigned an IP address from a random country. The country code needs to be a two letter ISO country code.
    See the [full list of available country codes](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#Officially_assigned_code_elements).
    This parameter is optional, by default, the proxy uses all available proxy servers from all countries.
    """


@docs_group('Classes')
class ProxyConfiguration(CrawleeProxyConfiguration):
    """Configures a connection to a proxy server with the provided options.

    Proxy servers are used to prevent target websites from blocking your crawlers based on IP address rate limits or
    blacklists. The default servers used by this class are managed by [Apify Proxy](https://docs.apify.com/proxy).
    To be able to use Apify Proxy, you need an Apify account and access to the selected proxies. If you provide
    no configuration option, the proxies will be managed automatically using a smart algorithm.

    If you want to use your own proxies, use the `proxy_urls` or `new_url_function` constructor options. Your list
    of proxy URLs will be rotated by the configuration, if this option is provided.
    """

    _configuration: Configuration

    @ignore_docs
    def __init__(
        self,
        *,
        password: str | None = None,
        groups: list[str] | None = None,
        country_code: str | None = None,
        proxy_urls: list[str | None] | None = None,
        new_url_function: _NewUrlFunction | None = None,
        tiered_proxy_urls: list[list[str | None]] | None = None,
        _actor_config: Configuration | None = None,
        _apify_client: ApifyClientAsync | None = None,
    ) -> None:
        """Create a ProxyConfiguration instance.

        It is highly recommended to use `Actor.create_proxy_configuration()` instead of this.

        Args:
            password: Password for the Apify Proxy. If not provided, will use os.environ['APIFY_PROXY_PASSWORD'],
                if available.
            groups: Proxy groups which the Apify Proxy should use, if provided.
            country_code: Country which the Apify Proxy should use, if provided.
            proxy_urls: Custom proxy server URLs which should be rotated through.
            new_url_function: Function which returns a custom proxy URL to be used.
            tiered_proxy_urls: Proxy URLs arranged into tiers
        """
        _actor_config = _actor_config or Configuration.get_global_configuration()

        if groups:
            groups = [str(group) for group in groups]
            for group in groups:
                _check(group, label='groups', pattern=APIFY_PROXY_VALUE_REGEX)

        if country_code:
            country_code = str(country_code)
            _check(country_code, label='country_code', pattern=COUNTRY_CODE_REGEX)

        if (proxy_urls or new_url_function or tiered_proxy_urls) and (groups or country_code):
            raise ValueError(
                'Cannot combine custom proxies with Apify Proxy!'
                ' It is not allowed to set "proxy_urls" or "new_url_function" combined with'
                ' "groups" or "country_code".'
            )

        if proxy_urls and any('apify.com' in (url or '') for url in proxy_urls):
            logger.warning(
                'Some Apify proxy features may work incorrectly. Please consider setting up Apify properties '
                'instead of `proxy_urls`.\n'
                'See https://sdk.apify.com/docs/guides/proxy-management#apify-proxy-configuration'
            )

        self._uses_apify_proxy = not (proxy_urls or new_url_function or tiered_proxy_urls)

        super().__init__(
            proxy_urls=[f'http://{_actor_config.proxy_hostname}:{_actor_config.proxy_port}']
            if self._uses_apify_proxy
            else proxy_urls,
            new_url_function=new_url_function,
            tiered_proxy_urls=tiered_proxy_urls,
        )
        self._configuration = _actor_config

        self.is_man_in_the_middle = False

        self._apify_client = _apify_client

        self._hostname = self._configuration.proxy_hostname
        self._port = self._configuration.proxy_port
        self._password = password or self._configuration.proxy_password

        self._groups = list(groups) if groups else []
        self._country_code = country_code

    async def initialize(self) -> None:
        """Check if using proxy, if so, check the access.

        Load the Apify Proxy password from API (only if not passed to constructor or through env var).

        Only called if Apify Proxy configuration is used. Also checks if country has access to Apify Proxy groups
        if the country code is provided.

        You should use the Actor.create_proxy_configuration function to create a pre-initialized
        `ProxyConfiguration` instance instead of calling this manually.
        """
        if self._uses_apify_proxy:
            if not self._password:
                await self._maybe_fetch_password()
            if not self._password:
                raise ValueError(
                    'Apify Proxy password must be provided using the "password" constructor argument '
                    f'or the "{ApifyEnvVars.PROXY_PASSWORD}" environment variable. '
                    f'You can also provide your Apify token via the "${ApifyEnvVars.TOKEN}" environment variable, '
                    f'so that the SDK can fetch the proxy password from Apify API, '
                    f'when not provided through constructor or ${ApifyEnvVars.PROXY_PASSWORD}.'
                )

            await self._check_access()

    async def new_proxy_info(
        self,
        session_id: str | None = None,
        request: Request | None = None,
        proxy_tier: int | None = None,
    ) -> ProxyInfo | None:
        """Create a new ProxyInfo object.

        Use it if you want to work with a rich representation of a proxy URL. If you need the URL string only,
        use `ProxyConfiguration.new_url`.

        Args:
            session_id: Represents the identifier of a proxy session (https://docs.apify.com/proxy#sessions).
                All the HTTP requests going through the proxy with the same session identifier will use the same
                target proxy server (i.e. the same IP address). The identifier must not be longer than 50 characters
                and include only the following: `0-9`, `a-z`, `A-Z`, `"."`, `"_"` and `"~"`.
            request: request for which the proxy info is being issued, used in proxy tier handling.
            proxy_tier: allows forcing the proxy tier to be used.

        Returns:
            Dictionary that represents information about the proxy and its configuration.
        """
        if session_id is not None:
            _check(session_id, label='session_id', max_length=SESSION_ID_MAX_LENGTH, pattern=APIFY_PROXY_VALUE_REGEX)

        proxy_info = await super().new_proxy_info(session_id=session_id, request=request, proxy_tier=proxy_tier)

        if proxy_info is None:
            return None

        if self._uses_apify_proxy:
            parsed_url = httpx.URL(proxy_info.url)
            username = self._get_username(session_id)

            return ProxyInfo(
                url=f'http://{username}:{self._password or ""}@{parsed_url.host}:{parsed_url.port}',
                scheme='http',
                hostname=proxy_info.hostname,
                port=proxy_info.port,
                username=username,
                password=self._password or '',
                session_id=proxy_info.session_id,
                proxy_tier=proxy_info.proxy_tier,
                groups=self._groups,
                country_code=self._country_code or None,
            )

        return ProxyInfo(
            url=proxy_info.url,
            scheme=proxy_info.scheme,
            hostname=proxy_info.hostname,
            port=proxy_info.port,
            username=proxy_info.username,
            password=proxy_info.password,
            session_id=proxy_info.session_id,
            proxy_tier=proxy_info.proxy_tier,
        )

    async def _maybe_fetch_password(self) -> None:
        token = self._configuration.token

        if token and self._apify_client:
            user_info = await self._apify_client.user().get()
            if user_info:
                password = user_info['proxy']['password']
                self._password = password

    async def _check_access(self) -> None:
        proxy_status_url = f'{self._configuration.proxy_status_url}/?format=json'
        proxy_info = await self.new_proxy_info()

        if proxy_info is None:
            return

        status = None
        async with httpx.AsyncClient(proxy=proxy_info.url, timeout=10) as client:
            for _ in range(2):
                try:
                    response = await client.get(proxy_status_url)
                    status = response.json()
                    break
                except Exception:  # noqa: S110
                    # retry on connection errors
                    pass

        if status:
            if not status['connected']:
                raise ConnectionError(status['connectionError'])

            self.is_man_in_the_middle = status['isManInTheMiddle']
        else:
            logger.warning(
                'Apify Proxy access check timed out. Watch out for errors with status code 407. If you see some, it '
                'most likely means you do not have access to either all or some of the proxies you are trying to use.'
            )

    def _get_username(self, session_id: int | str | None = None) -> str:
        if session_id is not None:
            session_id = f'{session_id}'

        parts: list[str] = []

        if self._groups:
            parts.append(f'groups-{"+".join(self._groups)}')
        if session_id is not None:
            parts.append(f'session-{session_id}')
        if self._country_code:
            parts.append(f'country-{self._country_code}')

        if not parts:
            return 'auto'

        return ','.join(parts)
