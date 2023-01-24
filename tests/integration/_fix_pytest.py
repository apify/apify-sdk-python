import asyncio
from typing import Iterator

import pytest


# This overrides the default pytest-asyncio event loop fixture,
# because that one has some weird bug that raises `RuntimeError: Event loop is closed`
# when you run multiple integration tests at once.
# I have no idea why, it would be nice to find the root cause.
@pytest.fixture(scope='session')
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()
