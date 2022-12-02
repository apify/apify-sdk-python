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
        'apify-client ~= 0.7.0b30',
        'psutil ~= 5.9.4',
        'pyee ~= 9.0.4',
        'websockets ~= 10.4',
    ],
    extras_require={
        'dev': [
            'autopep8 ~= 2.0.0',
            'flake8 ~= 5.0.4',
            'flake8-bugbear ~= 22.10.27',
            'flake8-commas ~= 2.1.0',
            'flake8-docstrings ~= 1.6.0',
            'flake8-isort ~= 5.0.3',
            'flake8-quotes ~= 3.3.1',
            'flake8-unused-arguments ~= 0.0.12',
            'isort ~= 5.10.1',
            'mypy ~= 0.991',
            'pep8-naming ~= 0.13.2',
            'pytest ~= 7.2.0',
            'sphinx ~= 5.3.0',
            'sphinx-autodoc-typehints ~= 1.19.5',
            'sphinx-markdown-builder == 0.5.4',  # pinned to 0.5.4, because 0.5.5 has a formatting bug
            'types-psutil ~= 5.9.5.5',
            'types-setuptools ~= 65.6.0.1',
        ],
    },
)
