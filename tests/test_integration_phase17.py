"""
Phase 1.7 Integration Tests — StorageAdapter + EventBus + AgentMemory all wired.

Proves:
    1. Event emission: TaskRouter emits events on lifecycle transitions
    2. Event subscription: MemoryCollector receives events automatically
    3. AgentMemory auto-update: ProviderStats, ExecutionRecord, TaskPattern all update
    4. StorageAdapter integration: TaskRouter uses FileStorageAdapter internally
"""

import pytest
import tempfile
from pathlib import Path

from lynkmesh_ai.storage.adapters import FileStorageAdapter
from lynkmesh_ai.events.bus import EventBus, Event, EventType
from lynkmesh_ai.agents.memory import AgentMemory
from lynkmesh_ai.agents.collector import MemoryCollector
from lynkmesh_ai.bridges.task_router import TaskRouter, BridgeTask


# ══════════════════════════════════════════════════════════════════════
# StorageAdapter integration
# ══════════════════════════════════════════════════════════════════════

class TestStorageAdapterIntegration:
    """TaskRouter uses StorageAdapter internally."""

    @pytest.fixture
    def tmp(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_taskrouter_uses_storage_adapter(self, tmp):
        storage = FileStorageAdapter(tmp / "tasks")
        router = TaskRouter(tmp, storage=storage)

        task = router.create_task(title="Storage test", source="manual")
        # Verify storage adapter has the record
        assert storage.exists(task.id)
        rec = storage.get(task.id)
        assert rec.data["title"] == "Storage test"

    def test_taskrouter_loads_from_storage(self, tmp):
        storage = FileStorageAdapter(tmp / "tasks")
        router1 = TaskRouter(tmp, storage=storage)
        router1.create_task(title="Persist me")

        # New router with same storage sees the task
        router2 = TaskRouter(tmp, storage=storage)
        tasks = router2.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].title == "Persist me"

    def test_taskrouter_legacy_fallback(self, tmp):
        """When storage is empty, fall back to legacy JSON files."""
        router = TaskRouter(tmp)  # Default FileStorageAdapter
        task = router.create_task(title="Legacy test")
        # Should exist in storage
        assert router.storage.exists(task.id)
        # Should also have legacy JSON file
        assert router.task_file(task.id).exists()


# ══════════════════════════════════════════════════════════════════════
# Event emission from TaskRouter
# ══════════════════════════════════════════════════════════════════════

class TestEventEmission:
    """TaskRouter emits events on lifecycle transitions."""

    @pytest.fixture
    def setup(self):
        d = tempfile.mkdtemp()
        bus = EventBus()
        router = TaskRouter(Path(d), event_bus=bus)
        return router, bus

    def test_create_emits_task_created(self, setup):
        router, bus = setup
        received = []

        def handler(e):
            received.append(e)

        bus.subscribe(EventType.TASK_CREATED, handler)
        task = router.create_task(title="Event test", source="chatgpt", module="auth")

        assert len(received) == 1
        assert received[0].task_id == task.id
        assert received[0].data["source"] == "chatgpt"
        assert received[0].data["module"] == "auth"

    def test_execute_emits_task_claimed(self, setup):
        router, bus = setup
        received = []

        bus.subscribe(EventType.TASK_CLAIMED, lambda e: received.append(e))
        task = router.create_task(title="Claim me")
        router.move_to_executing(task.id)

        assert len(received) == 1
        assert received[0].task_id == task.id

    def test_done_emits_task_completed(self, setup):
        router, bus = setup
        received = []

        bus.subscribe(EventType.TASK_COMPLETED, lambda e: received.append(e))
        task = router.create_task(title="Complete me")
        router.move_to_done(task.id)

        assert len(received) == 1
        assert received[0].task_id == task.id

    def test_fail_emits_task_failed(self, setup):
        router, bus = setup
        received = []

        bus.subscribe(EventType.TASK_FAILED, lambda e: received.append(e))
        task = router.create_task(title="Fail me")
        router.move_to_failed(task.id, error="Test error")

        assert len(received) == 1
        assert received[0].task_id == task.id
        assert received[0].data["error"] == "Test error"

    def test_block_emits_task_blocked(self, setup):
        router, bus = setup
        received = []

        bus.subscribe(EventType.TASK_BLOCKED, lambda e: received.append(e))
        task = router.create_task(title="Block me")
        router.move_to_blocked(task.id, reason="Waiting")

        assert len(received) == 1
        assert received[0].data["reason"] == "Waiting"

    def test_router_without_bus_does_not_crash(self, setup):
        router, _ = setup
        router2 = TaskRouter(Path(tempfile.mkdtemp()))  # No bus
        task = router2.create_task(title="No bus test")
        router2.move_to_executing(task.id)
        router2.move_to_done(task.id)
        # Should not raise


# ══════════════════════════════════════════════════════════════════════
# MemoryCollector integration
# ══════════════════════════════════════════════════════════════════════

class TestMemoryCollectorIntegration:
    """MemoryCollector subscribes to events and auto-updates AgentMemory."""

    @pytest.fixture
    def setup(self):
        d = tempfile.mkdtemp()
        bus = EventBus()
        memory = AgentMemory(root_dir=Path(d))
        collector = MemoryCollector(bus, memory)
        router = TaskRouter(Path(d), event_bus=bus)
        return router, bus, memory, collector

    def test_completed_task_updates_execution_history(self, setup):
        router, bus, memory, collector = setup
        task = router.create_task(title="Complete me", module="auth.service",
                                  source="chatgpt", assigned_to="claude")
        router.move_to_executing(task.id)
        router.move_to_done(task.id)

        # AgentMemory should have an execution record
        executions = memory.list_executions()
        assert len(executions) == 1
        assert executions[0].status == "done"
        assert executions[0].module == "auth.service"

    def test_completed_task_updates_provider_stats(self, setup):
        router, bus, memory, collector = setup
        task = router.create_task(title="Stats test", module="auth.service",
                                  source="chatgpt", assigned_to="claude")
        router.move_to_executing(task.id)
        router.move_to_done(task.id)

        stats = memory.get_provider_stats("claude", "auth.service")
        assert stats is not None
        assert stats.total_tasks == 1
        assert stats.successes == 1
        assert stats.failures == 0
        assert stats.success_rate == 1.0

    def test_failed_task_updates_provider_stats(self, setup):
        router, bus, memory, collector = setup
        task = router.create_task(title="Fail test", module="payment.processor",
                                  source="chatgpt", assigned_to="claude")
        router.move_to_executing(task.id)
        router.move_to_failed(task.id, error="Something broke")

        stats = memory.get_provider_stats("claude", "payment.processor")
        assert stats is not None
        assert stats.total_tasks == 1
        assert stats.successes == 0
        assert stats.failures == 1
        assert stats.success_rate == 0.0

    def test_task_pattern_learned(self, setup):
        router, bus, memory, collector = setup
        # Simulate 3 successes for auth module
        for i in range(3):
            task = router.create_task(title=f"Task {i}", module="auth.service",
                                      source="chatgpt", assigned_to="claude")
            router.move_to_executing(task.id)
            router.move_to_done(task.id)

        pattern = memory.get_pattern("auth__unknown")
        assert pattern is not None
        assert pattern.success_count == 3
        assert pattern.failure_count == 0

    def test_failure_pattern_learned(self, setup):
        router, bus, memory, collector = setup
        # 2 successes, 1 failure
        for i in range(2):
            task = router.create_task(title=f"OK {i}", module="auth.service",
                                      source="chatgpt")
            router.move_to_executing(task.id)
            router.move_to_done(task.id)
        task = router.create_task(title="Fail", module="auth.service", source="chatgpt")
        router.move_to_executing(task.id)
        router.move_to_failed(task.id, error="Boom")

        pattern = memory.get_pattern("auth__unknown")
        assert pattern.success_count == 2
        assert pattern.failure_count == 1
        assert pattern.success_rate == 2 / 3

    def test_provider_stats_aggregate_across_tasks(self, setup):
        router, bus, memory, collector = setup
        # Mix of successes and failures for same provider+module
        for i in range(5):
            task = router.create_task(title=f"T{i}", module="auth.service",
                                      source="chatgpt", assigned_to="claude")
            router.move_to_executing(task.id)
            if i < 4:
                router.move_to_done(task.id)
            else:
                router.move_to_failed(task.id, error="Failed")

        stats = memory.get_provider_stats("claude", "auth.service")
        assert stats.total_tasks == 5
        assert stats.successes == 4
        assert stats.failures == 1

    def test_collector_stats(self, setup):
        router, bus, memory, collector = setup
        task = router.create_task(title="Stats", module="auth.service",
                                  source="chatgpt", assigned_to="claude")
        router.move_to_executing(task.id)
        router.move_to_done(task.id)

        cs = collector.collector_stats()
        assert cs["executions"] == 1
        assert cs["provider_stats"] == 1
        assert cs["patterns"] >= 0

    def test_shutdown_unsubscribes(self, setup):
        router, bus, memory, collector = setup
        collector.shutdown()
        # After shutdown, events should not update memory
        task = router.create_task(title="After shutdown", module="auth.service",
                                  source="chatgpt", assigned_to="claude")
        router.move_to_executing(task.id)
        router.move_to_done(task.id)

        # No new executions should be recorded
        executions = memory.list_executions()
        assert len(executions) == 0  # Collector was unsubscribed

    def test_blocked_task_recorded(self, setup):
        router, bus, memory, collector = setup
        task = router.create_task(title="Blocked task", module="auth.service",
                                  source="chatgpt", assigned_to="claude")
        router.move_to_executing(task.id)
        router.move_to_blocked(task.id, reason="Needs manual approval")

        executions = memory.list_executions(status="blocked")
        assert len(executions) == 1
        assert "Needs manual approval" in (executions[0].error or "")


# ══════════════════════════════════════════════════════════════════════
# End-to-end: EventBus -> MemoryCollector -> AgentMemory -> query
# ══════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """Full integration: Router emits, Collector records, Memory stores."""

    def test_full_cycle_multiple_modules(self):
        d = tempfile.mkdtemp()
        bus = EventBus()
        memory = AgentMemory(root_dir=Path(d))
        collector = MemoryCollector(bus, memory)
        router = TaskRouter(Path(d), event_bus=bus)

        # Simulate 10 tasks across 3 modules
        modules = ["auth.service", "payment.processor", "notifications.sender"]
        for i in range(10):
            mod = modules[i % 3]
            task = router.create_task(title=f"Task {i}", module=mod,
                                      source="chatgpt", assigned_to="claude")
            router.move_to_executing(task.id)
            if i < 8:
                router.move_to_done(task.id)
            else:
                router.move_to_failed(task.id, error=f"Error {i}")

        # Verify
        assert len(memory.list_executions()) == 10
        assert len(memory.list_provider_stats()) >= 1
        assert memory.get_provider_stats("claude", "auth.service").total_tasks >= 3

        # Event history
        created = bus.history(EventType.TASK_CREATED, limit=100)
        assert len(created) == 10
        completed = bus.history(EventType.TASK_COMPLETED, limit=100)
        assert len(completed) == 8
        failed = bus.history(EventType.TASK_FAILED, limit=100)
        assert len(failed) == 2

        collector.shutdown()
        import shutil
        shutil.rmtree(d, ignore_errors=True)
