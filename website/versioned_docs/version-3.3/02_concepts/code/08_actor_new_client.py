import asyncio

from apify import Actor

TOKEN = 'ANOTHER_USERS_TOKEN'


async def main() -> None:
    async with Actor:
        # Create a new user client with a custom token.
        apify_client = Actor.new_client(token=TOKEN, max_retries=2)
        user_client = apify_client.user('me')

        # Get information about the another user.
        them = await user_client.get()
        Actor.log.info(f'Another user: {them}')


if __name__ == '__main__':
    asyncio.run(main())
