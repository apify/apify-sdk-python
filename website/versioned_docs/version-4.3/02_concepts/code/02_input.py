import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        first_number = actor_input.get('firstNumber', 0)
        second_number = actor_input.get('secondNumber', 0)
        Actor.log.info('Sum: %s', first_number + second_number)


if __name__ == '__main__':
    asyncio.run(main())
