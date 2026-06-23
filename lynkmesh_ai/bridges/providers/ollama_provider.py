"""
OllamaProvider -- Local Ollama integration skeleton.

Integrates with locally running Ollama instances for fully offline,
self-hosted AI agent execution. No API keys, no cloud dependencies.

Integration points:
    1. ollama Python SDK or direct HTTP to http://localhost:11434
    2. No API key required (local only)
    3. Model management (pull, list, delete)
    4. Streaming and non-streaming generation
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

# Placeholder -- no external dependencies.
# import ollama  # pip install ollama


class OllamaProvider(AgentProvider):
    """
    Provider for locally running Ollama models.

    Ollama enables fully offline, self-hosted AI agent execution.
    No API keys, no internet required, no usage limits.

    Supported models: llama3.3, mistral, codellama, qwen, deepseek-r1, etc.

    To implement:
        1. Install and run Ollama: https://ollama.com
        2. Pull a model: ollama pull llama3.3
        3. Install the SDK: pip install ollama
        4. Implement submit_task() to call ollama.chat()
        5. No API key needed -- communicates with localhost:11434
    """

    PROVIDER_KEY = "ollama"

    def __init__(self, model: str = "llama3.3", host: str = "http://localhost:11434") -> None:
        super().__init__(name=self.PROVIDER_KEY)
        self.model = model
        self.host = host

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name=self.name,
            role=ProviderRole.BOTH,
            supports_streaming=True,
            supports_batch=False,
            supports_cancellation=True,
            supports_structured_output=False,
            max_context_tokens=0,  # Model-dependent
            max_output_tokens=0,   # Model-dependent
            default_model=self.model,
            description="Ollama -- local, offline, self-hosted AI. No API keys, no cloud.",
        )

    def submit_task(self, task: Any, context: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError(
            "OllamaProvider.submit_task() is not implemented. "
            "Install ollama and pull a model to enable."
        )

    def get_status(self, task_id: str) -> TaskStatus:
        raise NotImplementedError("OllamaProvider.get_status() is not implemented.")

    def get_result(self, task_id: str) -> TaskResult:
        raise NotImplementedError("OllamaProvider.get_result() is not implemented.")

    def cancel_task(self, task_id: str) -> bool:
        """Ollama supports cancellation of in-flight generations."""
        raise NotImplementedError("OllamaProvider.cancel_task() is not implemented.")

    def health_check(self) -> bool:
        """Check if Ollama is running on localhost:11434."""
        raise NotImplementedError("OllamaProvider.health_check() is not implemented.")
