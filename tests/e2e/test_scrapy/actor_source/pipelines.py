from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapy import Item, Spider


class PriceCleanerPipeline:
    def process_item(
        self,
        item: Item,
        _: Spider,
    ) -> Item:
        if 'price' in item and isinstance(item['price'], str):
            item['price'] = item['price'].lstrip('$')
        return item
