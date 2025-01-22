from apify import Actor, Webhook


async def main() -> None:
    async with Actor:
        # Create a webhook that will be triggered when the Actor run fails.
        webhook = Webhook(
            event_types=['ACTOR.RUN.FAILED'],
            request_url='https://example.com/run-failed',
        )

        # Add the webhook to the Actor.
        await Actor.add_webhook(webhook)

        # Raise an error to simulate a failed run.
        raise RuntimeError('I am an error and I know it!')
