"""
Tests for ProviderRegistry — provider discovery, registration, routing.

Run: python -m pytest tests/test_provider_registry.py -v
"""

import pytest

from lynkmesh_ai.bridges.base import (
    AgentProvider,
    ProviderCapabilities,
    ProviderRole,
    TaskStatus,
    TaskResult,
)
from lynkmesh_ai.bridges.registry import ProviderRegistry


# ---------------------------------------------------------------------------
# Stub provider for testing
# ---------------------------------------------------------------------------

class _StubProvider(AgentProvider):
    """Minimal provider implementation for registry tests."""

    def __init__(self, name="stub", role=ProviderRole.CONSUMER):
        super().__init__(name=name)
        self._role = role
        self._tasks = {}

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name=self.name,
            role=self._role,
            default_model="stub-v1",
            description="Stub provider for testing",
        )

    def submit_task(self, task, context=None) -> str:
        tid = f"stub_{len(self._tasks)}"
        self._tasks[tid] = {"task": task, "status": TaskStatus.PENDING}
        return tid

    def get_status(self, task_id: str) -> TaskStatus:
        if task_id not in self._tasks:
            raise KeyError(task_id)
        return self._tasks[task_id]["status"]

    def get_result(self, task_id: str) -> TaskResult:
        if task_id not in self._tasks:
            raise KeyError(task_id)
        status = self._tasks[task_id]["status"]
        if status not in (TaskStatus.DONE, TaskStatus.FAILED):
            raise RuntimeError(f"Task {task_id} not complete")
        return TaskResult(task_id=task_id, status=status, success=(status == TaskStatus.DONE),
                          provider_name=self.name)

    def cancel_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = TaskStatus.CANCELLED
            return True
        return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    """ProviderRegistry registration, lookup, and discovery."""

    def test_empty_registry(self):
        reg = ProviderRegistry()
        assert reg.count() == 0
        assert reg.list() == []
        assert reg.find_consumer() is None
        assert reg.find_producer() is None

    def test_register_and_get(self):
        reg = ProviderRegistry()
        p = _StubProvider(name="test-provider")
        reg.register("test-provider", p)
        assert reg.count() == 1
        assert "test-provider" in reg
        assert reg.get("test-provider") is p
        assert reg["test-provider"] is p

    def test_register_duplicate(self):
        reg = ProviderRegistry()
        p1 = _StubProvider(name="dup")
        p2 = _StubProvider(name="dup")
        reg.register("dup", p1)
        reg.register("dup", p2)  # Should warn but not crash
        assert reg.count() == 1
        assert reg.get("dup") is p2  # Replaced

    def test_unregister(self):
        reg = ProviderRegistry()
        p = _StubProvider(name="temp")
        reg.register("temp", p)
        assert reg.unregister("temp") is True
        assert reg.count() == 0
        assert reg.unregister("nonexistent") is False

    def test_get_missing_returns_none(self):
        reg = ProviderRegistry()
        assert reg.get("nonexistent") is None

    def test_get_missing_raises_keyerror(self):
        reg = ProviderRegistry()
        with pytest.raises(KeyError):
            _ = reg["nonexistent"]

    def test_list_sorted(self):
        reg = ProviderRegistry()
        reg.register("c", _StubProvider(name="c"))
        reg.register("a", _StubProvider(name="a"))
        reg.register("b", _StubProvider(name="b"))
        assert reg.list() == ["a", "b", "c"]

    def test_list_by_role(self):
        reg = ProviderRegistry()
        reg.register("consumer", _StubProvider(name="consumer", role=ProviderRole.CONSUMER))
        reg.register("producer", _StubProvider(name="producer", role=ProviderRole.PRODUCER))
        reg.register("both", _StubProvider(name="both", role=ProviderRole.BOTH))

        consumers = reg.list_by_role(ProviderRole.CONSUMER)
        producers = reg.list_by_role(ProviderRole.PRODUCER)
        boths = reg.list_by_role(ProviderRole.BOTH)

        assert "consumer" in consumers
        assert "both" in consumers      # BOTH includes CONSUMER
        assert "producer" in producers
        assert "both" in producers      # BOTH includes PRODUCER
        assert "both" in boths

    def test_find_consumer(self):
        reg = ProviderRegistry()
        reg.register("prod", _StubProvider(name="prod", role=ProviderRole.PRODUCER))
        assert reg.find_consumer() is None
        reg.register("cons", _StubProvider(name="cons", role=ProviderRole.CONSUMER))
        assert reg.find_consumer().name == "cons"

    def test_find_producer(self):
        reg = ProviderRegistry()
        reg.register("cons", _StubProvider(name="cons", role=ProviderRole.CONSUMER))
        assert reg.find_producer() is None
        reg.register("prod", _StubProvider(name="prod", role=ProviderRole.PRODUCER))
        assert reg.find_producer().name == "prod"

    def test_route_task_preferred(self):
        reg = ProviderRegistry()
        reg.register("a", _StubProvider(name="a", role=ProviderRole.CONSUMER))
        reg.register("b", _StubProvider(name="b", role=ProviderRole.CONSUMER))
        target = reg.route_task({"title": "test"}, preferred_provider="b")
        assert target == "b"

    def test_route_task_fallback(self):
        reg = ProviderRegistry()
        reg.register("a", _StubProvider(name="a", role=ProviderRole.CONSUMER))
        target = reg.route_task({"title": "test"})
        assert target == "a"

    def test_route_task_no_consumer(self):
        reg = ProviderRegistry()
        reg.register("p", _StubProvider(name="p", role=ProviderRole.PRODUCER))
        target = reg.route_task({"title": "test"})
        assert target is None

    def test_get_capabilities(self):
        reg = ProviderRegistry()
        reg.register("test", _StubProvider(name="test"))
        caps = reg.get_capabilities("test")
        assert caps is not None
        assert caps.provider_name == "test"
        assert caps.default_model == "stub-v1"

    def test_get_all_capabilities(self):
        reg = ProviderRegistry()
        reg.register("a", _StubProvider(name="a"))
        reg.register("b", _StubProvider(name="b"))
        all_caps = reg.get_all_capabilities()
        assert len(all_caps) == 2
        assert "a" in all_caps
        assert "b" in all_caps

    def test_to_dict(self):
        reg = ProviderRegistry()
        reg.register("a", _StubProvider(name="a"))
        d = reg.to_dict()
        assert "a" in d
        assert d["a"]["provider_name"] == "a"

    def test_report(self):
        reg = ProviderRegistry()
        reg.register("test", _StubProvider(name="test"))
        report = reg.report()
        assert "Available Providers" in report
        assert "test" in report

    def test_empty_report(self):
        reg = ProviderRegistry()
        assert "No providers registered" in reg.report()

    def test_registry_isolation(self):
        """Separate registries do not share state."""
        r1 = ProviderRegistry()
        r2 = ProviderRegistry()
        r1.register("p", _StubProvider(name="p"))
        assert r2.count() == 0
        assert r1.count() == 1
