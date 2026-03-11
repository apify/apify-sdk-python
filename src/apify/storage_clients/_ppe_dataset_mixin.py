from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from apify._charging import DEFAULT_DATASET_ITEM_EVENT, charging_manager_ctx

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class DatasetClientPpeMixin:
    """A mixin for dataset clients to add support for PPE pricing model and tracking synthetic events."""

    def __init__(self) -> None:
        self.is_default_dataset = False

    def _compute_limit_for_push(self, items_count: int) -> int:
        if self.is_default_dataset and (charging_manager := charging_manager_ctx.get()):
            max_charged_count = charging_manager.calculate_max_event_charge_count_within_limit(
                event_name=DEFAULT_DATASET_ITEM_EVENT
            )
            return min(max_charged_count, items_count) if max_charged_count is not None else items_count
        return items_count

    async def _charge_for_items(self, count_items: int) -> None:
        if self.is_default_dataset and (charging_manager := charging_manager_ctx.get()):
            await charging_manager.charge(
                event_name=DEFAULT_DATASET_ITEM_EVENT,
                count=count_items,
            )

    @asynccontextmanager
    async def _charge_lock(self) -> AsyncIterator[None]:
        """Context manager to acquire the charge lock if PPE charging manager is active."""
        charging_manager = charging_manager_ctx.get()
        if charging_manager:
            async with charging_manager.charge_lock():
                yield
        else:
            yield
