from datetime import timedelta

from apify import Actor, Configuration, Event


async def main() -> None:
    global_config = Configuration.get_global_configuration()
    global_config.persist_state_interval = timedelta(seconds=10)

    async with Actor:
        # Define a handler that will be called for every persist state event.
        async def save_state() -> None:
            await Actor.set_value('STATE', 'Hello, world!')

        # The save_state handler will be called every 10 seconds now.
        Actor.on(Event.PERSIST_STATE, save_state)
