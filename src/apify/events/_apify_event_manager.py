from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Annotated, Self

import websockets.asyncio.client
import websockets.exceptions
from pydantic import Discriminator, TypeAdapter
from typing_extensions import Unpack, override

from crawlee.events import EventManager
from crawlee.events._types import Event, EventPersistStateData

from apify._utils import docs_group
from apify.events._types import DeprecatedEvent, EventMessage, SystemInfoEventData, UnknownEvent
from apify.log import logger

if TYPE_CHECKING:
    from types import TracebackType

    from crawlee.events._event_manager import EventManagerOptions

    from apify._configuration import Configuration


event_data_adapter = TypeAdapter[EventMessage | DeprecatedEvent | UnknownEvent](
    Annotated[EventMessage, Discriminator('name')] | DeprecatedEvent | UnknownEvent
)


@docs_group('Event managers')
class ApifyEventManager(EventManager):
    """Event manager for the Apify platform.

    This class extends Crawlee's `EventManager` to provide Apify-specific functionality, including websocket
    connectivity to the Apify platform for receiving platform events.

    The event manager handles:
    - Registration and emission of events and their listeners.
    - Websocket connection to Apify platform events.
    - Processing and validation of platform messages.
    - Automatic event forwarding from the platform to local event listeners.

    This class should not be used directly. Use the `Actor.on` and `Actor.off` methods to interact
    with the event system.
    """

    def __init__(self, configuration: Configuration, **kwargs: Unpack[EventManagerOptions]) -> None:
        """Initialize a new instance.

        Args:
            configuration: The Actor configuration for the event manager.
            **kwargs: Additional event manager options passed to the parent class.
        """
        super().__init__(**kwargs)

        self._configuration = configuration
        """The Actor configuration for the event manager."""

        self._platform_events_websocket: websockets.asyncio.client.ClientConnection | None = None
        """WebSocket connection to the platform events."""

        self._process_platform_messages_task: asyncio.Task | None = None
        """Task for processing messages from the platform websocket."""

        self._connected_to_platform_websocket: asyncio.Future[bool] | None = None
        """Future that resolves when the connection to the platform websocket is established."""

    @override
    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self._connected_to_platform_websocket = asyncio.Future()

        # Run tasks but don't await them
        if self._configuration.actor_events_ws_url:
            self._process_platform_messages_task = asyncio.create_task(
                self._process_platform_messages(self._configuration.actor_events_ws_url)
            )
            is_connected = await self._connected_to_platform_websocket
            if not is_connected:
                # Exit the already-entered parent so the recurring persist state task does not leak.
                await self.__aexit__(None, None, None)
                raise RuntimeError('Error connecting to platform events websocket!')
        else:
            logger.debug('APIFY_ACTOR_EVENTS_WS_URL env var not set, no events from Apify platform will be emitted.')

        return self

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        # Cancel the task before closing the websocket so that the closed connection is not treated as a drop
        # and followed by a reconnect attempt.
        if self._process_platform_messages_task and not self._process_platform_messages_task.done():
            self._process_platform_messages_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._process_platform_messages_task

        if self._platform_events_websocket:
            await self._platform_events_websocket.close()

        await super().__aexit__(exc_type, exc_value, exc_traceback)

    def _process_connection_exception(self, exc: Exception) -> Exception | None:
        """Decide whether a failed connection attempt to the platform websocket should be retried.

        Before the first successful connection, every error is fatal so that `__aenter__` fails fast. After that,
        the default `websockets` behavior decides which errors are transient and retried with exponential backoff.
        """
        if self._connected_to_platform_websocket and self._connected_to_platform_websocket.done():
            return websockets.asyncio.client.process_exception(exc)
        return exc

    async def _process_platform_messages(self, ws_url: str) -> None:
        try:
            # Used as an async iterator, `connect` reconnects with exponential backoff whenever a connection
            # attempt fails with a transient error.
            async for websocket in websockets.asyncio.client.connect(
                ws_url, process_exception=self._process_connection_exception
            ):
                self._platform_events_websocket = websocket
                if self._connected_to_platform_websocket and not self._connected_to_platform_websocket.done():
                    self._connected_to_platform_websocket.set_result(True)
                else:
                    logger.info('Reconnected to the platform events websocket.')

                try:
                    async for message in websocket:
                        try:
                            parsed_message = event_data_adapter.validate_json(message)

                            if isinstance(parsed_message, DeprecatedEvent):
                                continue

                            if isinstance(parsed_message, UnknownEvent):
                                logger.info(
                                    f'Unknown message received: event_name={parsed_message.name}, '
                                    f'event_data={parsed_message.data}'
                                )
                                continue

                            self.emit(
                                event=parsed_message.name,
                                event_data=parsed_message.data
                                if not isinstance(parsed_message.data, SystemInfoEventData)
                                else parsed_message.data.to_crawlee_format(self._configuration.dedicated_cpus or 1),
                            )

                            if parsed_message.name == Event.MIGRATING:
                                await self._emit_persist_state_event_rec_task.stop()
                                self.emit(
                                    event=Event.PERSIST_STATE, event_data=EventPersistStateData(is_migrating=True)
                                )
                        except Exception:
                            logger.exception('Cannot parse Actor event', extra={'raw_message': message})
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(
                        f'Connection to platform events websocket was lost '
                        f'(code={websocket.close_code}, reason={websocket.close_reason!r}), reconnecting...'
                    )
                else:
                    logger.info(
                        f'Connection to platform events websocket was closed '
                        f'(code={websocket.close_code}, reason={websocket.close_reason!r}), reconnecting...'
                    )
        except Exception:
            logger.exception('Error in websocket connection')
            if self._connected_to_platform_websocket is not None and not self._connected_to_platform_websocket.done():
                self._connected_to_platform_websocket.set_result(False)
