"""
AgentProvider -- abstract base for all AI agent providers.

Defines the contract that every provider (Claude, ChatGPT, Gemini, etc.)
must implement. This makes LynkMesh AI provider-agnostic -- any AI agent
that implements this interface can participate in the orchestration bus.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Types
# ══════════════════════════════════════════════════════════════════════

class TaskStatus(str, Enum):
    """Canonical task status across all providers."""
    PENDING = "pending"
    EXECUTING = "executing"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ProviderRole(str, Enum):
    """What role does this provider play in the orchestration bus?"""
    PRODUCER = "producer"    # Creates tasks (e.g., ChatGPT architect)
    CONSUMER = "consumer"    # Executes tasks (e.g., Claude Code)
    BOTH = "both"            # Can produce and consume


@dataclass
class TaskResult:
    """Standardized result from any provider's task execution."""

    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    success: bool = False
    output: str = ""                    # Human-readable output
    data: Dict[str, Any] = field(default_factory=dict)  # Structured result
    error: Optional[str] = None         # Error message if failed
    duration_ms: float = 0.0            # Execution time
    provider_name: str = ""             # Which provider produced this result
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "success": self.success,
            "output": self.output,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "provider_name": self.provider_name,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        status_raw = data.get("status", "pending")
        status = TaskStatus(status_raw) if isinstance(status_raw, str) else status_raw
        return cls(
            task_id=data.get("task_id", ""),
            status=status,
            success=data.get("success", False),
            output=data.get("output", ""),
            data=data.get("data", {}),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0.0),
            provider_name=data.get("provider_name", ""),
            completed_at=data.get("completed_at", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ProviderCapabilities:
    """Describes what a provider can and cannot do."""

    provider_name: str
    role: ProviderRole = ProviderRole.CONSUMER
    supports_streaming: bool = False
    supports_batch: bool = False
    supports_cancellation: bool = False
    supports_structured_output: bool = False
    max_context_tokens: int = 0       # 0 = unknown
    max_output_tokens: int = 0        # 0 = unknown
    default_model: str = ""
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "role": self.role.value,
            "supports_streaming": self.supports_streaming,
            "supports_batch": self.supports_batch,
            "supports_cancellation": self.supports_cancellation,
            "supports_structured_output": self.supports_structured_output,
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "default_model": self.default_model,
            "description": self.description,
            "metadata": self.metadata,
        }


# ══════════════════════════════════════════════════════════════════════
# AgentProvider ABC
# ══════════════════════════════════════════════════════════════════════

class AgentProvider(ABC):
    """
    Abstract base for all AI agent providers.

    Every provider -- whether it produces tasks (ChatGPT architect role),
    consumes tasks (Claude Code executor role), or both -- must implement
    this interface.

    This is the contract that makes LynkMesh AI provider-agnostic.
    Any AI agent that implements these methods can join the orchestration bus.

    Subclassing guide:
        1. Override capabilities() to declare what your provider supports
        2. Implement submit_task() for task submission
        3. Implement get_status() and get_result() for task tracking
        4. Override cancel_task() if your provider supports cancellation
        5. Override validate_task() if your provider has special requirements
    """

    def __init__(self, name: str = "") -> None:
        self._name = name or self.__class__.__name__

    @property
    def name(self) -> str:
        """Unique provider name (used as registry key)."""
        return self._name

    # ------------------------------------------------------------------
    # Required interface (all providers MUST implement)
    # ------------------------------------------------------------------

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """
        Return the capabilities of this provider.

        This is used by the orchestration layer to understand what
        this provider can and cannot do. Providers should be honest --
        declaring capabilities they do not support will cause runtime
        failures.

        Returns:
            ProviderCapabilities describing this provider.
        """
        ...

    @abstractmethod
    def submit_task(
        self,
        task: Any,  # BridgeTask or dict
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Submit a task to this provider for execution.

        Args:
            task: The task to execute (BridgeTask or dict with task metadata).
            context: Optional additional context (ContextPackage data, etc.).

        Returns:
            A task ID string that can be used to track execution.

        Raises:
            NotImplementedError: If the provider does not support task submission.
            ValueError: If the task is invalid.
        """
        ...

    @abstractmethod
    def get_status(self, task_id: str) -> TaskStatus:
        """
        Get the current status of a submitted task.

        Args:
            task_id: The task ID returned by submit_task().

        Returns:
            The current TaskStatus.

        Raises:
            KeyError: If the task_id is unknown.
        """
        ...

    @abstractmethod
    def get_result(self, task_id: str) -> TaskResult:
        """
        Get the result of a completed task.

        Args:
            task_id: The task ID returned by submit_task().

        Returns:
            TaskResult with output, data, and status.

        Raises:
            KeyError: If the task_id is unknown.
            RuntimeError: If the task is not yet complete.
        """
        ...

    # ------------------------------------------------------------------
    # Optional interface (providers MAY override)
    # ------------------------------------------------------------------

    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending or executing task.

        The default implementation returns False (cancellation not supported).
        Override this if your provider supports cancellation.

        Args:
            task_id: The task ID to cancel.

        Returns:
            True if the task was cancelled, False otherwise.
        """
        return False

    def validate_task(self, task: Any) -> bool:
        """
        Validate that a task is compatible with this provider.

        Override to enforce provider-specific constraints (e.g., token limits,
        file format requirements, model availability).

        The default implementation accepts all tasks.

        Args:
            task: The task to validate.

        Returns:
            True if the task can be handled by this provider.
        """
        return True

    def health_check(self) -> bool:
        """
        Check whether the provider is available and healthy.

        Override to implement provider-specific health checks (API key
        validation, endpoint reachability, quota status).

        The default implementation returns True (assumed healthy).

        Returns:
            True if the provider is operational.
        """
        return True

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
