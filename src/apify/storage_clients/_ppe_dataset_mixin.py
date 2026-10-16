from __future__ import annotations

from apify._charging import DEFAULT_DATASET_ITEM_EVENT, charging_manager_ctx


class DatasetClientPpeMixin:
    """A mixin for dataset clients to add support for PPE pricing model and tracking synthetic events."""

    def __init__(self) -> None:
        self.is_default_dataset = False

    def _compute_limit_for_push(self, items_count: int) -> int:
        if self.is_default_dataset and (charging_manager := charging_manager_ctx.get()):
            # The synthetic event is the only one charged per item, so it is priced as the explicit event.
            return charging_manager.compute_push_data_limit(
                items_count,
                DEFAULT_DATASET_ITEM_EVENT,
                is_default_dataset=False,
            )
        return items_count

    async def _charge_for_items(self, count_items: int) -> None:
        if self.is_default_dataset and (charging_manager := charging_manager_ctx.get()):
            await charging_manager.charge(
                event_name=DEFAULT_DATASET_ITEM_EVENT,
                count=count_items,
            )
