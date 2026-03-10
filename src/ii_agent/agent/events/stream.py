"""Event stream for publishing and subscribing to realtime events."""

from typing import Optional
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Set

from ii_agent.agent.events.models import RealtimeEvent
from ii_agent.agent.subscribers.subscriber import EventSubscriber


class EventStream(ABC):
    """Abstract base class for event streaming."""

    @abstractmethod
    async def publish(self, event: RealtimeEvent) -> None:
        """Add an event to the stream."""
        pass

    @abstractmethod
    async def subscribe(self, subscriber: EventSubscriber) -> None:
        """Subscribe to events in the stream."""
        pass

    @abstractmethod
    async def unsubscribe(self, subscriber: EventSubscriber) -> None:
        """Unsubscribe from events in the stream."""
        pass

    @abstractmethod
    async def clear_subscribers(self) -> None:
        """Unsubscribe from events in the stream."""
        pass

    @abstractmethod
    def register_hook(self, hook) -> None:
        """Register an event hook."""
        pass

    @abstractmethod
    def unregister_hook(self, hook) -> None:
        """Unregister an event hook."""
        pass

    @abstractmethod
    def clear_hooks(self) -> None:
        """Remove all registered hooks."""
        pass


class AsyncEventStream(EventStream):
    """Async implementation of EventStream that manages event subscribers."""

    def __init__(self, logger: logging.Logger | None = None):
        # TODO: using event name instead of class instance for subscriber management. can cause duplication
        self._subscribers: Set[EventSubscriber] = set()
        self._lock = asyncio.Lock()
        self._logger = logger or logging.getLogger(__name__)
        self._hook_registry = EventHookRegistry()

    async def publish(self, event: RealtimeEvent) -> None:
        """Add an event to the stream and notify all subscribers."""
        # Process event through hooks first
        try:
            processed_event = await self._hook_registry.process_event(event)
        except Exception as e:
            self._logger.error(f"Error processing event hooks: {e}")
            processed_event = event  # Fall back to original event

        # If event was filtered out by hooks, don't propagate
        if processed_event is None:
            return

        async with self._lock:
            subscribers = self._subscribers.copy()

        # Notify all subscribers
        for subscriber in subscribers:
            try:
                # Call the handle_event method on the subscriber
                asyncio.create_task(subscriber.handle_event(processed_event))
            except Exception as e:
                self._logger.error(
                    f"Error in event subscriber {type(subscriber).__name__}: {e}"
                )

    async def subscribe(self, subscriber: EventSubscriber) -> None:
        """Subscribe to events in the stream."""
        async with self._lock:
            self._subscribers.add(subscriber)

    async def unsubscribe(self, subscriber: EventSubscriber) -> None:
        """Unsubscribe from events in the stream."""
        async with self._lock:
            self._subscribers.discard(subscriber)

    async def clear_subscribers(self) -> None:
        """Remove all subscribers."""
        async with self._lock:
            self._subscribers.clear()

    async def get_subscribers(self) -> Set[EventSubscriber]:
        """Get a copy of all current subscribers."""
        async with self._lock:
            return self._subscribers.copy()

    async def get_subscriber_count(self) -> int:
        """Get the number of active subscribers."""
        async with self._lock:
            return len(self._subscribers)

    async def has_subscriber(self, subscriber: EventSubscriber) -> bool:
        """Check if a specific subscriber is registered."""
        async with self._lock:
            return subscriber in self._subscribers

    def register_hook(self, hook) -> None:
        """Register an event hook."""
        self._hook_registry.register_hook(hook)

    def unregister_hook(self, hook) -> None:
        """Unregister an event hook."""
        self._hook_registry.unregister_hook(hook)

    def clear_hooks(self) -> None:
        """Remove all registered hooks."""
        self._hook_registry.clear_hooks()

class EventHook(ABC):
    """Abstract base class for event hooks that can modify events before propagation."""

    @abstractmethod
    async def process_event(self, event: RealtimeEvent) -> Optional[RealtimeEvent]:
        """
        Process an event before it's propagated to subscribers.

        Args:
            event: The original event

        Returns:
            Modified event or None to filter out the event entirely
        """
        pass

    @abstractmethod
    def should_process(self, event: RealtimeEvent) -> bool:
        """
        Determine if this hook should process the given event.

        Args:
            event: The event to check

        Returns:
            True if this hook should process the event, False otherwise
        """
        pass


class EventHookRegistry:
    """Registry for managing event hooks."""

    def __init__(self):
        self._hooks: list[EventHook] = []

    def register_hook(self, hook: EventHook) -> None:
        """Register an event hook."""
        self._hooks.append(hook)

    def unregister_hook(self, hook: EventHook) -> None:
        """Unregister an event hook."""
        if hook in self._hooks:
            self._hooks.remove(hook)

    async def process_event(self, event: RealtimeEvent) -> Optional[RealtimeEvent]:
        """
        Process an event through all registered hooks.

        Args:
            event: The original event

        Returns:
            Processed event or None if filtered out
        """
        current_event = event

        for hook in self._hooks:
            if hook.should_process(current_event):
                processed_event = await hook.process_event(current_event)
                if processed_event is None:
                    # Hook filtered out the event
                    return None
                current_event = processed_event

        return current_event

    def clear_hooks(self) -> None:
        """Remove all registered hooks."""
        self._hooks.clear()