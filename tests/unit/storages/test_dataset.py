import pytest

from apify.storages import Dataset, KeyValueStore


@pytest.fixture
async def dataset() -> Dataset:
    return await Dataset.open()


async def test_open() -> None:
    default_dataset = await Dataset.open()
    default_dataset_by_id = await Dataset.open(id=default_dataset._id)

    assert default_dataset is default_dataset_by_id

    dataset_name = 'dummy-name'
    named_dataset = await Dataset.open(name=dataset_name)
    assert default_dataset is not named_dataset

    with pytest.raises(RuntimeError, match='Dataset with id "nonexistent-id" does not exist!'):
        await Dataset.open(id='nonexistent-id')

    # Test that when you try to open a dataset by ID and you use a name of an existing dataset,
    # it doesn't work
    with pytest.raises(RuntimeError, match='Dataset with id "dummy-name" does not exist!'):
        await Dataset.open(id='dummy-name')


async def test_same_references() -> None:
    dataset1 = await Dataset.open()
    dataset2 = await Dataset.open()
    assert dataset1 is dataset2

    dataset_name = 'non-default'
    dataset_named1 = await Dataset.open(name=dataset_name)
    dataset_named2 = await Dataset.open(name=dataset_name)
    assert dataset_named1 is dataset_named2


async def test_drop() -> None:
    dataset1 = await Dataset.open()
    await dataset1.drop()
    dataset2 = await Dataset.open()
    assert dataset1 is not dataset2


async def test_export(dataset: Dataset) -> None:
    expected_csv = 'id,test\r\n0,test\r\n1,test\r\n2,test\r\n'
    expected_json = [{'id': 0, 'test': 'test'}, {'id': 1, 'test': 'test'}, {'id': 2, 'test': 'test'}]
    desired_item_count = 3
    await dataset.push_data([{'id': i, 'test': 'test'} for i in range(desired_item_count)])
    await dataset.export_to_csv('dataset-csv')
    await dataset.export_to_json('dataset-json')
    dataset_csv = await KeyValueStore.get_value('dataset-csv')
    dataset_json = await KeyValueStore.get_value('dataset-json')
    assert dataset_csv == expected_csv
    assert dataset_json == expected_json


async def test_push_data(dataset: Dataset) -> None:
    desired_item_count = 2000
    await dataset.push_data([{'id': i} for i in range(desired_item_count)])
    dataset_info = await dataset.get_info()
    assert dataset_info is not None
    assert dataset_info['itemCount'] == desired_item_count
    list_page = await dataset.get_data(limit=desired_item_count)
    assert list_page.items[0]['id'] == 0
    assert list_page.items[-1]['id'] == desired_item_count - 1


async def test_push_data_empty(dataset: Dataset) -> None:
    await dataset.push_data([])
    dataset_info = await dataset.get_info()
    assert dataset_info is not None
    assert dataset_info['itemCount'] == 0


async def test_push_data_singular(dataset: Dataset) -> None:
    await dataset.push_data({'id': 1})
    dataset_info = await dataset.get_info()
    assert dataset_info is not None
    assert dataset_info['itemCount'] == 1
    list_page = await dataset.get_data()
    assert list_page.items[0]['id'] == 1


async def test_get_data(dataset: Dataset) -> None:  # We don't test everything, that's done in memory storage tests
    desired_item_count = 3
    await dataset.push_data([{'id': i} for i in range(desired_item_count)])
    list_page = await dataset.get_data()
    assert list_page.count == desired_item_count
    assert list_page.desc is False
    assert list_page.offset == 0
    assert list_page.items[0]['id'] == 0
    assert list_page.items[-1]['id'] == desired_item_count - 1


async def test_iterate_items(dataset: Dataset) -> None:
    desired_item_count = 3
    idx = 0
    await dataset.push_data([{'id': i} for i in range(desired_item_count)])
    async for item in dataset.iterate_items():
        assert item['id'] == idx
        idx += 1
