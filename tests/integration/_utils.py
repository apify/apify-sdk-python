from __future__ import annotations

from crawlee._utils.crypto import crypto_random_object_id


def read_file(file_path: str) -> str:
    """Read the content of a file and return it as a string."""
    with open(file_path, encoding='utf-8') as file:
        return file.read()


def generate_unique_resource_name(label: str) -> str:
    """Generates a unique resource name, which will contain the given label."""
    label = label.replace('_', '-')
    return f'python-sdk-tests-{label}-generated-{crypto_random_object_id(8)}'
