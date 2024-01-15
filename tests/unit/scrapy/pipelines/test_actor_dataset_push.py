from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class TestCase:
    item: Item
    item_dict: dict
    expected_exception: type[Exception] | None


test_cases = [
    TestCase(
        item=DummyItem(a='string', b=123, c=False),
        item_dict={'a': 'string', 'b': 123, 'c': False},
        expected_exception=None,
    ),
    TestCase(
        item=TitleItem(url='https://example.com', title='Example'),
        item_dict={'url': 'https://example.com', 'title': 'Example'},
        expected_exception=None,
    ),
    TestCase(
        item=None,
        item_dict={},
        expected_exception=TypeError,
    ),
]


@pytest.mark.parametrize('tc', test_cases)
async def test__process_item(
    monkeypatch: pytest.MonkeyPatch,
    pipeline: ActorDatasetPushPipeline,
    spider: Spider,
    tc: TestCase,
) -> None:
    dataset = []

    async def mock_push_data(item: dict) -> None:
        dataset.append(item)

    monkeypatch.setattr(Actor, 'push_data', mock_push_data)

    if tc.expected_exception:
        with pytest.raises(tc.expected_exception):
            await pipeline.process_item(tc.item, spider)

    else:
        output = await pipeline.process_item(tc.item, spider)
        assert output == tc.item
        assert dataset == [tc.item_dict]
