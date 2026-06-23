"""
Tests for AgentProvider contract — ClaudeBridge and ChatGPTBridge implementations.

Verifies that both bridges correctly implement the AgentProvider interface:
capabilities, submit_task, get_status, get_result, cancel_task, validate_task, health_check.

Run: python -m pytest tests/test_agent_provider_contract.py -v
"""

import pytest
import tempfile
from pathlib import Path

from lynkmesh_ai.bridges.base import (
    AgentProvider,
    ProviderCapabilities,
    ProviderRole,
    TaskStatus,
    TaskResult,
)
from lynkmesh_ai.bridges.claude_bridge import ClaudeBridge
from lynkmesh_ai.bridges.chatgpt_bridge import ChatGPTBridge
from lynkmesh_ai.bridges.task_router import BridgeTask
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
def claude_bridge(tmp_dir):
    return ClaudeBridge(tmp_dir)


@pytest.fixture
def chatgpt_bridge(tmp_dir):
    return ChatGPTBridge(tmp_dir)


# ---------------------------------------------------------------------------
# Inheritance check
# ---------------------------------------------------------------------------

class TestAgentProviderInheritance:
    """Both bridges must be instances of AgentProvider."""

    def test_claude_bridge_is_agent_provider(self):
        assert issubclass(ClaudeBridge, AgentProvider)

    def test_chatgpt_bridge_is_agent_provider(self):
        assert issubclass(ChatGPTBridge, AgentProvider)

    def test_claude_code_provider_is_agent_provider(self):
        assert issubclass(ClaudeCodeProvider, AgentProvider)

    def test_concrete_instances_are_agent_providers(self, claude_bridge, chatgpt_bridge):
        assert isinstance(claude_bridge, AgentProvider)
        assert isinstance(chatgpt_bridge, AgentProvider)


# ---------------------------------------------------------------------------
# capabilities()
# ---------------------------------------------------------------------------

class TestCapabilities:
    """capabilities() must return a valid ProviderCapabilities."""

    def test_claude_capabilities(self, claude_bridge):
        caps = claude_bridge.capabilities()
        assert isinstance(caps, ProviderCapabilities)
        assert caps.provider_name == "claude-code"
        assert caps.role == ProviderRole.CONSUMER
        assert caps.default_model == "claude-sonnet-4-6"

    def test_chatgpt_capabilities(self, chatgpt_bridge):
        caps = chatgpt_bridge.capabilities()
        assert isinstance(caps, ProviderCapabilities)
        assert caps.provider_name == "chatgpt"
        assert caps.role == ProviderRole.PRODUCER
        assert caps.default_model == "gpt-4o"

    def test_capabilities_to_dict(self, claude_bridge):
        d = claude_bridge.capabilities().to_dict()
        assert d["provider_name"] == "claude-code"
        assert d["role"] == "consumer"


# ---------------------------------------------------------------------------
# submit_task()
# ---------------------------------------------------------------------------

class TestSubmitTask:
    """submit_task() must accept dict, BridgeTask, and str task_id."""

    def test_submit_dict(self, claude_bridge):
        tid = claude_bridge.submit_task({
            "title": "Test task",
            "module": "auth",
            "priority": "high",
            "description": "Test description",
        })
        assert tid.startswith("task_")
        # Verify it was stored
        status = claude_bridge.get_status(tid)
        assert status == TaskStatus.PENDING

    def test_submit_bridge_task(self, claude_bridge):
        bt = BridgeTask(
            id="task_test_001",
            source="manual",
            assigned_to="claude",
            title="Pre-built task",
            module="auth",
        )
        tid = claude_bridge.submit_task(bt)
        assert tid == "task_test_001"

    def test_submit_task_id_string(self, claude_bridge):
        # First create a task, then submit its ID
        tid1 = claude_bridge.submit_task({"title": "First"})
        tid2 = claude_bridge.submit_task(tid1)
        assert tid1 == tid2

    def test_submit_invalid_type_raises(self, claude_bridge):
        with pytest.raises(ValueError, match="must be BridgeTask, dict, or str"):
            claude_bridge.submit_task(42)

    def test_submit_with_context(self, claude_bridge):
        tid = claude_bridge.submit_task(
            {"title": "Test"},
            context={"key": "value", "analysis": {"risk": "high"}},
        )
        # Context should be attached to the task metadata
        from lynkmesh_ai.bridges.task_router import TaskRouter
        router = TaskRouter(claude_bridge.router.root_dir)
        task = router.get_task(tid)
        assert task is not None
        assert task.metadata.get("context") == {"key": "value", "analysis": {"risk": "high"}}

    def test_chatgpt_submit_dict(self, chatgpt_bridge):
        tid = chatgpt_bridge.submit_task({
            "title": "ChatGPT task",
            "module": "payment",
        })
        assert tid.startswith("task_")
        task = chatgpt_bridge.router.get_task(tid)
        assert task.source == "chatgpt"
        assert task.assigned_to == "claude"


# ---------------------------------------------------------------------------
# get_status() / get_result()
# ---------------------------------------------------------------------------

class TestStatusAndResult:
    """Status tracking must work correctly through the provider interface."""

    def test_get_status_pending(self, claude_bridge):
        tid = claude_bridge.submit_task({"title": "Status test"})
        assert claude_bridge.get_status(tid) == TaskStatus.PENDING

    def test_get_status_executing(self, claude_bridge):
        tid = claude_bridge.submit_task({"title": "Status test"})
        claude_bridge.mark_running(tid)
        assert claude_bridge.get_status(tid) == TaskStatus.EXECUTING

    def test_get_status_done(self, claude_bridge):
        tid = claude_bridge.submit_task({"title": "Status test"})
        claude_bridge.mark_running(tid)
        claude_bridge.mark_done(tid)
        assert claude_bridge.get_status(tid) == TaskStatus.DONE

    def test_get_status_nonexistent(self, claude_bridge):
        with pytest.raises(KeyError):
            claude_bridge.get_status("nonexistent_xyz")

    def test_get_result_completed(self, claude_bridge):
        tid = claude_bridge.submit_task({"title": "Result test"})
        claude_bridge.mark_done(tid, result={"output": "success"})
        result = claude_bridge.get_result(tid)
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert result.data == {"output": "success"}

    def test_get_result_failed(self, claude_bridge):
        tid = claude_bridge.submit_task({"title": "Fail test"})
        claude_bridge.mark_failed(tid, error="Something broke")
        result = claude_bridge.get_result(tid)
        assert result.success is False
        assert result.error == "Something broke"

    def test_get_result_pending_raises(self, claude_bridge):
        tid = claude_bridge.submit_task({"title": "Pending"})
        with pytest.raises(RuntimeError, match="not complete"):
            claude_bridge.get_result(tid)

    def test_get_result_nonexistent(self, claude_bridge):
        with pytest.raises(KeyError):
            claude_bridge.get_result("nonexistent_xyz")


# ---------------------------------------------------------------------------
# Optional methods
# ---------------------------------------------------------------------------

class TestOptionalMethods:
    """cancel_task, validate_task, health_check should work correctly."""

    def test_cancel_pending_task(self, claude_bridge):
        tid = claude_bridge.submit_task({"title": "Cancel me"})
        assert claude_bridge.cancel_task(tid) is True
        assert claude_bridge.router.get_task(tid) is None  # Deleted

    def test_cancel_executing_task_fails(self, claude_bridge):
        tid = claude_bridge.submit_task({"title": "Running"})
        claude_bridge.mark_running(tid)
        assert claude_bridge.cancel_task(tid) is False  # Can't cancel executing

    def test_validate_task_bridge_task(self, claude_bridge):
        bt = BridgeTask(id="v", source="manual", assigned_to="claude", title="OK")
        assert claude_bridge.validate_task(bt) is True

    def test_validate_task_dict(self, claude_bridge):
        assert claude_bridge.validate_task({"title": "OK"}) is True
        assert claude_bridge.validate_task({"id": "task_123"}) is True
        assert claude_bridge.validate_task({}) is False

    def test_validate_task_string(self, claude_bridge):
        assert claude_bridge.validate_task("task_123") is True
        assert claude_bridge.validate_task("") is False

    def test_validate_task_invalid(self, claude_bridge):
        assert claude_bridge.validate_task(42) is False

    def test_health_check(self, claude_bridge):
        assert claude_bridge.health_check() is True


# ---------------------------------------------------------------------------
# ChatGPT-specific contract
# ---------------------------------------------------------------------------

class TestChatGPTProviderContract:
    """ChatGPTBridge-specific behaviors."""

    def test_create_chatgpt_task_backward_compat(self, chatgpt_bridge):
        task = chatgpt_bridge.create_chatgpt_task(
            title="Legacy API test",
            module="auth",
            priority="high",
            description="Testing backward compat",
        )
        assert task.source == "chatgpt"
        assert task.assigned_to == "claude"
        assert task.priority == "high"

    def test_get_task_status_dict(self, chatgpt_bridge):
        task = chatgpt_bridge.create_chatgpt_task(title="Status check", module="auth")
        result = chatgpt_bridge.get_task_status(task.id)
        assert result is not None
        assert result["status"] == "pending"
        assert result["title"] == "Status check"

    def test_cancel_task_override(self, chatgpt_bridge):
        task = chatgpt_bridge.create_chatgpt_task(title="Cancel GPT task")
        assert chatgpt_bridge.cancel_task(task.id) is True
        assert chatgpt_bridge.get_task_status(task.id) is None

    def test_cancel_non_pending_fails(self, chatgpt_bridge):
        task = chatgpt_bridge.create_chatgpt_task(title="Running GPT task")
        chatgpt_bridge.router.move_to_executing(task.id)
        assert chatgpt_bridge.cancel_task(task.id) is False
