import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Check the dataset because there might already be items
        # if the run migrated or was restarted
        default_dataset = await Actor.open_dataset()
        metadata = await default_dataset.get_metadata()
        charged_items = metadata.item_count

        # highlight-start
        if Actor.get_charging_manager().get_pricing_info().is_pay_per_event:
            # highlight-end
            await Actor.push_data({'hello': 'world'}, 'dataset-item')
        elif charged_items < (Actor.configuration.max_paid_dataset_items or 0):
            await Actor.push_data({'hello': 'world'})
            charged_items += 1


if __name__ == '__main__':
    asyncio.run(main())
