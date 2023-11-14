from apify._crypto import crypto_random_object_id


def generate_unique_resource_name(label: str) -> str:
    """Generates a unique resource name, which will contain the given label."""
    label = label.replace('_', '-')
    return f'python-sdk-tests-{label}-generated-{crypto_random_object_id(8)}'
