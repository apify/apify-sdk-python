import asyncio

from apify import Actor, Webhook, WebhookEventType


async def main() -> None:
    async with Actor:
        # Create a webhook that will be triggered when the Actor run fails.
        webhook = Webhook(
            event_types=[WebhookEventType.ACTOR_RUN_FAILED],
            request_url='https://example.com/run-failed',
        )

        # Add the webhook to the Actor.
        await Actor.add_webhook(webhook, idempotency_key=Actor.configuration.actor_run_id)

        # Raise an error to simulate a failed run.
        raise RuntimeError('I am an error and I know it!')


if __name__ == '__main__':
    asyncio.run(main())
