from __future__ import annotations

from typing import TYPE_CHECKING, Any

from typing_extensions import Self, override

from crawlee.storage_clients._file_system import FileSystemDatasetClient

from apify._configuration import Configuration as ApifyConfiguration
from apify.storage_clients._ppe_dataset_mixin import DatasetClientPpeMixin

if TYPE_CHECKING:
    from crawlee.configuration import Configuration


class ApifyFileSystemDatasetClient(FileSystemDatasetClient, DatasetClientPpeMixin):
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
        configuration: Configuration | ApifyConfiguration,
    ) -> Self:

        dataset_client = await super().open(
            id=id,
            name=name,
            alias=alias,
            configuration=configuration,
        )

        if isinstance(configuration, ApifyConfiguration) and all(v is None for v in (id, name, alias)):
            dataset_client.is_default_dataset = True

        return dataset_client

    @override
    async def push_data(self, data: list[dict[str, Any]] | dict[str, Any]) -> None:
        items = data if isinstance(data, list) else [data]
        limit = await self._calculate_limit_for_push(len(items))
        await super().push_data(items[:limit])
        await self._charge_for_items(limit)
