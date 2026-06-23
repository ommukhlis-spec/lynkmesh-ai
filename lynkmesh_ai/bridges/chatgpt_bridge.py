"""
ChatGPTBridge -- ChatGPT-facing bridge interface.

Provides the API that ChatGPT (or any LLM-based task generator)
would use to create tasks on the LynkMesh AI bus for Claude Code
to execute.

This bridge is the "producer side" -- it creates tasks sourced
from ChatGPT and checks their execution status.

Implements AgentProvider for provider-agnostic orchestration.
"""

from __future__ import annotations

import logging
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
from lynkmesh_ai.context.schema import ContextPackage

logger = logging.getLogger(__name__)


class ChatGPTBridge(AgentProvider):
    """
    Bridge interface for ChatGPT task creation.

    Implements AgentProvider -- can be registered in ProviderRegistry
    and used through the provider-agnostic orchestration API.

    Usage (from ChatGPT's perspective):
        bridge = ChatGPTBridge()
        task = bridge.create_chatgpt_task(
            title="Refactor auth.service to use dependency injection",
            module="auth.service",
            context=context_package,
        )
        # ... later ...
        status = bridge.get_task_status(task.id)
        completed = bridge.get_completed_tasks()

    Usage (provider-agnostic):
        bridge = ChatGPTBridge()
        task_id = bridge.submit_task({"title": "Fix auth bug", "module": "auth"})
        result = bridge.get_result(task_id)
    """

    AGENT_NAME = "chatgpt"
    PROVIDER_KEY = "chatgpt"

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        super().__init__(name=self.PROVIDER_KEY)
        self.router = TaskRouter(root_dir)

    # ------------------------------------------------------------------
    # AgentProvider implementation
    # ------------------------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        """ChatGPT (architect role) capabilities."""
        return ProviderCapabilities(
            provider_name=self.name,
            role=ProviderRole.PRODUCER,
            supports_streaming=False,
            supports_batch=True,
            supports_cancellation=True,
            supports_structured_output=True,
            max_context_tokens=128000,
            max_output_tokens=16384,
            default_model="gpt-4o",
            description="ChatGPT architect -- generates tasks from code analysis and architecture reasoning",
        )

    def submit_task(
        self,
        task: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Submit a task created by ChatGPT to the orchestration bus.

        The task is created with source='chatgpt' and assigned_to='claude'.

        Args:
            task: Dict with task spec (title, module, priority, etc.) or BridgeTask.
            context: Optional context data (ContextPackage, analysis results).

        Returns:
            The task ID string.
        """
        if isinstance(task, BridgeTask):
            bridge_task = task
            if bridge_task.source != self.AGENT_NAME:
                bridge_task = BridgeTask(
                    id=bridge_task.id,
                    source=self.AGENT_NAME,
                    assigned_to="claude",
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
            meta = task.get("metadata", {})
            if context:
                meta["context"] = context
            bridge_task = self.router.create_task(
                title=task.get("title", "Untitled"),
                source=self.AGENT_NAME,
                assigned_to="claude",
                module=task.get("module", ""),
                priority=task.get("priority", "medium"),
                description=task.get("description", ""),
                instructions=task.get("instructions", ""),
                tags=task.get("tags", []),
                metadata=meta,
            )
            task_id = bridge_task.id
        elif isinstance(task, str):
            task_id = task
        else:
            raise ValueError(
                f"task must be BridgeTask, dict, or str (task ID), got {type(task).__name__}"
            )
        logger.info(f"ChatGPTBridge: submitted task {task_id}")
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

        return TaskResult(
            task_id=task_id,
            status=status,
            success=(status == TaskStatus.DONE),
            output=task.metadata.get("completion_note", ""),
            data=task.metadata.get("result", {}),
            error=task.metadata.get("error"),
            provider_name=self.name,
            completed_at=task.completed_at or "",
        )

    # ------------------------------------------------------------------
    # Optional AgentProvider overrides
    # ------------------------------------------------------------------

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel (delete) a pending task that hasn't been picked up yet.

        Overrides AgentProvider.cancel_task().
        """
        task = self.router.get_task(task_id)
        if not task:
            return False
        if task.status != "pending":
            return False
        return self.router.delete_task(task_id)

    # ------------------------------------------------------------------
    # ChatGPT-specific convenience methods (existing API -- unchanged)
    # ------------------------------------------------------------------

    def create_chatgpt_task(
        self,
        title: str,
        module: str = "",
        priority: str = "medium",
        description: str = "",
        instructions: str = "",
        context: Optional[ContextPackage] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BridgeTask:
        """
        Create a task sourced from ChatGPT, assigned to Claude.

        Args:
            title: Short task title (required).
            module: Target module name.
            priority: critical, high, medium, low.
            description: Human-readable description of what to do.
            instructions: Step-by-step execution instructions for Claude.
            context: Optional ContextPackage with code analysis data.
            tags: Categorization tags.
            metadata: Arbitrary extra data.

        Returns:
            The created BridgeTask.
        """
        task_metadata = metadata or {}

        # If a ContextPackage is provided, embed relevant data
        if context:
            task_metadata["context"] = {
                "module": context.module,
                "file_count": context.file_count,
                "dependency_count": context.dependency_count,
                "risk_score": context.risk_score,
                "architectural_role": context.architectural_role,
                "design_patterns": context.design_patterns,
            }

        task = self.router.create_task(
            title=title,
            source=self.AGENT_NAME,
            assigned_to="claude",
            module=module,
            priority=priority,
            description=description,
            instructions=instructions,
            tags=tags or [],
            metadata=task_metadata,
        )

        logger.info(
            f"ChatGPTBridge: created task {task.id} "
            f"for module '{module}' (priority={priority})"
        )
        return task

    def create_batch_from_analysis(
        self,
        recommendations: List[Dict[str, Any]],
        module: str = "",
    ) -> List[BridgeTask]:
        """
        Create multiple tasks from a list of recommendations.

        Each recommendation dict should have:
            title, priority, description, instructions (optional)

        Args:
            recommendations: List of recommendation dicts (e.g., from DecisionEngine).
            module: Default module name if not specified per recommendation.

        Returns:
            List of created BridgeTask objects.
        """
        created: List[BridgeTask] = []
        for rec in recommendations:
            task = self.create_chatgpt_task(
                title=rec.get("title", "Untitled task"),
                module=rec.get("module", module),
                priority=rec.get("priority", "medium"),
                description=rec.get("description", rec.get("rationale", "")),
                instructions=rec.get("instructions", ""),
                tags=rec.get("tags", []),
            )
            created.append(task)
        return created

    # ------------------------------------------------------------------
    # Status queries (existing API -- unchanged)
    # ------------------------------------------------------------------

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current status of a task ChatGPT created.

        Returns a dict with id, status, and result (if done).
        Note: This is the ChatGPT-specific status method.
        Use AgentProvider.get_result() for the provider-agnostic equivalent.
        """
        task = self.router.get_task(task_id)
        if not task:
            return None

        result: Dict[str, Any] = {
            "id": task.id,
            "status": task.status,
            "title": task.title,
            "module": task.module,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
        }

        if task.status == "done" and "result" in task.metadata:
            result["result"] = task.metadata["result"]
        if task.status == "failed" and "error" in task.metadata:
            result["error"] = task.metadata["error"]

        return result

    def get_my_tasks(self, status: Optional[str] = None) -> List[BridgeTask]:
        """
        List tasks created by ChatGPT.

        Args:
            status: Optional status filter.
        """
        return self.router.list_tasks(
            status=status,
            source=self.AGENT_NAME,
        )

    def get_completed_tasks(self) -> List[BridgeTask]:
        """
        Get all tasks ChatGPT created that have been completed by Claude.
        """
        return self.router.list_tasks(status="done", source=self.AGENT_NAME)

    def get_pending_tasks(self) -> List[BridgeTask]:
        """
        Get all tasks ChatGPT created that are still pending execution.
        """
        return self.router.list_tasks(status="pending", source=self.AGENT_NAME)

    def get_failed_tasks(self) -> List[BridgeTask]:
        """
        Get all tasks ChatGPT created that failed during execution.
        """
        return self.router.list_tasks(status="failed", source=self.AGENT_NAME)

    # ------------------------------------------------------------------
    # Task management (existing API -- unchanged)
    # ------------------------------------------------------------------

    def update_instructions(self, task_id: str, instructions: str) -> Optional[BridgeTask]:
        """
        Update the instructions for a pending task.

        Only works if the task is still pending.
        """
        task = self.router.get_task(task_id)
        if not task:
            return None
        if task.status != "pending":
            logger.warning(
                f"ChatGPTBridge: cannot update task {task_id} "
                f"with status '{task.status}' -- must be pending"
            )
            return None
        if task.source != self.AGENT_NAME:
            logger.warning(
                f"ChatGPTBridge: task {task_id} was created by "
                f"'{task.source}', not '{self.AGENT_NAME}'"
            )
        task.instructions = instructions
        self.router.update_task(task)
        return task

    # ------------------------------------------------------------------
    # Reporting (existing API -- unchanged)
    # ------------------------------------------------------------------

    def status_report(self) -> str:
        """Human-readable status report for ChatGPT's created tasks."""
        my_tasks = self.get_my_tasks()
        counts: Dict[str, int] = {}
        for t in my_tasks:
            counts[t.status] = counts.get(t.status, 0) + 1

        lines = [
            "=== ChatGPT Bridge Status ===",
            f"  Tasks Created: {len(my_tasks)}",
            f"  Pending:       {counts.get('pending', 0)}",
            f"  Executing:     {counts.get('executing', 0)}",
            f"  Done:          {counts.get('done', 0)}",
            f"  Failed:        {counts.get('failed', 0)}",
            f"  Blocked:       {counts.get('blocked', 0)}",
        ]
        return "\n".join(lines)
