from typing import Self

from pydantic import BaseModel, model_validator


class ActorInput(BaseModel):
    min_price: int = 0
    max_price: int = 100

    @model_validator(mode='after')
    def _check_range(self) -> Self:
        if self.min_price > self.max_price:
            raise ValueError('min_price must not exceed max_price')
        return self
