from importlib import metadata

from crawlee.events._types import Event

from .actor import Actor
from .config import Configuration
from .proxy_configuration import ProxyConfiguration, ProxyInfo

__version__ = metadata.version('apify')

__all__ = ['Actor', 'Event', 'Configuration', 'ProxyConfiguration', 'ProxyInfo', '__version__']
