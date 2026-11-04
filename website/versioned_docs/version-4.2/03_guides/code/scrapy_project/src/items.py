from __future__ import annotations

from scrapy import Field, Item


class TitleItem(Item):
    """Represents a title item scraped from a web page."""

    url = Field()
    title = Field()
