"""
AgentMemory -- schema and storage for learning loop data.

Persists task execution patterns, provider success rates,
execution history, and architecture decisions for the future
Agent Loop Engine to learn from past outcomes.

Schema design (ready for Phase 2 integration):
    - task_patterns:      What kinds of tasks succeed/fail?
    - provider_stats:     Which providers are reliable for which modules?
    - execution_history:  What happened on each agent cycle?
    - decisions:          What architecture decisions were made?
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lynkmesh_ai.storage.adapters import StorageAdapter, FileStorageAdapter

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Schema types
# ══════════════════════════════════════════════════════════════════════

@dataclass
class TaskPattern:
    """Learned pattern about what kinds of tasks succeed or fail."""

    pattern_id: str
    module_pattern: str = ""       # Regex or glob for module names
    action_type: str = ""          # refactor, add_tests, etc.
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: float = 0.0
    common_errors: List[str] = field(default_factory=list)
    last_seen: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "module_pattern": self.module_pattern,
            "action_type": self.action_type,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_duration_ms": self.avg_duration_ms,
            "common_errors": self.common_errors,
            "last_seen": self.last_seen,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskPattern":
        return cls(
            pattern_id=d.get("pattern_id", ""),
            module_pattern=d.get("module_pattern", ""),
            action_type=d.get("action_type", ""),
            success_count=d.get("success_count", 0),
            failure_count=d.get("failure_count", 0),
            avg_duration_ms=d.get("avg_duration_ms", 0.0),
            common_errors=d.get("common_errors", []),
            last_seen=d.get("last_seen", ""),
            created_at=d.get("created_at", ""),
        )


@dataclass
class ProviderStats:
    """Success/failure statistics for a specific provider on a specific module."""

    provider_name: str
    module: str = ""               # Empty = aggregate across all modules
    total_tasks: int = 0
    successes: int = 0
    failures: int = 0
    avg_duration_ms: float = 0.0
    last_used: str = ""

    @property
    def success_rate(self) -> float:
        return self.successes / self.total_tasks if self.total_tasks > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "module": self.module,
            "total_tasks": self.total_tasks,
            "successes": self.successes,
            "failures": self.failures,
            "avg_duration_ms": self.avg_duration_ms,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProviderStats":
        return cls(
            provider_name=d.get("provider_name", ""),
            module=d.get("module", ""),
            total_tasks=d.get("total_tasks", 0),
            successes=d.get("successes", 0),
            failures=d.get("failures", 0),
            avg_duration_ms=d.get("avg_duration_ms", 0.0),
            last_used=d.get("last_used", ""),
        )


@dataclass
class ExecutionRecord:
    """Record of a single agent cycle execution."""

    cycle_id: str
    module: str = ""
    action_type: str = ""
    provider_name: str = ""
    task_id: str = ""
    status: str = ""               # pending, executing, done, failed
    duration_ms: float = 0.0
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "module": self.module,
            "action_type": self.action_type,
            "provider_name": self.provider_name,
            "task_id": self.task_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExecutionRecord":
        return cls(
            cycle_id=d.get("cycle_id", ""),
            module=d.get("module", ""),
            action_type=d.get("action_type", ""),
            provider_name=d.get("provider_name", ""),
            task_id=d.get("task_id", ""),
            status=d.get("status", ""),
            duration_ms=d.get("duration_ms", 0.0),
            error=d.get("error"),
            created_at=d.get("created_at", ""),
            metadata=d.get("metadata", {}),
        )


# ══════════════════════════════════════════════════════════════════════
# AgentMemory
# ══════════════════════════════════════════════════════════════════════

class AgentMemory:
    """
    Persistent memory for the Agent Loop Engine.

    Stores task patterns, provider statistics, execution history,
    and architecture decisions. Backed by any StorageAdapter.

    Schema (four collections):
        patterns/  -- TaskPattern records
        providers/ -- ProviderStats records
        history/   -- ExecutionRecord entries
        decisions/ -- ArchitectureDecision references

    Usage (Phase 2):
        memory = AgentMemory(FileStorageAdapter(Path(".ai/memory")))
        memory.record_execution(ExecutionRecord(...))
        pattern = memory.get_best_pattern_for_module("auth.service")
        stats = memory.get_provider_stats("claude-code")
    """

    PREFIX_PATTERNS = "patterns/"
    PREFIX_PROVIDERS = "providers/"
    PREFIX_HISTORY = "history/"
    PREFIX_DECISIONS = "decisions/"

    def __init__(self, storage: Optional[StorageAdapter] = None, root_dir: Optional[Path] = None) -> None:
        self.storage = storage or FileStorageAdapter(root_dir or Path(".ai/memory"))

    # ------------------------------------------------------------------
    # Task patterns
    # ------------------------------------------------------------------

    def record_pattern(self, pattern: TaskPattern) -> None:
        """Store or update a learned task pattern."""
        key = f"{self.PREFIX_PATTERNS}{pattern.pattern_id}"
        self.storage.put(key, pattern.to_dict())

    def get_pattern(self, pattern_id: str) -> Optional[TaskPattern]:
        """Retrieve a specific task pattern."""
        key = f"{self.PREFIX_PATTERNS}{pattern_id}"
        rec = self.storage.get(key)
        return TaskPattern.from_dict(rec.data) if rec else None

    def list_patterns(self, action_type: Optional[str] = None) -> List[TaskPattern]:
        """List task patterns, optionally filtered by action type."""
        patterns = []
        for key in self.storage.list_keys(prefix=self.PREFIX_PATTERNS):
            rec = self.storage.get(key)
            if rec:
                p = TaskPattern.from_dict(rec.data)
                if not action_type or p.action_type == action_type:
                    patterns.append(p)
        return patterns

    def get_best_pattern_for_module(self, module: str) -> Optional[TaskPattern]:
        """Find the pattern with the highest success rate matching a module."""
        import re
        best = None
        best_rate = -1.0
        for pattern in self.list_patterns():
            if pattern.module_pattern:
                try:
                    if re.search(pattern.module_pattern, module):
                        if pattern.success_rate > best_rate:
                            best_rate = pattern.success_rate
                            best = pattern
                except re.error:
                    pass
        return best

    # ------------------------------------------------------------------
    # Provider statistics
    # ------------------------------------------------------------------

    def record_provider_stats(self, stats: ProviderStats) -> None:
        """Store or update provider statistics."""
        key = f"{self.PREFIX_PROVIDERS}{stats.provider_name}/{stats.module or '_all'}"
        self.storage.put(key, stats.to_dict())

    def get_provider_stats(self, provider_name: str, module: str = "") -> Optional[ProviderStats]:
        """Get statistics for a provider, optionally scoped to a module."""
        mod_key = module or "_all"
        key = f"{self.PREFIX_PROVIDERS}{provider_name}/{mod_key}"
        rec = self.storage.get(key)
        return ProviderStats.from_dict(rec.data) if rec else None

    def list_provider_stats(self) -> List[ProviderStats]:
        """List all provider statistics."""
        stats = []
        for key in self.storage.list_keys(prefix=self.PREFIX_PROVIDERS):
            rec = self.storage.get(key)
            if rec:
                stats.append(ProviderStats.from_dict(rec.data))
        return stats

    def get_best_provider_for_module(self, module: str) -> Optional[str]:
        """Find the provider with the highest success rate for a given module."""
        best_name = None
        best_rate = -1.0
        for stats in self.list_provider_stats():
            if stats.module == module or stats.module == "_all":
                if stats.success_rate > best_rate and stats.total_tasks >= 3:
                    best_rate = stats.success_rate
                    best_name = stats.provider_name
        return best_name

    # ------------------------------------------------------------------
    # Execution history
    # ------------------------------------------------------------------

    def record_execution(self, record: ExecutionRecord) -> None:
        """Record an execution cycle outcome."""
        key = f"{self.PREFIX_HISTORY}{record.cycle_id}"
        self.storage.put(key, record.to_dict())

    def get_execution(self, cycle_id: str) -> Optional[ExecutionRecord]:
        """Retrieve a specific execution record."""
        key = f"{self.PREFIX_HISTORY}{cycle_id}"
        rec = self.storage.get(key)
        return ExecutionRecord.from_dict(rec.data) if rec else None

    def list_executions(
        self,
        module: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ExecutionRecord]:
        """List execution records with optional filters."""
        records = []
        for key in self.storage.list_keys(prefix=self.PREFIX_HISTORY):
            rec = self.storage.get(key)
            if rec:
                er = ExecutionRecord.from_dict(rec.data)
                if module and er.module != module:
                    continue
                if status and er.status != status:
                    continue
                records.append(er)
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    # ------------------------------------------------------------------
    # Architecture decisions
    # ------------------------------------------------------------------

    def record_decision(self, decision_id: str, data: Dict[str, Any]) -> None:
        """Store an architecture decision reference."""
        key = f"{self.PREFIX_DECISIONS}{decision_id}"
        self.storage.put(key, data)

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an architecture decision."""
        key = f"{self.PREFIX_DECISIONS}{decision_id}"
        rec = self.storage.get(key)
        return rec.data if rec else None

    def list_decisions(self) -> List[Dict[str, Any]]:
        """List all stored architecture decisions."""
        decisions = []
        for key in self.storage.list_keys(prefix=self.PREFIX_DECISIONS):
            rec = self.storage.get(key)
            if rec:
                decisions.append(rec.data)
        return decisions

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def count_by_prefix(self) -> Dict[str, int]:
        """Count records per collection."""
        counts = {}
        for prefix in [self.PREFIX_PATTERNS, self.PREFIX_PROVIDERS, self.PREFIX_HISTORY, self.PREFIX_DECISIONS]:
            counts[prefix.rstrip("/")] = len(self.storage.list_keys(prefix=prefix))
        return counts

    def clear_all(self) -> None:
        """Clear all memory records."""
        self.storage.clear()

    def to_dict(self) -> Dict[str, Any]:
        """Export all memory as a dict (for debugging/migration)."""
        result: Dict[str, Any] = {}
        for key in self.storage.list_keys():
            rec = self.storage.get(key)
            if rec:
                result[key] = rec.to_dict()
        return result
