from __future__ import annotations

from scrapy import Field, Item


class ProductItem(Item):
    name = Field()
    url = Field()
    price = Field()
    description = Field()
