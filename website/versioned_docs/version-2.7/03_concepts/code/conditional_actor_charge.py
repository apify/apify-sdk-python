from apify import Actor


async def main() -> None:
    async with Actor:
        # Check the dataset because there might already be items
        # if the run migrated or was restarted
        default_dataset = await Actor.open_dataset()
        dataset_info = await default_dataset.get_info()
        charged_items = dataset_info.item_count if dataset_info else 0

        # highlight-start
        if Actor.get_charging_manager().get_pricing_info().is_pay_per_event:
            # highlight-end
            await Actor.push_data({'hello': 'world'}, 'dataset-item')
        elif charged_items < (Actor.config.max_paid_dataset_items or 0):
            await Actor.push_data({'hello': 'world'})
            charged_items += 1
