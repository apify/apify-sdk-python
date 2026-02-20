from __future__ import annotations

from dataclasses import dataclass

import pytest
from scrapy import Field, Item

from apify import Actor
from apify.scrapy.pipelines import ActorDatasetPushPipeline


class DummyItem(Item):
    a = Field()
    b = Field()
    c = Field()


class TitleItem(Item):
    url = Field()
    title = Field()


@pytest.fixture
def pipeline() -> ActorDatasetPushPipeline:
    """Fixture to create an Actor dataset push pipeline."""
    return ActorDatasetPushPipeline()


@dataclass(frozen=True)
class ItemTestCase:
    item: Item
    item_dict: dict
    expected_exception: type[Exception] | None


@pytest.mark.parametrize(
    'tc',
    [
        ItemTestCase(
            item=DummyItem(a='string', b=123, c=False),
            item_dict={'a': 'string', 'b': 123, 'c': False},
            expected_exception=None,
        ),
        ItemTestCase(
            item=TitleItem(url='https://example.com', title='Example'),
            item_dict={'url': 'https://example.com', 'title': 'Example'},
            expected_exception=None,
        ),
        ItemTestCase(
            item=None,  # ty: ignore[invalid-argument-type]
            item_dict={},
            expected_exception=TypeError,
        ),
    ],
    ids=['dummy_item_with_valid_data', 'title_item_with_valid_data', 'none_item_raises_type_error'],
)
async def test_process_item(
    monkeypatch: pytest.MonkeyPatch,
    pipeline: ActorDatasetPushPipeline,
    tc: ItemTestCase,
) -> None:
    dataset = []

    async def mock_push_data(item: dict) -> None:
        dataset.append(item)

    monkeypatch.setattr(Actor, 'push_data', mock_push_data)

    if tc.expected_exception:
        with pytest.raises(tc.expected_exception):
            await pipeline.process_item(tc.item)

    else:
        output = await pipeline.process_item(tc.item)
        assert output == tc.item
        assert dataset == [tc.item_dict]
