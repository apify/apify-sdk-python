import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Use the KVS to persist a simple reboot counter across restarts.
        kvs = await Actor.open_key_value_store()
        reboot_counter = await kvs.get_value('reboot_counter', 0)

        # Limit the number of reboots to avoid infinite loops.
        if reboot_counter < 3:
            await kvs.set_value('reboot_counter', reboot_counter + 1)
            Actor.log.info(f'Reboot attempt {reboot_counter + 1}/3')
            # Trigger a platform reboot; after restart the code runs from the beginning.
            await Actor.reboot()

        Actor.log.info('Reboot limit reached, finishing run')


if __name__ == '__main__':
    asyncio.run(main())
