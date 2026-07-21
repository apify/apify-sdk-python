from __future__ import annotations

import asyncio
import contextlib
import time
from logging import getLogger
from typing import TYPE_CHECKING, Annotated, Self

import websockets.asyncio.client
import websockets.client
import websockets.exceptions
from pydantic import Discriminator, TypeAdapter
from typing_extensions import Unpack, override
from websockets.frames import CloseCode

from crawlee.events import EventManager
from crawlee.events._types import Event, EventPersistStateData

from apify._utils import docs_group
from apify.events._types import DeprecatedEvent, EventMessage, SystemInfoEventData, UnknownEvent

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import TracebackType

    from crawlee.events._event_manager import EventManagerOptions

    from apify._configuration import Configuration


logger = getLogger(__name__)

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

    _NON_RETRYABLE_CLOSE_CODES = frozenset(
        {
            CloseCode.PROTOCOL_ERROR,
            CloseCode.UNSUPPORTED_DATA,
            CloseCode.INVALID_DATA,
            CloseCode.POLICY_VIOLATION,
            CloseCode.MANDATORY_EXTENSION,
        }
    )
    """WebSocket close codes for a permanent condition, on which the connection is not re-established.

    The platform sends `POLICY_VIOLATION` (1008) for an unknown/missing run ID or an exceeded per-run
    connection limit. The rest are protocol, data, or mandatory-extension failures that reconnecting
    cannot resolve.
    """

    _HEALTHY_CONNECTION_MIN_DURATION = 1.0
    """Seconds a connection must stay open to count as healthy, after which a drop reconnects without backoff."""

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

        # The parent ref-counts nested contexts (e.g. a crawler entering the same event manager). Only the
        # outermost enter (0 -> 1) may start the platform websocket machinery; a nested enter must reuse the
        # existing connection rather than open a second one.
        if self._active_ref_count > 1:
            return self

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
        # Mirror the parent's ref counting: only the outermost exit (1 -> 0) tears down the platform websocket
        # machinery. A nested exit must leave the connection and its processing task intact for the still-active
        # outer context.
        if self._active_ref_count == 1:
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
        # The `websockets` reconnect iterator only backs off on failed connection *attempts*, not on a connection
        # that opens and is then closed. Track our own backoff here so a server that keeps accepting and immediately
        # closing is not hammered; it is reset after a healthy connection so a healthy drop reconnects immediately.
        backoff_delays: Generator[float] | None = None

        try:
            # Used as an async iterator, `connect` reconnects with exponential backoff on failed connection attempts.
            async for websocket in websockets.asyncio.client.connect(
                ws_url, process_exception=self._process_connection_exception
            ):
                self._platform_events_websocket = websocket
                if self._connected_to_platform_websocket and not self._connected_to_platform_websocket.done():
                    self._connected_to_platform_websocket.set_result(True)
                else:
                    logger.info('Reconnected to the platform events websocket.')

                connection_opened_at = time.monotonic()
                connection_lost = await self._consume_messages(websocket)

                if not self._should_reconnect_after_close(websocket, connection_lost=connection_lost):
                    break

                # Reconnect a healthy connection immediately; back off only on repeated rapid drops. The first
                # rapid drop reconnects once without delay (it only primes the backoff generator), and each
                # subsequent consecutive rapid drop then sleeps for the next backoff interval. A healthy
                # connection resets the generator, so the next rapid drop again gets that one free retry.
                if time.monotonic() - connection_opened_at >= self._HEALTHY_CONNECTION_MIN_DURATION:
                    backoff_delays = None
                elif backoff_delays is None:
                    backoff_delays = websockets.client.backoff()
                else:
                    await asyncio.sleep(next(backoff_delays))
        except Exception:
            logger.exception('Error in websocket connection')
            if self._connected_to_platform_websocket is not None and not self._connected_to_platform_websocket.done():
                self._connected_to_platform_websocket.set_result(False)

    async def _consume_messages(self, websocket: websockets.asyncio.client.ClientConnection) -> bool:
        """Handle platform messages until the connection closes; return whether it was lost vs. closed cleanly."""
        try:
            async for message in websocket:
                await self._handle_platform_message(message)
        except websockets.exceptions.ConnectionClosed:
            return True
        return False

    async def _handle_platform_message(self, message: str | bytes) -> None:
        """Parse a single platform message and emit the matching local event."""
        try:
            parsed_message = event_data_adapter.validate_json(message)

            if isinstance(parsed_message, DeprecatedEvent):
                return

            if isinstance(parsed_message, UnknownEvent):
                logger.debug(
                    f'Unknown message received: event_name={parsed_message.name}, event_data={parsed_message.data}'
                )
                return

            self.emit(
                event=parsed_message.name,
                event_data=parsed_message.data
                if not isinstance(parsed_message.data, SystemInfoEventData)
                else parsed_message.data.to_crawlee_format(self._configuration.dedicated_cpus or 1),
            )

            if parsed_message.name == Event.MIGRATING:
                await self._emit_persist_state_event_rec_task.stop()
                self.emit(event=Event.PERSIST_STATE, event_data=EventPersistStateData(is_migrating=True))
        except Exception:
            logger.exception('Cannot parse Actor event', extra={'raw_message': message})

    def _should_reconnect_after_close(
        self,
        websocket: websockets.asyncio.client.ClientConnection,
        *,
        connection_lost: bool,
    ) -> bool:
        """Log the websocket close and report whether to reconnect (`False` on a non-retryable close code)."""
        if websocket.close_code in self._NON_RETRYABLE_CLOSE_CODES:
            logger.error(
                f'Connection to platform events websocket was closed with a non-retryable code '
                f'(code={websocket.close_code}, reason={websocket.close_reason!r}); not reconnecting. '
                f'No further platform events will be received for the rest of this run, so migration and '
                f'abort handling (e.g. persisting state before a migration) is now disabled.'
            )
            return False

        if connection_lost:
            logger.warning(
                f'Connection to platform events websocket was lost '
                f'(code={websocket.close_code}, reason={websocket.close_reason!r}), reconnecting...'
            )
        else:
            logger.info(
                f'Connection to platform events websocket was closed '
                f'(code={websocket.close_code}, reason={websocket.close_reason!r}), reconnecting...'
            )
        return True
