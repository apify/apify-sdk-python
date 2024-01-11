from __future__ import annotations

import pytest
from scrapy import Field, Item, Spider

from apify import Actor
from apify.scrapy.pipelines import ActorDatasetPushPipeline


class DummySpider(Spider):
    name = 'dummy_spider'


class DummyItem(Item):
    a = Field()
    b = Field()
    c = Field()


class TitleItem(Item):
    url = Field()
    title = Field()


@pytest.fixture()
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


@pytest.fixture()
def pipeline() -> ActorDatasetPushPipeline:
    """Fixture to create an Actor dataset push pipeline."""
    return ActorDatasetPushPipeline()


@pytest.mark.parametrize(
    ('item', 'item_dict', 'expected_exception'),
    [
        (DummyItem(a='string', b=123, c=False), {'a': 'string', 'b': 123, 'c': False}, None),
        (TitleItem(url='https://example.com', title='Example'), {'url': 'https://example.com', 'title': 'Example'}, None),
        (None, {}, TypeError),
    ],
)
async def test__process_item(
    monkeypatch: pytest.MonkeyPatch,
    pipeline: ActorDatasetPushPipeline,
    spider: Spider,
    item: Item,
    item_dict: dict,
    expected_exception: type[Exception] | None,
) -> None:
    dataset = []

    async def mock_push_data(item: dict) -> None:
        dataset.append(item)

    monkeypatch.setattr(Actor, 'push_data', mock_push_data)

    if expected_exception:
        with pytest.raises(expected_exception):
            await pipeline.process_item(item, spider)

    else:
        output = await pipeline.process_item(item, spider)
        assert output == item
        assert dataset == [item_dict]
