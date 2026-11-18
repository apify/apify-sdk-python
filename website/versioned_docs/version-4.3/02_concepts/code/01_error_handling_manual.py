import asyncio
import random

from apify import Actor


async def do_work() -> None:
    # Simulate random outcomes: success or one of two exception types.
    outcome = random.random()

    if outcome < 0.33:
        raise ValueError('Invalid input data encountered')
    if outcome < 0.66:
        raise RuntimeError('Unexpected runtime failure')

    # Simulate successful work
    Actor.log.info('Work completed successfully')


async def main() -> None:
    await Actor.init()
    try:
        await do_work()
    except ValueError as exc:  # Specific error mapping example
        await Actor.fail(exit_code=10, exception=exc)
    except Exception as exc:  # Catch-all for unexpected errors
        await Actor.fail(exit_code=91, exception=exc)
    else:
        await Actor.exit(status_message='Actor completed successfully')


if __name__ == '__main__':
    asyncio.run(main())
