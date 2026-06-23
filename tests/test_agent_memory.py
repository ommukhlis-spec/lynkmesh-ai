"""Tests for AgentMemory — patterns, provider stats, execution history, decisions."""

import pytest
import tempfile
from pathlib import Path

from lynkmesh_ai.agents.memory import (
    AgentMemory, TaskPattern, ProviderStats, ExecutionRecord,
)
from lynkmesh_ai.storage.adapters import FileStorageAdapter


class TestAgentMemory:
    """AgentMemory: CRUD for all four collections."""

    @pytest.fixture
    def memory(self):
        d = tempfile.mkdtemp()
        m = AgentMemory(root_dir=Path(d))
        yield m
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # ------------------------------------------------------------------
    # Task patterns
    # ------------------------------------------------------------------

    def test_record_and_get_pattern(self, memory):
        p = TaskPattern(
            pattern_id="pat_001",
            module_pattern="auth\\..*",
            action_type="refactor",
            success_count=5,
            failure_count=1,
        )
        memory.record_pattern(p)
        retrieved = memory.get_pattern("pat_001")
        assert retrieved is not None
        assert retrieved.module_pattern == "auth\\..*"
        assert retrieved.action_type == "refactor"
        assert retrieved.success_rate == 5 / 6

    def test_list_patterns(self, memory):
        memory.record_pattern(TaskPattern(pattern_id="p1", action_type="refactor"))
        memory.record_pattern(TaskPattern(pattern_id="p2", action_type="add_tests"))
        memory.record_pattern(TaskPattern(pattern_id="p3", action_type="refactor"))
        all_p = memory.list_patterns()
        assert len(all_p) == 3
        refactor = memory.list_patterns(action_type="refactor")
        assert len(refactor) == 2

    def test_get_pattern_nonexistent(self, memory):
        assert memory.get_pattern("nonexistent") is None

    def test_get_best_pattern_for_module(self, memory):
        memory.record_pattern(TaskPattern(
            pattern_id="p1", module_pattern="auth\\..*",
            action_type="refactor", success_count=9, failure_count=1,
        ))
        memory.record_pattern(TaskPattern(
            pattern_id="p2", module_pattern="payment\\..*",
            action_type="refactor", success_count=1, failure_count=9,
        ))
        best = memory.get_best_pattern_for_module("auth.service")
        assert best is not None
        assert best.pattern_id == "p1"

    def test_get_best_pattern_no_match(self, memory):
        assert memory.get_best_pattern_for_module("nonexistent") is None

    # ------------------------------------------------------------------
    # Provider statistics
    # ------------------------------------------------------------------

    def test_record_and_get_provider_stats(self, memory):
        s = ProviderStats(
            provider_name="claude-code",
            module="auth.service",
            total_tasks=10,
            successes=9,
            failures=1,
        )
        memory.record_provider_stats(s)
        retrieved = memory.get_provider_stats("claude-code", "auth.service")
        assert retrieved is not None
        assert retrieved.total_tasks == 10
        assert retrieved.success_rate == 0.9

    def test_list_provider_stats(self, memory):
        memory.record_provider_stats(ProviderStats(provider_name="claude-code", total_tasks=5, successes=5))
        memory.record_provider_stats(ProviderStats(provider_name="chatgpt", total_tasks=3, successes=2, failures=1))
        all_stats = memory.list_provider_stats()
        assert len(all_stats) == 2

    def test_get_best_provider_for_module(self, memory):
        memory.record_provider_stats(ProviderStats(
            provider_name="claude-code", module="auth.service",
            total_tasks=10, successes=9, failures=1,
        ))
        memory.record_provider_stats(ProviderStats(
            provider_name="chatgpt", module="auth.service",
            total_tasks=10, successes=3, failures=7,
        ))
        best = memory.get_best_provider_for_module("auth.service")
        assert best == "claude-code"

    def test_get_best_provider_requires_min_tasks(self, memory):
        memory.record_provider_stats(ProviderStats(
            provider_name="new-provider", module="auth.service",
            total_tasks=1, successes=1, failures=0,  # 100% but only 1 task
        ))
        # Should not recommend because total_tasks < 3
        best = memory.get_best_provider_for_module("auth.service")
        assert best is None

    # ------------------------------------------------------------------
    # Execution history
    # ------------------------------------------------------------------

    def test_record_and_get_execution(self, memory):
        er = ExecutionRecord(
            cycle_id="cycle_001",
            module="auth.service",
            action_type="refactor",
            provider_name="claude-code",
            task_id="task_001",
            status="done",
            duration_ms=1500.0,
        )
        memory.record_execution(er)
        retrieved = memory.get_execution("cycle_001")
        assert retrieved is not None
        assert retrieved.module == "auth.service"
        assert retrieved.status == "done"

    def test_list_executions_filtered(self, memory):
        memory.record_execution(ExecutionRecord(
            cycle_id="c1", module="auth", status="done", action_type="refactor",
            provider_name="claude-code", task_id="t1",
        ))
        memory.record_execution(ExecutionRecord(
            cycle_id="c2", module="payment", status="failed", action_type="add_tests",
            provider_name="claude-code", task_id="t2",
        ))
        memory.record_execution(ExecutionRecord(
            cycle_id="c3", module="auth", status="done", action_type="add_tests",
            provider_name="chatgpt", task_id="t3",
        ))
        auth_done = memory.list_executions(module="auth", status="done")
        assert len(auth_done) == 2
        assert auth_done[0].cycle_id == "c3"  # Most recent first

    def test_list_executions_limit(self, memory):
        for i in range(10):
            memory.record_execution(ExecutionRecord(
                cycle_id=f"c{i}", module="auth", status="done",
                action_type="refactor", provider_name="claude-code", task_id=f"t{i}",
            ))
        assert len(memory.list_executions(limit=5)) == 5

    def test_get_execution_nonexistent(self, memory):
        assert memory.get_execution("nonexistent") is None

    # ------------------------------------------------------------------
    # Architecture decisions
    # ------------------------------------------------------------------

    def test_record_and_get_decision(self, memory):
        memory.record_decision("ADR-001", {"title": "Provider Architecture", "status": "accepted"})
        dec = memory.get_decision("ADR-001")
        assert dec is not None
        assert dec["title"] == "Provider Architecture"

    def test_list_decisions(self, memory):
        memory.record_decision("ADR-001", {"title": "First"})
        memory.record_decision("ADR-002", {"title": "Second"})
        decisions = memory.list_decisions()
        assert len(decisions) == 2

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def test_count_by_prefix(self, memory):
        memory.record_pattern(TaskPattern(pattern_id="p1"))
        memory.record_provider_stats(ProviderStats(provider_name="test"))
        memory.record_execution(ExecutionRecord(
            cycle_id="c1", module="auth", status="done",
            action_type="refactor", provider_name="claude-code", task_id="t1",
        ))
        counts = memory.count_by_prefix()
        assert counts["patterns"] == 1
        assert counts["providers"] == 1
        assert counts["history"] == 1

    def test_clear_all(self, memory):
        memory.record_pattern(TaskPattern(pattern_id="p1"))
        memory.record_execution(ExecutionRecord(
            cycle_id="c1", module="auth", status="done",
            action_type="refactor", provider_name="claude-code", task_id="t1",
        ))
        memory.clear_all()
        assert len(memory.list_patterns()) == 0
        assert len(memory.list_executions()) == 0

    def test_to_dict(self, memory):
        memory.record_pattern(TaskPattern(pattern_id="p1"))
        d = memory.to_dict()
        assert len(d) == 1
        assert any("patterns" in k for k in d)
