from __future__ import annotations

from typing import TYPE_CHECKING, Any

from typing_extensions import Self, override

from crawlee.storage_clients._file_system import FileSystemDatasetClient

from apify.storage_clients._ppe_dataset_mixin import DatasetClientPpeMixin

if TYPE_CHECKING:
    from crawlee.configuration import Configuration


class ApifyFileSystemDatasetClient(FileSystemDatasetClient, DatasetClientPpeMixin):
    """Apify-specific implementation of the `FileSystemDatasetClient`.

    It extends the functionality of `FileSystemDatasetClient` using `DatasetClientPpeMixin` and updates `push_data` to
    limit and charge for the synthetic `apify-default-dataset-item` event. This is necessary for consistent behavior
    when locally testing the `PAY_PER_EVENT` pricing model.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        FileSystemDatasetClient.__init__(self, *args, **kwargs)
        DatasetClientPpeMixin.__init__(self)

    @override
    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        alias: str | None,
        configuration: Configuration,
    ) -> Self:

        dataset_client = await super().open(
            id=id,
            name=name,
            alias=alias,
            configuration=configuration,
        )

        dataset_client.is_default_dataset = all(v is None for v in (id, name, alias))

        return dataset_client

    @override
    async def push_data(self, data: list[dict[str, Any]] | dict[str, Any]) -> None:
        async with self._lock, self._charge_lock():
            items = data if isinstance(data, list) else [data]
            limit = self._compute_limit_for_push(len(items))

            new_item_count = self._metadata.item_count
            for item in items[:limit]:
                new_item_count += 1
                await self._push_item(item, new_item_count)

            # now update metadata under the same lock
            await self._update_metadata(
                update_accessed_at=True,
                update_modified_at=True,
                new_item_count=new_item_count,
            )

            await self._charge_for_items(limit)
