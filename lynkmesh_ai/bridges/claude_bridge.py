"""
ClaudeBridge -- Claude Code-facing bridge interface.

Provides the API that Claude Code (or any Claude Code-compatible
executor) would use to consume tasks from the LynkMesh AI bus.

This bridge is the "consumer side" -- it pulls tasks assigned
to Claude, marks them running, and reports completion.

Implements AgentProvider for provider-agnostic orchestration.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from lynkmesh_ai.bridges.task_router import TaskRouter, BridgeTask
from lynkmesh_ai.bridges.base import (
    AgentProvider,
    ProviderCapabilities,
    ProviderRole,
    TaskStatus,
    TaskResult,
)

logger = logging.getLogger(__name__)


class ClaudeBridge(AgentProvider):
    """
    Bridge interface for Claude Code task consumption.

    Implements AgentProvider -- can be registered in ProviderRegistry
    and used through the provider-agnostic orchestration API.

    Usage (from Claude Code's perspective):
        bridge = ClaudeBridge()
        task = bridge.pull_next_task()      # Get work
        bridge.mark_running(task.id)        # Claim it
        # ... Claude Code does the work ...
        bridge.mark_done(task.id, result)   # Report completion

    Usage (provider-agnostic):
        bridge = ClaudeBridge()
        task_id = bridge.submit_task(task_dict)
        status = bridge.get_status(task_id)
        result = bridge.get_result(task_id)
    """

    AGENT_NAME = "claude"
    PROVIDER_KEY = "claude-code"

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        super().__init__(name=self.PROVIDER_KEY)
        self.router = TaskRouter(root_dir)
        # Track submitted task timings
        self._task_start_times: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # AgentProvider implementation
    # ------------------------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        """Claude Code capabilities."""
        return ProviderCapabilities(
            provider_name=self.name,
            role=ProviderRole.CONSUMER,
            supports_streaming=False,
            supports_batch=False,
            supports_cancellation=True,
            supports_structured_output=True,
            max_context_tokens=200000,
            max_output_tokens=8192,
            default_model="claude-sonnet-4-6",
            description="Claude Code CLI -- file-based task execution via .ai/inbox/",
        )

    def submit_task(
        self,
        task: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Submit a task to Claude Code for execution.

        Creates a BridgeTask and places it in the queue. The actual
        execution happens when Claude Code pulls and processes the
        corresponding .md file from .ai/inbox/.

        Args:
            task: BridgeTask, dict with task spec, or task ID string.
            context: Optional context data to attach.

        Returns:
            The task ID string.
        """
        if isinstance(task, BridgeTask):
            bridge_task = task
            # Ensure it's assigned to claude
            if bridge_task.assigned_to != self.AGENT_NAME:
                bridge_task = BridgeTask(
                    id=bridge_task.id,
                    source=bridge_task.source,
                    assigned_to=self.AGENT_NAME,
                    title=bridge_task.title,
                    module=bridge_task.module,
                    priority=bridge_task.priority,
                    description=bridge_task.description,
                    instructions=bridge_task.instructions,
                    tags=bridge_task.tags,
                    metadata=bridge_task.metadata,
                )
            self.router.update_task(bridge_task)
            task_id = bridge_task.id
        elif isinstance(task, dict):
            bridge_task = self.router.create_task(
                title=task.get("title", "Untitled"),
                source=task.get("source", "manual"),
                assigned_to=self.AGENT_NAME,
                module=task.get("module", ""),
                priority=task.get("priority", "medium"),
                description=task.get("description", ""),
                instructions=task.get("instructions", ""),
                metadata=task.get("metadata", {}),
            )
            task_id = bridge_task.id
        elif isinstance(task, str):
            # Assume it's a pre-existing task ID
            task_id = task
        else:
            raise ValueError(
                f"task must be BridgeTask, dict, or str (task ID), got {type(task).__name__}"
            )

        if context:
            existing = self.router.get_task(task_id)
            if existing:
                existing.metadata["context"] = context
                self.router.update_task(existing)

        self._task_start_times[task_id] = time.perf_counter()
        logger.info(f"ClaudeBridge: submitted task {task_id}")
        return task_id

    def get_status(self, task_id: str) -> TaskStatus:
        """
        Get the current status of a submitted task.

        Maps BridgeTask status strings to TaskStatus enum values.
        """
        task = self.router.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        status_map = {
            "pending": TaskStatus.PENDING,
            "executing": TaskStatus.EXECUTING,
            "done": TaskStatus.DONE,
            "failed": TaskStatus.FAILED,
            "blocked": TaskStatus.BLOCKED,
        }
        return status_map.get(task.status, TaskStatus.PENDING)

    def get_result(self, task_id: str) -> TaskResult:
        """
        Get the result of a completed task.

        Raises RuntimeError if the task is not yet complete.
        """
        task = self.router.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")

        status = self.get_status(task_id)
        if status not in (TaskStatus.DONE, TaskStatus.FAILED):
            raise RuntimeError(
                f"Task '{task_id}' is not complete (status: {status.value})"
            )

        duration_ms = 0.0
        if task_id in self._task_start_times:
            duration_ms = (time.perf_counter() - self._task_start_times[task_id]) * 1000

        return TaskResult(
            task_id=task_id,
            status=status,
            success=(status == TaskStatus.DONE),
            output=task.metadata.get("completion_note", ""),
            data=task.metadata.get("result", {}),
            error=task.metadata.get("error"),
            duration_ms=duration_ms,
            provider_name=self.name,
            completed_at=task.completed_at or "",
        )

    # ------------------------------------------------------------------
    # Optional AgentProvider overrides
    # ------------------------------------------------------------------

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task (only if not yet executing)."""
        task = self.router.get_task(task_id)
        if not task:
            return False
        if task.status == "pending":
            return self.router.delete_task(task_id)
        return False

    def validate_task(self, task: Any) -> bool:
        """Validate that a task can be handled by Claude Code."""
        if isinstance(task, BridgeTask):
            return True
        if isinstance(task, dict):
            return "title" in task or "id" in task
        if isinstance(task, str):
            return bool(task.strip())
        return False

    def health_check(self) -> bool:
        """
        Check Claude Code availability.

        Returns True if the .ai/ tasks directory is writable.
        """
        try:
            self.router.tasks_dir.mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Claude-specific convenience methods (existing API -- unchanged)
    # ------------------------------------------------------------------

    def pull_next_task(self) -> Optional[BridgeTask]:
        """
        Pull the next pending task assigned to Claude.

        Returns the highest-priority, oldest pending task,
        or None if no tasks are available.

        Does NOT change status -- use mark_running() to claim it.
        """
        task = self.router.get_next_task(assigned_to=self.AGENT_NAME)
        if task:
            logger.info(
                f"ClaudeBridge: pulled task {task.id} "
                f"(priority={task.priority}, module={task.module})"
            )
        else:
            logger.debug("ClaudeBridge: no pending tasks")
        return task

    def pull_and_claim(self) -> Optional[BridgeTask]:
        """
        Pull the next task AND immediately mark it as executing.
        Atomic consume operation.
        """
        task = self.pull_next_task()
        if task:
            return self.router.move_to_executing(task.id)
        return None

    def list_my_tasks(self, status: Optional[str] = None) -> List[BridgeTask]:
        """
        List tasks assigned to Claude.

        Args:
            status: Optional status filter (pending, executing, done, failed).
        """
        return self.router.list_tasks(
            status=status,
            assigned_to=self.AGENT_NAME,
        )

    # ------------------------------------------------------------------
    # Lifecycle (existing API -- unchanged)
    # ------------------------------------------------------------------

    def mark_running(self, task_id: str) -> Optional[BridgeTask]:
        """Mark a task as executing (Claude is working on it)."""
        task = self.router.get_task(task_id)
        if not task:
            logger.warning(f"ClaudeBridge: task {task_id} not found")
            return None
        if task.assigned_to != self.AGENT_NAME:
            logger.warning(
                f"ClaudeBridge: task {task_id} is assigned to "
                f"'{task.assigned_to}', not '{self.AGENT_NAME}'"
            )
        return self.router.move_to_executing(task_id)

    def mark_done(
        self,
        task_id: str,
        result: Optional[Dict[str, Any]] = None,
        note: str = "",
    ) -> Optional[BridgeTask]:
        """
        Mark a task as done, optionally with result data.

        Args:
            task_id: The task to complete.
            result: Optional structured result data.
            note: Optional human-readable completion note.

        Returns:
            The updated BridgeTask, or None if not found.
        """
        task = self.router.get_task(task_id)
        if not task:
            logger.warning(f"ClaudeBridge: task {task_id} not found")
            return None

        if result:
            task.metadata["result"] = result
        if note:
            task.metadata["completion_note"] = note

        self.router.update_task(task)
        completed = self.router.move_to_done(task_id)
        if completed:
            logger.info(f"ClaudeBridge: task {task_id} completed")
        return completed

    def mark_failed(self, task_id: str, error: str = "") -> Optional[BridgeTask]:
        """
        Mark a task as failed.

        Args:
            task_id: The failed task.
            error: Description of what went wrong.

        Returns:
            The updated BridgeTask, or None if not found.
        """
        logger.warning(f"ClaudeBridge: task {task_id} failed: {error}")
        return self.router.move_to_failed(task_id, error)

    def mark_blocked(self, task_id: str, reason: str = "") -> Optional[BridgeTask]:
        """
        Mark a task as blocked (cannot proceed without external input).

        Args:
            task_id: The blocked task.
            reason: Why it is blocked.
        """
        return self.router.move_to_blocked(task_id, reason)

    # ------------------------------------------------------------------
    # Query (existing API -- unchanged)
    # ------------------------------------------------------------------

    def pending_count(self) -> int:
        """Number of pending tasks assigned to Claude."""
        return len(self.list_my_tasks(status="pending"))

    def executing_count(self) -> int:
        """Number of tasks Claude is currently executing."""
        return len(self.list_my_tasks(status="executing"))

    def done_count(self) -> int:
        """Number of tasks Claude has completed."""
        return len(self.list_my_tasks(status="done"))

    def status_report(self) -> str:
        """Human-readable status report for Claude's task queue."""
        lines = [
            "=== Claude Bridge Status ===",
            f"  Pending:   {self.pending_count()}",
            f"  Executing: {self.executing_count()}",
            f"  Done:      {self.done_count()}",
            f"  Failed:    {len(self.list_my_tasks(status='failed'))}",
            f"  Blocked:   {len(self.list_my_tasks(status='blocked'))}",
        ]
        return "\n".join(lines)
