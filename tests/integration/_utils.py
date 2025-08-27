from __future__ import annotations

from crawlee._utils.crypto import crypto_random_object_id


def generate_unique_resource_name(label: str) -> str:
    """Generates a unique resource name, which will contain the given label."""
    name_template = 'python-sdk-tests-{}-generated-{}'
    template_length = len(name_template.format('', ''))
    api_name_limit = 63
    generated_random_id_length = 8
    label_length_limit = api_name_limit - template_length - generated_random_id_length

    label = label.replace('_', '-')
    assert len(label) <= label_length_limit, f'Max label length is {label_length_limit}, but got {len(label)}'

    return name_template.format(label, crypto_random_object_id(generated_random_id_length))
