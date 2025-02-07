from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from itemadapter.adapter import ItemAdapter

from apify import Actor

if TYPE_CHECKING:
    from scrapy import Item, Spider

logger = getLogger(__name__)


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
        logger.debug(f'Pushing item={item_dict} produced by spider={spider} to the dataset.')
        await Actor.push_data(item_dict)
        return item
