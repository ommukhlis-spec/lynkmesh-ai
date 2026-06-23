"""Tests for EventBus — publish, subscribe, history, convenience methods."""

import pytest

from lynkmesh_ai.events.bus import (
    EventBus, Event, EventType, get_event_bus, reset_event_bus,
)


class TestEvent:
    """Event dataclass."""

    def test_create(self):
        e = Event(EventType.TASK_CREATED, task_id="t1", source="test")
        assert e.event_type == EventType.TASK_CREATED
        assert e.task_id == "t1"
        assert e.event_id.startswith("evt_")

    def test_to_dict(self):
        e = Event(EventType.TASK_DONE if hasattr(EventType, 'TASK_DONE') else EventType.TASK_COMPLETED)
        d = e.to_dict()
        assert "event_type" in d
        assert "event_id" in d

    def test_from_dict(self):
        d = {"event_type": "task_created", "task_id": "t1", "source": "test"}
        e = Event.from_dict(d)
        assert e.event_type == EventType.TASK_CREATED
        assert e.task_id == "t1"


class TestEventBus:
    """Core EventBus behavior."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    def test_subscribe_and_publish(self, bus):
        received = []

        def handler(event):
            received.append(event.task_id)

        bus.subscribe(EventType.TASK_CREATED, handler)
        bus.publish(Event(EventType.TASK_CREATED, task_id="task_001"))
        assert received == ["task_001"]

    def test_unsubscribe(self, bus):
        received = []

        def handler(event):
            received.append(event.task_id)

        bus.subscribe(EventType.TASK_CREATED, handler)
        bus.publish(Event(EventType.TASK_CREATED, task_id="t1"))
        assert bus.unsubscribe(EventType.TASK_CREATED, handler) is True
        bus.publish(Event(EventType.TASK_CREATED, task_id="t2"))
        assert received == ["t1"]  # t2 not received

    def test_unsubscribe_nonexistent(self, bus):
        def handler(e): pass
        assert bus.unsubscribe(EventType.TASK_CREATED, handler) is False

    def test_multiple_handlers(self, bus):
        received = []

        def h1(e): received.append("h1")
        def h2(e): received.append("h2")

        bus.subscribe(EventType.TASK_CREATED, h1)
        bus.subscribe(EventType.TASK_CREATED, h2)
        bus.publish(Event(EventType.TASK_CREATED))
        assert received == ["h1", "h2"]

    def test_handler_exception_does_not_block(self, bus):
        received = []

        def bad_handler(e):
            raise RuntimeError("boom")

        def good_handler(e):
            received.append("ok")

        bus.subscribe(EventType.TASK_CREATED, bad_handler)
        bus.subscribe(EventType.TASK_CREATED, good_handler)
        bus.publish(Event(EventType.TASK_CREATED))  # Should not raise
        assert received == ["ok"]

    def test_clear_handlers(self, bus):
        received = []

        def h(e): received.append(e.task_id)

        bus.subscribe(EventType.TASK_CREATED, h)
        bus.clear_handlers(EventType.TASK_CREATED)
        bus.publish(Event(EventType.TASK_CREATED, task_id="t1"))
        assert received == []

    def test_clear_all_handlers(self, bus):
        received = []

        def h(e): received.append(e.task_id)

        bus.subscribe(EventType.TASK_CREATED, h)
        bus.subscribe(EventType.TASK_COMPLETED, h)
        bus.clear_handlers()
        bus.publish(Event(EventType.TASK_CREATED, task_id="t1"))
        bus.publish(Event(EventType.TASK_COMPLETED, task_id="t2"))
        assert received == []

    def test_subscriber_count(self, bus):
        assert bus.subscriber_count() == 0

        def h(e): pass
        bus.subscribe(EventType.TASK_CREATED, h)
        bus.subscribe(EventType.TASK_COMPLETED, h)
        assert bus.subscriber_count() == 2
        assert bus.subscriber_count(EventType.TASK_CREATED) == 1


class TestConveniencePublishers:
    """Convenience methods emit correct event types."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    def test_task_created(self, bus):
        received = []
        bus.subscribe(EventType.TASK_CREATED, lambda e: received.append(e))
        bus.task_created("t1", source="test", priority="high")
        assert len(received) == 1
        assert received[0].task_id == "t1"
        assert received[0].data["priority"] == "high"

    def test_task_claimed(self, bus):
        received = []
        bus.subscribe(EventType.TASK_CLAIMED, lambda e: received.append(e))
        bus.task_claimed("t1", source="claude")
        assert len(received) == 1

    def test_task_completed(self, bus):
        received = []
        bus.subscribe(EventType.TASK_COMPLETED, lambda e: received.append(e))
        bus.task_completed("t1", source="claude", result="ok")
        assert len(received) == 1

    def test_task_failed(self, bus):
        received = []
        bus.subscribe(EventType.TASK_FAILED, lambda e: received.append(e))
        bus.task_failed("t1", source="claude", error="timeout")
        assert len(received) == 1

    def test_task_blocked(self, bus):
        received = []
        bus.subscribe(EventType.TASK_BLOCKED, lambda e: received.append(e))
        bus.task_blocked("t1", source="claude", reason="waiting")
        assert len(received) == 1


class TestEventHistory:
    """Event history ring buffer."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    def test_history_records_events(self, bus):
        bus.task_created("t1")
        bus.task_created("t2")
        assert bus.history_count() == 2

    def test_history_filtered(self, bus):
        bus.task_created("t1")
        bus.task_completed("t2")
        created = bus.history(EventType.TASK_CREATED)
        assert len(created) == 1
        assert created[0].task_id == "t1"

    def test_history_limit(self, bus):
        for i in range(5):
            bus.task_created(f"t{i}")
        assert len(bus.history(limit=3)) == 3

    def test_clear_history(self, bus):
        bus.task_created("t1")
        bus.clear_history()
        assert bus.history_count() == 0


class TestEventBusSingleton:
    """Module-level singleton."""

    def test_get_event_bus(self):
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_reset_event_bus(self):
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2
