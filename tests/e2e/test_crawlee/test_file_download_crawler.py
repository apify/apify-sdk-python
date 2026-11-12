from __future__ import annotations

from typing import TYPE_CHECKING

from ..._utils import poll_until_condition
from ..actor_source_base.server import file_body
from .conftest import read_actor_source

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction

# The key, size and content type of each file the Actor downloads from the `/files/<size>.<ext>` route.
_EXPECTED_FILES = {
    '1024.pdf': (1024, 'application/pdf'),
    '2048.png': (2048, 'image/png'),
    '5242880.bin': (5242880, 'application/octet-stream'),
}


async def test_file_download_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    """Buffered and streamed downloads store the exact file bytes and content type in the KVS."""
    actor = await make_actor(
        label='crawl-file-download',
        source_files={
            'actor/main.py': read_actor_source('main_file_download_crawler.py'),
        },
    )
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'

    dataset = actor.last_run().dataset()
    items = await poll_until_condition(
        dataset.list_items,
        lambda page: len(page.items) >= len(_EXPECTED_FILES),
        timeout=30,
    )
    items_by_key = {item['key']: item for item in items.items}
    assert set(items_by_key) == set(_EXPECTED_FILES)

    # A 5 MiB body that arrives in one chunk would mean the streamed crawler buffered it.
    assert items_by_key['5242880.bin']['chunk_count'] > 1

    kvs = actor.last_run().key_value_store()
    for key, (size, content_type) in _EXPECTED_FILES.items():
        record = await kvs.get_record_as_bytes(key)
        assert record is not None, f'Missing KVS record: {key}'
        assert record['content_type'].split(';')[0] == content_type, f'{key}: {record["content_type"]}'
        assert record['value'] == file_body(size), f'{key}: the stored bytes differ from the downloaded file'
