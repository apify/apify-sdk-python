from typing import Dict, List, Optional, Type

from apify_client._utils import ListPage

from ..._utils import ignore_docs
from .base_resource_collection_client import BaseResourceCollectionClient
from .dataset import DatasetClient


@ignore_docs
class DatasetCollectionClient(BaseResourceCollectionClient):
    """Sub-client for manipulating datasets."""

    def _get_storage_client_cache(self) -> List[DatasetClient]:
        return self._memory_storage_client._datasets_handled

    def _get_resource_client_class(self) -> Type[DatasetClient]:
        return DatasetClient

    async def list(self) -> ListPage:
        """List the available datasets.

        Returns:
            ListPage: The list of available datasets matching the specified filters.
        """
        return await super().list()

    async def get_or_create(
        self,
        *,
        name: Optional[str] = None,
        schema: Optional[Dict] = None,
        _id: Optional[str] = None,
    ) -> Dict:
        """Retrieve a named dataset, or create a new one when it doesn't exist.

        Args:
            name (str, optional): The name of the dataset to retrieve or create.
            schema (Dict, optional): The schema of the dataset

        Returns:
            dict: The retrieved or newly-created dataset.
        """
        return await super().get_or_create(name=name, schema=schema, _id=_id)
