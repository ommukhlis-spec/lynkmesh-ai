"""Bridge layer -- provider-agnostic AI agent orchestration bus."""

from lynkmesh_ai.bridges.claude_task import ClaudeTaskGenerator
from lynkmesh_ai.bridges.inbox import InboxManager
from lynkmesh_ai.bridges.task_router import TaskRouter, BridgeTask
from lynkmesh_ai.bridges.claude_bridge import ClaudeBridge
from lynkmesh_ai.bridges.chatgpt_bridge import ChatGPTBridge
from lynkmesh_ai.bridges.base import AgentProvider, TaskResult, ProviderCapabilities, TaskStatus, ProviderRole
from lynkmesh_ai.bridges.registry import ProviderRegistry

__all__ = [
    "ClaudeTaskGenerator",
    "InboxManager",
    "TaskRouter",
    "BridgeTask",
    "ClaudeBridge",
    "ChatGPTBridge",
    "AgentProvider",
    "TaskResult",
    "ProviderCapabilities",
    "TaskStatus",
    "ProviderRole",
    "ProviderRegistry",
]
