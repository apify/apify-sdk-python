import json
from pathlib import Path
from tempfile import mkdtemp
from urllib.parse import urlsplit
from zipfile import ZipFile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions

from apify import Actor


def proxy_auth_extension(proxy_url: str) -> str:
    """Build a Chrome extension that routes Chrome through an authenticated proxy."""
    parts = urlsplit(proxy_url)

    manifest = {
        'name': 'Apify Proxy',
        'version': '1.0.0',
        'manifest_version': 3,
        'permissions': ['proxy', 'webRequest', 'webRequestAuthProvider'],
        'host_permissions': ['<all_urls>'],
        'background': {'service_worker': 'background.js'},
        'minimum_chrome_version': '108',
    }

    # The service worker sets the proxy and answers the auth challenge.
    proxy_config = json.dumps(
        {
            'mode': 'fixed_servers',
            'rules': {
                'singleProxy': {
                    'scheme': parts.scheme,
                    'host': parts.hostname,
                    'port': parts.port,
                },
            },
        }
    )
    credentials = json.dumps(
        {'username': parts.username or '', 'password': parts.password or ''}
    )
    background = (
        'chrome.proxy.settings.set('
        '{value: ' + proxy_config + ', scope: "regular"});\n'
        'chrome.webRequest.onAuthRequired.addListener(\n'
        '    () => ({authCredentials: ' + credentials + '}),\n'
        '    {urls: ["<all_urls>"]},\n'
        '    ["blocking"],\n'
        ');\n'
    )

    extension_path = Path(mkdtemp()) / 'apify_proxy.zip'
    with ZipFile(extension_path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('background.js', background)
    return str(extension_path)


def build_chrome_driver(proxy_url: str) -> webdriver.Chrome:
    """Create a headless Chrome WebDriver routed through an authenticated proxy."""
    chrome_options = ChromeOptions()

    if Actor.configuration.headless:
        # The new headless mode is required to load the proxy extension.
        chrome_options.add_argument('--headless=new')

    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')

    # Load the proxy extension and keep it enabled in headless mode.
    chrome_options.add_extension(proxy_auth_extension(proxy_url))
    chrome_options.add_argument(
        '--disable-features=DisableLoadExtensionCommandLineSwitch'
    )

    return webdriver.Chrome(options=chrome_options)
