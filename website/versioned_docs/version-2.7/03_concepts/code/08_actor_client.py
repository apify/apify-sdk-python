from apify import Actor


async def main() -> None:
    async with Actor:
        # Create a new user client.
        user_client = Actor.apify_client.user('me')

        # Get information about the current user.
        me = await user_client.get()
        Actor.log.info(f'User: {me}')
