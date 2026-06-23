"""
EventBus -- internal publish/subscribe event system for LynkMesh AI.

Enables decoupled communication between components without direct
imports. The bus is synchronous and single-process (no external
message broker dependency).

Events: TaskCreated, TaskClaimed, TaskCompleted, TaskFailed, TaskBlocked
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Event types
# ══════════════════════════════════════════════════════════════════════

class EventType(str, Enum):
    TASK_CREATED = "task_created"
    TASK_CLAIMED = "task_claimed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_BLOCKED = "task_blocked"


@dataclass
class Event:
    """A single event on the bus."""

    event_type: EventType
    task_id: str = ""
    source: str = ""           # Which provider/component emitted this
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = ""         # Auto-generated if empty

    def __post_init__(self) -> None:
        if not self.event_id:
            import uuid
            self.event_id = f"evt_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "task_id": self.task_id,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Event":
        return cls(
            event_id=d.get("event_id", ""),
            event_type=EventType(d["event_type"]) if isinstance(d.get("event_type"), str) else d.get("event_type", EventType.TASK_CREATED),
            task_id=d.get("task_id", ""),
            source=d.get("source", ""),
            data=d.get("data", {}),
            timestamp=d.get("timestamp", ""),
        )


# Type alias for event handlers
EventHandler = Callable[[Event], None]


# ══════════════════════════════════════════════════════════════════════
# EventBus
# ══════════════════════════════════════════════════════════════════════

class EventBus:
    """
    Synchronous, in-process publish/subscribe event bus.

    Components register handlers for specific event types.
    When an event is published, all registered handlers for that
    type are called synchronously in registration order.

    Usage:
        bus = EventBus()

        def on_task_done(event: Event):
            print(f"Task {event.task_id} completed!")

        bus.subscribe(EventType.TASK_COMPLETED, on_task_done)
        bus.publish(Event(EventType.TASK_COMPLETED, task_id="task_001"))
    """

    def __init__(self) -> None:
        self._handlers: Dict[EventType, List[EventHandler]] = {
            et: [] for et in EventType
        }
        self._history: List[Event] = []
        self._max_history: int = 1000

    # ------------------------------------------------------------------
    # Subscribe / Unsubscribe
    # ------------------------------------------------------------------

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Register a handler for an event type.

        Handlers are called in registration order when the event fires.
        The same handler can be registered multiple times (called multiple times).
        """
        self._handlers[event_type].append(handler)
        logger.debug(f"EventBus: subscribed to {event_type.value}")

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> bool:
        """
        Remove a handler from an event type.

        Returns True if the handler was found and removed.
        """
        handlers = self._handlers[event_type]
        if handler in handlers:
            handlers.remove(handler)
            logger.debug(f"EventBus: unsubscribed from {event_type.value}")
            return True
        return False

    def clear_handlers(self, event_type: Optional[EventType] = None) -> None:
        """Remove all handlers, optionally for a specific event type."""
        if event_type:
            self._handlers[event_type].clear()
        else:
            for et in EventType:
                self._handlers[et].clear()

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, event: Event) -> None:
        """
        Publish an event to all registered handlers.

        Handlers are called synchronously. If a handler raises an
        exception, it is logged and the remaining handlers continue.
        """
        self._record(event)
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.error(
                    f"EventBus: handler for {event.event_type.value} "
                    f"failed on event {event.event_id}: {exc}"
                )

    # ------------------------------------------------------------------
    # Convenience publishers
    # ------------------------------------------------------------------

    def task_created(self, task_id: str, source: str = "", **data: Any) -> None:
        """Convenience: publish a TaskCreated event."""
        self.publish(Event(
            event_type=EventType.TASK_CREATED,
            task_id=task_id,
            source=source,
            data=data,
        ))

    def task_claimed(self, task_id: str, source: str = "", **data: Any) -> None:
        """Convenience: publish a TaskClaimed event."""
        self.publish(Event(
            event_type=EventType.TASK_CLAIMED,
            task_id=task_id,
            source=source,
            data=data,
        ))

    def task_completed(self, task_id: str, source: str = "", **data: Any) -> None:
        """Convenience: publish a TaskCompleted event."""
        self.publish(Event(
            event_type=EventType.TASK_COMPLETED,
            task_id=task_id,
            source=source,
            data=data,
        ))

    def task_failed(self, task_id: str, source: str = "", **data: Any) -> None:
        """Convenience: publish a TaskFailed event."""
        self.publish(Event(
            event_type=EventType.TASK_FAILED,
            task_id=task_id,
            source=source,
            data=data,
        ))

    def task_blocked(self, task_id: str, source: str = "", **data: Any) -> None:
        """Convenience: publish a TaskBlocked event."""
        self.publish(Event(
            event_type=EventType.TASK_BLOCKED,
            task_id=task_id,
            source=source,
            data=data,
        ))

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record(self, event: Event) -> None:
        """Record event in history (ring buffer)."""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def history(self, event_type: Optional[EventType] = None, limit: int = 50) -> List[Event]:
        """Get recent events, optionally filtered by type."""
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def subscriber_count(self, event_type: Optional[EventType] = None) -> int:
        """Number of registered handlers."""
        if event_type:
            return len(self._handlers[event_type])
        return sum(len(h) for h in self._handlers.values())

    def history_count(self) -> int:
        """Number of events in history."""
        return len(self._history)


# ══════════════════════════════════════════════════════════════════════
# Module-level singleton (optional — importers may create their own)
# ══════════════════════════════════════════════════════════════════════

_default_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the module-level EventBus singleton."""
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus


def reset_event_bus() -> None:
    """Reset the module-level singleton (useful for testing)."""
    global _default_bus
    _default_bus = None
