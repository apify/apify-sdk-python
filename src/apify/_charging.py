from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from apify._configuration import Configuration


class ChargingManager:
    def __init__(self, configuration: Configuration, client: ApifyClientAsync) -> None:
        pass

    async def init(self) -> None:
        pass

    async def charge(self, event_name: str, count: int = 1) -> ChargeResult:
        pass

    def calculate_max_event_charge_within_limit(self, event_name: str) -> int:
        pass


@dataclass(frozen=True)
class ChargeResult:
    event_charge_limit_reached: bool
    charged_count: int
    chargeable_within_limit: int
