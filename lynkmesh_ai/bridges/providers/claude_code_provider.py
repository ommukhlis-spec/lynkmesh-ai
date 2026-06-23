"""
ClaudeCodeProvider -- Claude Code CLI integration skeleton.

Wraps the Claude Code CLI as an AgentProvider. This is the bridge
between LynkMesh AI's orchestration bus and the Claude Code execution
engine that processes .ai/inbox/task_*.md files.

This provider is the reference consumer implementation. It delegates
to ClaudeBridge internally -- no NotImplementedError here because
the ClaudeBridge is already fully implemented.

Integration points (already implemented via ClaudeBridge):
    1. Task files written to .ai/inbox/ as Markdown
    2. Claude Code CLI monitors .ai/inbox/ for new tasks
    3. Tasks move through inbox -> executing -> done lifecycle
    4. Results captured from Claude Code output
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from lynkmesh_ai.bridges.base import (
    AgentProvider,
    ProviderCapabilities,
    ProviderRole,
    TaskStatus,
    TaskResult,
)
from lynkmesh_ai.bridges.claude_bridge import ClaudeBridge


class ClaudeCodeProvider(AgentProvider):
    """
    Provider for Claude Code CLI -- the reference consumer implementation.

    Unlike the other provider skeletons, this provider is FULLY FUNCTIONAL.
    It delegates to ClaudeBridge, which implements the complete task
    lifecycle using the .ai/inbox/ file-based protocol.

    This is the default execution engine for tasks on the LynkMesh AI bus.

    Usage:
        provider = ClaudeCodeProvider()
        registry.register("claude-code", provider)

        # Provider-agnostic API
        task_id = provider.submit_task({"title": "Fix auth bug"})
        status = provider.get_status(task_id)
        result = provider.get_result(task_id)
    """

    PROVIDER_KEY = "claude-code"

    def __init__(self, root_dir: Optional[str] = None) -> None:
        super().__init__(name=self.PROVIDER_KEY)
        from pathlib import Path
        self._bridge = ClaudeBridge(Path(root_dir) if root_dir else None)

    def capabilities(self) -> ProviderCapabilities:
        """Claude Code CLI capabilities (fully implemented)."""
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
            description="Claude Code CLI -- file-based task execution via .ai/inbox/ (FULLY IMPLEMENTED)",
        )

    def submit_task(self, task: Any, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Submit a task to Claude Code for execution.

        Delegates to ClaudeBridge.submit_task(). This is fully functional
        -- tasks are written to .ai/tasks/ as JSON and queued for Claude Code.
        """
        return self._bridge.submit_task(task, context)

    def get_status(self, task_id: str) -> TaskStatus:
        """
        Get the current status of a task.

        Delegates to ClaudeBridge.get_status(). Fully functional.
        """
        return self._bridge.get_status(task_id)

    def get_result(self, task_id: str) -> TaskResult:
        """
        Get the result of a completed task.

        Delegates to ClaudeBridge.get_result(). Fully functional.
        """
        return self._bridge.get_result(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task. Fully functional."""
        return self._bridge.cancel_task(task_id)

    def validate_task(self, task: Any) -> bool:
        """Validate task for Claude Code. Fully functional."""
        return self._bridge.validate_task(task)

    def health_check(self) -> bool:
        """Check .ai/ directory writability. Fully functional."""
        return self._bridge.health_check()

    # ------------------------------------------------------------------
    # Claude Code-specific convenience (delegated)
    # ------------------------------------------------------------------

    def pull_next_task(self):
        """Pull the next pending task. Delegates to ClaudeBridge."""
        return self._bridge.pull_next_task()

    def pull_and_claim(self):
        """Pull and claim next task. Delegates to ClaudeBridge."""
        return self._bridge.pull_and_claim()

    def status_report(self) -> str:
        """Human-readable status. Delegates to ClaudeBridge."""
        return self._bridge.status_report()
