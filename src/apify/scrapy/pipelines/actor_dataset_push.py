from __future__ import annotations

from typing import TYPE_CHECKING

from itemadapter.adapter import ItemAdapter

try:
    if TYPE_CHECKING:
        from scrapy import Item, Spider
except ImportError as exc:
    raise ImportError(
        'To use this module, you need to install the "scrapy" extra. Run "pip install apify[scrapy]".',
    ) from exc

from apify import Actor


class ActorDatasetPushPipeline:
    """A Scrapy pipeline for pushing items to an Actor's default dataset.

    This pipeline is designed to be enabled only when the Scrapy project is run as an Actor.
    """

    async def process_item(
        self,
        item: Item,
        spider: Spider,
    ) -> Item:
        """Pushes the provided Scrapy item to the Actor's default dataset."""
        item_dict = ItemAdapter(item).asdict()
        Actor.log.debug(f'Pushing item={item_dict} produced by spider={spider} to the dataset.')
        await Actor.push_data(item_dict)
        return item
