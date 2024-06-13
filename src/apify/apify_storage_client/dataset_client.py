from __future__ import annotations

from typing import TYPE_CHECKING

from crawlee.base_storage_client.base_dataset_client import BaseDatasetClient
from crawlee.models import DatasetItemsListPage, DatasetMetadata
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from apify_client.clients import DatasetClientAsync
    from crawlee.types import JSONSerializable


class DatasetClient(BaseDatasetClient):
    """Dataset resource client implementation based on the Apify platform storage."""

    def __init__(self, apify_dataset_client: DatasetClientAsync) -> None:
        self._client = apify_dataset_client

    @override
    async def get(self) -> DatasetMetadata | None:
        result = await self._client.get()
        return DatasetMetadata.model_validate(result) if result else None

    @override
    async def update(
        self,
        *,
        name: str | None = None,
    ) -> DatasetMetadata:
        return DatasetMetadata.model_validate(
            await self._client.update(
                name=name,
            )
        )

    @override
    async def delete(self) -> None:
        await self._client.delete()

    @override
    async def list_items(
        self,
        *,
        offset: int | None = 0,
        limit: int | None = BaseDatasetClient._LIST_ITEMS_LIMIT,
        clean: bool = False,
        desc: bool = False,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        skip_empty: bool = False,
        skip_hidden: bool = False,
        flatten: list[str] | None = None,
        view: str | None = None,
    ) -> DatasetItemsListPage:
        return DatasetItemsListPage.model_validate(
            await self._client.list_items(
                offset=offset,
                limit=limit,
                clean=clean,
                desc=desc,
                fields=fields,
                omit=omit,
                unwind=unwind,
                skip_empty=skip_empty,
                skip_hidden=skip_hidden,
                flatten=flatten,
                view=view,
            )
        )

    @override
    async def iterate_items(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
        clean: bool = False,
        desc: bool = False,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        skip_empty: bool = False,
        skip_hidden: bool = False,
    ) -> AsyncIterator[dict]:
        return self._client.iterate_items(
            offset=offset,
            limit=limit,
            clean=clean,
            desc=desc,
            fields=fields,
            omit=omit,
            unwind=unwind,
            skip_empty=skip_empty,
            skip_hidden=skip_hidden,
        )

    @override
    async def get_items_as_bytes(
        self,
        *,
        item_format: str = 'json',
        offset: int | None = None,
        limit: int | None = None,
        desc: bool = False,
        clean: bool = False,
        bom: bool = False,
        delimiter: str | None = None,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        skip_empty: bool = False,
        skip_header_row: bool = False,
        skip_hidden: bool = False,
        xml_root: str | None = None,
        xml_row: str | None = None,
        flatten: list[str] | None = None,
    ) -> bytes:
        return await self._client.get_items_as_bytes(
            item_format=item_format,
            offset=offset,
            limit=limit,
            desc=desc,
            clean=clean,
            bom=bom,
            delimiter=delimiter,
            fields=fields,
            omit=omit,
            unwind=unwind,
            skip_empty=skip_empty,
            skip_header_row=skip_header_row,
            skip_hidden=skip_hidden,
            xml_root=xml_root,
            xml_row=xml_row,
            flatten=flatten,
        )

    @override
    async def stream_items(
        self,
        *,
        item_format: str = 'json',
        offset: int | None = None,
        limit: int | None = None,
        desc: bool = False,
        clean: bool = False,
        bom: bool = False,
        delimiter: str | None = None,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        skip_empty: bool = False,
        skip_header_row: bool = False,
        skip_hidden: bool = False,
        xml_root: str | None = None,
        xml_row: str | None = None,
    ) -> AsyncIterator[dict]:  # TODO incorrect type
        return self._client.stream_items(
            item_format=item_format,
            offset=offset,
            limit=limit,
            desc=desc,
            clean=clean,
            bom=bom,
            delimiter=delimiter,
            fields=fields,
            omit=omit,
            unwind=unwind,
            skip_empty=skip_empty,
            skip_header_row=skip_header_row,
            skip_hidden=skip_hidden,
            xml_root=xml_root,
            xml_row=xml_row,
        )

    @override
    async def push_items(self, items: JSONSerializable) -> None:
        await self._client.push_items(
            items=items,
        )