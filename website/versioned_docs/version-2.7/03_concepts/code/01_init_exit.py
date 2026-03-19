from apify import Actor


async def main() -> None:
    await Actor.init()

    try:
        Actor.log.info('Actor input:', await Actor.get_input())
        await Actor.set_value('OUTPUT', 'Hello, world!')
        raise RuntimeError('Ouch!')

    except Exception as exc:
        Actor.log.exception('Error while running Actor')
        await Actor.fail(exit_code=91, exception=exc)

    await Actor.exit()
