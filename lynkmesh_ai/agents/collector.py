"""
MemoryCollector -- subscribes to EventBus and automatically updates AgentMemory.

This is the integration point connecting the three Phase 1.6 subsystems:
    EventBus (events) -> MemoryCollector (bridge) -> AgentMemory (storage)

When TaskRouter emits lifecycle events, MemoryCollector:
    - Records ExecutionRecord entries for every task completion/failure
    - Updates ProviderStats from task outcomes
    - Learns TaskPatterns from recurring success/failure patterns

Usage:
    bus = EventBus()
    memory = AgentMemory()
    collector = MemoryCollector(bus, memory)  # Wires everything automatically
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from lynkmesh_ai.events.bus import EventBus, Event, EventType
from lynkmesh_ai.agents.memory import (
    AgentMemory, TaskPattern, ProviderStats, ExecutionRecord,
)

logger = logging.getLogger(__name__)


class MemoryCollector:
    """
    Subscribes to EventBus events and updates AgentMemory automatically.

    Handlers:
        TaskCreated  -> (no-op; task doesn't exist in memory until claimed)
        TaskClaimed  -> Record start time for duration tracking
        TaskCompleted -> Create ExecutionRecord, update ProviderStats, learn pattern
        TaskFailed    -> Create ExecutionRecord, update ProviderStats, learn failure pattern
        TaskBlocked   -> Create ExecutionRecord with blocked status
    """

    def __init__(self, bus: EventBus, memory: AgentMemory) -> None:
        self.bus = bus
        self.memory = memory
        self._start_times: Dict[str, float] = {}  # task_id -> perf_counter

        # Subscribe to all task events
        bus.subscribe(EventType.TASK_CREATED, self._on_task_created)
        bus.subscribe(EventType.TASK_CLAIMED, self._on_task_claimed)
        bus.subscribe(EventType.TASK_COMPLETED, self._on_task_completed)
        bus.subscribe(EventType.TASK_FAILED, self._on_task_failed)
        bus.subscribe(EventType.TASK_BLOCKED, self._on_task_blocked)

        logger.info("MemoryCollector: subscribed to all task lifecycle events")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_task_created(self, event: Event) -> None:
        """TaskCreated: track creation metadata (no storage yet)."""
        pass  # ExecutionRecord created on completion, not creation

    def _on_task_claimed(self, event: Event) -> None:
        """TaskClaimed: record start time for duration tracking."""
        self._start_times[event.task_id] = time.perf_counter()

    def _on_task_completed(self, event: Event) -> None:
        """TaskCompleted: record success, update stats, learn pattern."""
        duration_ms = self._pop_duration(event.task_id)
        module = event.data.get("module", "")
        provider = event.data.get("provider", "unknown")

        # 1. Record execution
        er = ExecutionRecord(
            cycle_id=f"cycle_{event.task_id}",
            module=module,
            action_type=event.data.get("action_type", "unknown"),
            provider_name=provider,
            task_id=event.task_id,
            status="done",
            duration_ms=duration_ms,
        )
        self.memory.record_execution(er)

        # 2. Update provider stats
        self._update_provider_stats(provider, module, success=True, duration_ms=duration_ms)

        # 3. Learn pattern
        self._learn_pattern(module, event.data.get("action_type", "unknown"), success=True)

    def _on_task_failed(self, event: Event) -> None:
        """TaskFailed: record failure, update stats, learn failure pattern."""
        duration_ms = self._pop_duration(event.task_id)
        module = event.data.get("module", "")
        provider = event.data.get("provider", "unknown")
        error = event.data.get("error", "unknown error")

        # 1. Record execution
        er = ExecutionRecord(
            cycle_id=f"cycle_{event.task_id}",
            module=module,
            action_type=event.data.get("action_type", "unknown"),
            provider_name=provider,
            task_id=event.task_id,
            status="failed",
            duration_ms=duration_ms,
            error=error,
        )
        self.memory.record_execution(er)

        # 2. Update provider stats
        self._update_provider_stats(provider, module, success=False, duration_ms=duration_ms)

        # 3. Learn failure pattern
        self._learn_pattern(module, event.data.get("action_type", "unknown"), success=False)

    def _on_task_blocked(self, event: Event) -> None:
        """TaskBlocked: record blocked status."""
        duration_ms = self._pop_duration(event.task_id)
        module = event.data.get("module", "")
        provider = event.data.get("provider", "unknown")

        er = ExecutionRecord(
            cycle_id=f"cycle_{event.task_id}",
            module=module,
            action_type=event.data.get("action_type", "unknown"),
            provider_name=provider,
            task_id=event.task_id,
            status="blocked",
            duration_ms=duration_ms,
            error=f"Blocked: {event.data.get('reason', 'unknown')}",
        )
        self.memory.record_execution(er)

    # ------------------------------------------------------------------
    # Stats + pattern learning
    # ------------------------------------------------------------------

    def _update_provider_stats(
        self, provider_name: str, module: str,
        success: bool, duration_ms: float,
    ) -> None:
        """Update or create ProviderStats for a given provider+module."""
        now = datetime.now(timezone.utc).isoformat()
        stats = self.memory.get_provider_stats(provider_name, module)

        if not stats:
            stats = ProviderStats(
                provider_name=provider_name,
                module=module,
                total_tasks=0,
                successes=0,
                failures=0,
                avg_duration_ms=0.0,
            )

        stats.total_tasks += 1
        if success:
            stats.successes += 1
        else:
            stats.failures += 1

        # Exponential moving average for duration
        alpha = 0.3
        stats.avg_duration_ms = (
            alpha * duration_ms + (1 - alpha) * stats.avg_duration_ms
            if stats.total_tasks > 1 else duration_ms
        )
        stats.last_used = now
        self.memory.record_provider_stats(stats)

    def _learn_pattern(
        self, module: str, action_type: str, success: bool,
    ) -> None:
        """Learn a TaskPattern from an execution outcome."""
        if not module:
            return

        # Create a pattern key from module prefix + action type
        # Examples: "auth.*:refactor", "payment.*:add_tests"
        parts = module.split(".")
        prefix = parts[0] if parts else module
        pattern_id = f"{prefix}__{action_type}"

        pattern = self.memory.get_pattern(pattern_id)
        if not pattern:
            pattern = TaskPattern(
                pattern_id=pattern_id,
                module_pattern=f"{prefix}\\..*",
                action_type=action_type,
            )

        if success:
            pattern.success_count += 1
        else:
            pattern.failure_count += 1

        pattern.last_seen = datetime.now(timezone.utc).isoformat()
        self.memory.record_pattern(pattern)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pop_duration(self, task_id: str) -> float:
        """Get and remove the start time for a task, returning duration in ms."""
        start = self._start_times.pop(task_id, None)
        if start is None:
            return 0.0
        return (time.perf_counter() - start) * 1000.0

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def collector_stats(self) -> Dict[str, Any]:
        """Return statistics about the collector's activity."""
        return {
            "tracked_durations": len(self._start_times),
            "patterns": len(self.memory.list_patterns()),
            "provider_stats": len(self.memory.list_provider_stats()),
            "executions": len(self.memory.list_executions()),
            "decisions": len(self.memory.list_decisions()),
        }

    def shutdown(self) -> None:
        """Unsubscribe from all events."""
        self.bus.unsubscribe(EventType.TASK_CREATED, self._on_task_created)
        self.bus.unsubscribe(EventType.TASK_CLAIMED, self._on_task_claimed)
        self.bus.unsubscribe(EventType.TASK_COMPLETED, self._on_task_completed)
        self.bus.unsubscribe(EventType.TASK_FAILED, self._on_task_failed)
        self.bus.unsubscribe(EventType.TASK_BLOCKED, self._on_task_blocked)
        logger.info("MemoryCollector: unsubscribed from all events")
