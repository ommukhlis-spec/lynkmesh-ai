"""
Tests for the full bridge task lifecycle — pending → executing → done.

Covers TaskRouter, ClaudeBridge, ChatGPTBridge, and ProviderDiscovery
through the full lifecycle.

Run: python -m pytest tests/test_bridge_lifecycle.py -v
"""

import pytest
import tempfile
from pathlib import Path

from lynkmesh_ai.bridges.task_router import TaskRouter, BridgeTask
from lynkmesh_ai.bridges.claude_bridge import ClaudeBridge
from lynkmesh_ai.bridges.chatgpt_bridge import ChatGPTBridge
from lynkmesh_ai.bridges.registry import ProviderRegistry
from lynkmesh_ai.bridges.base import ProviderRole, TaskStatus
from lynkmesh_ai.bridges.providers.claude_code_provider import ClaudeCodeProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def router(tmp_dir):
    return TaskRouter(tmp_dir)


@pytest.fixture
def claude(tmp_dir):
    return ClaudeBridge(tmp_dir)


@pytest.fixture
def chatgpt(tmp_dir):
    return ChatGPTBridge(tmp_dir)


# ---------------------------------------------------------------------------
# TaskRouter lifecycle
# ---------------------------------------------------------------------------

class TestTaskRouterLifecycle:
    """TaskRouter: create → execute → done → query."""

    def test_create_task(self, router):
        task = router.create_task(
            title="Lifecycle test",
            source="manual",
            assigned_to="claude",
            module="auth",
            priority="high",
        )
        assert task.id.startswith("task_")
        assert task.status == "pending"
        assert task.source == "manual"
        assert task.priority == "high"

    def test_create_task_defaults(self, router):
        task = router.create_task(title="Defaults")
        assert task.source == "manual"
        assert task.assigned_to == "claude"
        assert task.status == "pending"
        assert task.priority == "medium"

    def test_create_task_invalid_source_raises(self, router):
        with pytest.raises(ValueError, match="Invalid source"):
            BridgeTask(id="x", source="invalid_source", title="Bad")

    def test_create_task_invalid_status_raises(self, router):
        with pytest.raises(ValueError, match="Invalid status"):
            BridgeTask(id="x", source="manual", status="invalid_status", title="Bad")

    def test_move_to_executing(self, router):
        task = router.create_task(title="Move to exec")
        updated = router.move_to_executing(task.id)
        assert updated.status == "executing"

    def test_move_to_done(self, router):
        task = router.create_task(title="Move to done")
        router.move_to_executing(task.id)
        updated = router.move_to_done(task.id)
        assert updated.status == "done"
        assert updated.completed_at is not None

    def test_move_to_failed(self, router):
        task = router.create_task(title="Move to fail")
        updated = router.move_to_failed(task.id, error="Test error")
        assert updated.status == "failed"
        assert updated.metadata["error"] == "Test error"

    def test_move_to_blocked(self, router):
        task = router.create_task(title="Move to blocked")
        updated = router.move_to_blocked(task.id, reason="Waiting for input")
        assert updated.status == "blocked"
        assert updated.metadata["blocked_reason"] == "Waiting for input"

    def test_transition_nonexistent(self, router):
        assert router.move_to_executing("nonexistent") is None
        assert router.move_to_done("nonexistent") is None

    def test_get_task(self, router):
        task = router.create_task(title="Get me")
        retrieved = router.get_task(task.id)
        assert retrieved is not None
        assert retrieved.title == "Get me"

    def test_get_task_nonexistent(self, router):
        assert router.get_task("nonexistent") is None

    def test_delete_task(self, router):
        task = router.create_task(title="Delete me")
        assert router.delete_task(task.id) is True
        assert router.get_task(task.id) is None

    def test_delete_nonexistent(self, router):
        assert router.delete_task("nonexistent") is False

    def test_list_tasks_filtered(self, router):
        router.create_task(title="Task A", source="chatgpt", priority="high")
        router.create_task(title="Task B", source="manual", priority="low")
        router.create_task(title="Task C", source="chatgpt", priority="medium")

        chatgpt_tasks = router.list_tasks(source="chatgpt")
        assert len(chatgpt_tasks) == 2

        high_tasks = router.list_tasks(source="chatgpt")
        # High-priority chatgpt tasks ordered first
        assert high_tasks[0].priority == "high"

    def test_get_next_task(self, router):
        router.create_task(title="Low prio", priority="low", source="chatgpt")
        router.create_task(title="High prio", priority="high", source="chatgpt")
        next_task = router.get_next_task(assigned_to="claude")
        assert next_task.priority == "high"

    def test_get_next_task_empty(self, router):
        assert router.get_next_task() is None

    def test_count_by_status(self, router):
        router.create_task(title="P1")
        router.create_task(title="P2")
        t3 = router.create_task(title="E1")
        router.move_to_executing(t3.id)
        counts = router.count_by_status()
        assert counts.get("pending") == 2
        assert counts.get("executing") == 1

    def test_count_by_source(self, router):
        router.create_task(title="A", source="chatgpt")
        router.create_task(title="B", source="chatgpt")
        router.create_task(title="C", source="manual")
        counts = router.count_by_source()
        assert counts.get("chatgpt") == 2
        assert counts.get("manual") == 1

    def test_create_batch(self, router):
        specs = [
            {"title": "Batch 1", "module": "auth", "priority": "high"},
            {"title": "Batch 2", "module": "payment", "priority": "medium"},
        ]
        tasks = router.create_batch(specs, source="chatgpt")
        assert len(tasks) == 2
        assert tasks[0].source == "chatgpt"
        assert tasks[0].priority == "high"

    def test_json_roundtrip(self, router):
        task = router.create_task(
            title="Roundtrip test",
            source="chatgpt",
            module="auth",
            priority="high",
            description="Test desc",
            tags=["urgent", "security"],
        )
        # Read back from disk
        task2 = router.get_task(task.id)
        assert task2 is not None
        assert task2.title == task.title
        assert task2.source == task.source
        assert task2.module == task.module
        assert task2.priority == task.priority
        assert task2.tags == task.tags


# ---------------------------------------------------------------------------
# Full ChatGPT → Claude lifecycle
# ---------------------------------------------------------------------------

class TestChatGPTToClaudeLifecycle:
    """End-to-end: ChatGPT creates task → Claude picks up → Claude completes."""

    def test_full_lifecycle(self, chatgpt, claude):
        # 1. ChatGPT creates a task
        task = chatgpt.create_chatgpt_task(
            title="Refactor auth.service",
            module="auth.service",
            priority="high",
            description="The auth service needs dependency injection.",
            instructions="1. Identify direct instantiations\n2. Replace with constructor injection",
        )
        assert task.source == "chatgpt"
        assert task.assigned_to == "claude"
        assert task.status == "pending"

        # 2. ChatGPT checks status (still pending)
        status = chatgpt.get_task_status(task.id)
        assert status["status"] == "pending"

        # 3. Claude pulls the next task
        pulled = claude.pull_next_task()
        assert pulled is not None
        assert pulled.id == task.id
        assert pulled.priority == "high"

        # 4. Claude claims it
        claimed = claude.pull_and_claim()
        assert claimed is not None
        # (The claimed task might be this one or the next one)

        # 5. Claude marks the original as done
        completed = claude.mark_done(
            task.id,
            result={"files_changed": 3, "tests_added": 5},
            note="Refactored auth.service constructor to accept dependencies.",
        )
        assert completed is not None
        assert completed.status == "done"
        assert completed.metadata["result"] == {"files_changed": 3, "tests_added": 5}

        # 6. ChatGPT queries completed tasks
        done = chatgpt.get_completed_tasks()
        assert len(done) >= 1
        assert any(t.id == task.id for t in done)

        # 7. ChatGPT gets the final result
        final_status = chatgpt.get_task_status(task.id)
        assert final_status["status"] == "done"
        assert final_status["result"] == {"files_changed": 3, "tests_added": 5}

    def test_multiple_tasks_priority_order(self, chatgpt, claude):
        """Tasks should be consumed in priority order (high → medium → low)."""
        # Create in mixed order
        chatgpt.create_chatgpt_task(title="Low", priority="low", module="a")
        chatgpt.create_chatgpt_task(title="High", priority="high", module="a")
        chatgpt.create_chatgpt_task(title="Medium", priority="medium", module="a")

        # pull_and_claim() consumes each task (marks executing), so next pull gets the next
        first = claude.pull_and_claim()
        second = claude.pull_and_claim()
        third = claude.pull_and_claim()

        assert first.priority == "high"
        assert second.priority == "medium"
        assert third.priority == "low"


# ---------------------------------------------------------------------------
# Provider discovery in lifecycle context
# ---------------------------------------------------------------------------

class TestProviderDiscovery:
    """ProviderRegistry integrated with the task lifecycle."""

    def test_discover_and_use_claude_code(self, tmp_dir):
        reg = ProviderRegistry()
        reg.register("claude-code", ClaudeCodeProvider(tmp_dir))

        # Discover consumer
        consumer = reg.find_consumer()
        assert consumer is not None
        assert consumer.name == "claude-code"

        # Use it
        tid = consumer.submit_task({"title": "Via discovery"})
        assert tid.startswith("task_")

        status = consumer.get_status(tid)
        assert status == TaskStatus.PENDING

    def test_provider_role_routing(self, tmp_dir):
        reg = ProviderRegistry()
        from lynkmesh_ai.bridges.providers import AnthropicProvider, OpenAIProvider

        reg.register("claude-code", ClaudeCodeProvider(tmp_dir))
        reg.register("openai", OpenAIProvider())
        reg.register("anthropic", AnthropicProvider())

        consumers = reg.list_by_role(ProviderRole.CONSUMER)
        producers = reg.list_by_role(ProviderRole.PRODUCER)

        assert "claude-code" in consumers
        assert "openai" in producers
        # anthropic is BOTH
        assert "anthropic" in consumers
        assert "anthropic" in producers

    def test_route_from_chatgpt_to_claude(self, tmp_dir):
        """Simulate ChatGPT creating a task that gets routed to Claude."""
        reg = ProviderRegistry()
        reg.register("claude-code", ClaudeCodeProvider(tmp_dir))

        chatgpt_bridge = ChatGPTBridge(tmp_dir)
        task = chatgpt_bridge.create_chatgpt_task(
            title="Routed task",
            module="auth",
            priority="high",
        )

        # Route to the consumer
        target = reg.route_task(task.to_dict(), preferred_provider="claude-code")
        assert target == "claude-code"

        # Consumer executes it
        consumer = reg[target]
        status = consumer.get_status(task.id)
        assert status == TaskStatus.PENDING

    def test_registry_capabilities_export(self):
        reg = ProviderRegistry()
        reg.register("claude-code", ClaudeCodeProvider())

        caps = reg.get_all_capabilities()
        cc = caps["claude-code"]
        assert cc.provider_name == "claude-code"
        assert cc.role == ProviderRole.CONSUMER
        assert cc.default_model == "claude-sonnet-4-6"
