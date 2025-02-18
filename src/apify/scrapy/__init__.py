from crawlee._utils.try_import import install_import_hook as _install_import_hook
from crawlee._utils.try_import import try_import as _try_import

_install_import_hook(__name__)

# The following imports use try_import to handle optional dependencies, as they may not always be available.

with _try_import(__name__, 'run_scrapy_actor'):
    from ._actor_runner import run_scrapy_actor

with _try_import(__name__, 'initialize_logging'):
    from ._logging_config import initialize_logging

with _try_import(__name__, 'to_apify_request', 'to_scrapy_request'):
    from .requests import to_apify_request, to_scrapy_request

with _try_import(__name__, 'ApifyScheduler'):
    from .scheduler import ApifyScheduler

with _try_import(__name__, 'apply_apify_settings', 'get_basic_auth_header'):
    from .utils import apply_apify_settings, get_basic_auth_header


__all__ = [
    'ApifyScheduler',
    'apply_apify_settings',
    'get_basic_auth_header',
    'initialize_logging',
    'run_scrapy_actor',
    'to_apify_request',
    'to_scrapy_request',
]
