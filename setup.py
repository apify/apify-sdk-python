import pathlib

from setuptools import find_packages, setup

here = pathlib.Path(__file__).parent.resolve()

long_description = (here / 'README.md').read_text(encoding='utf-8')

version_file = (here / 'src/apify/_version.py').read_text(encoding='utf-8')
version = None
for line in version_file.splitlines():
    if line.startswith('__version__'):
        delim = '"' if '"' in line else "'"
        version = line.split(delim)[1]
        break
else:
    raise RuntimeError('Unable to find version string.')

setup(
    name='apify',
    version=version,

    author='Apify Technologies s.r.o.',
    author_email='support@apify.com',
    url='https://github.com/apify/apify-sdk-python',
    project_urls={
        'Documentation': 'https://docs.apify.com/apify-sdk-python',
        'Source': 'https://github.com/apify/apify-sdk-python',
        'Issue tracker': 'https://github.com/apify/apify-sdk-python/issues',
        'Apify Homepage': 'https://apify.com',
    },
    license='Apache Software License',
    license_files=['LICENSE'],

    description='Apify SDK for Python',
    long_description=long_description,
    long_description_content_type='text/markdown',

    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries',
    ],
    keywords='apify, sdk, actor, scraping, automation',

    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    package_data={'apify': ['py.typed']},
    python_requires='>=3.8',
    install_requires=[
        'apify-client ~= 0.7.0b46',
        'httpx ~= 0.23.0',
        'psutil ~= 5.9.4',
        'pydantic ~= 1.10.2',
        'pyee ~= 9.0.4',
        'typing-extensions ~= 4.4.0',
        'websockets ~= 10.4',
        'aiofiles ~= 22.1.0',
        'aioshutil ~= 1.2',
        'cryptography ~= 39.0.1',
    ],
    extras_require={
        'dev': [
            'autopep8 ~= 2.0.1',
            'filelock ~= 3.9.0',
            'flake8 ~= 6.0.0',
            'flake8-bugbear ~= 23.1.20',
            'flake8-commas ~= 2.1.0',
            'flake8-docstrings ~= 1.7.0',
            'flake8-isort ~= 6.0.0',
            'flake8-quotes ~= 3.3.1',
            'flake8-unused-arguments ~= 0.0.13',  # TODO: remove overload noqa
            'isort ~= 5.12.0',
            'mypy ~= 1.0.0',
            'pep8-naming ~= 0.13.2',
            'pre-commit ~= 3.0.1',
            'pytest ~= 7.2.0',
            'pytest-asyncio ~= 0.20.3',
            'pytest-only ~= 2.0.0',
            'pytest-randomly ~= 3.12.0',
            'pytest-timeout ~= 2.1.0',
            'pytest-xdist ~= 3.2.0',
            'respx ~= 0.20.1',
            'sphinx ~= 6.1.3',
            'sphinx-autodoc-typehints ~= 1.22',
            'sphinx-markdown-builder == 0.5.4',  # pinned to 0.5.4, because 0.5.5 has a formatting bug
            'types-aiofiles ~= 22.1.0.4',
            'types-psutil ~= 5.9.5.5',
            'types-setuptools',  # always latest, since we always install latest setuptools
        ],
    },
)
