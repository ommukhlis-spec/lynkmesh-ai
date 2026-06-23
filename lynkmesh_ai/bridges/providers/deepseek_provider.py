"""
DeepSeekProvider -- DeepSeek API integration skeleton.

Integrates with the DeepSeek API (deepseek-chat, deepseek-reasoner).
DeepSeek's key differentiator is its reasoning models that expose
chain-of-thought for complex architecture analysis.

Integration points:
    1. OpenAI-compatible SDK (DeepSeek API is OpenAI-format)
    2. API key from DEEPSEEK_API_KEY env var
    3. Base URL: https://api.deepseek.com
    4. Reasoning models for architecture decision support
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
# from openai import OpenAI  # DeepSeek uses OpenAI-compatible SDK


class DeepSeekProvider(AgentProvider):
    """
    Provider for the DeepSeek API.

    DeepSeek's reasoning models (deepseek-reasoner) expose internal
    chain-of-thought, making them well-suited for architecture reasoning
    and complex decision-making tasks.

    To implement:
        1. Use the OpenAI SDK with base_url="https://api.deepseek.com"
        2. Set DEEPSEEK_API_KEY environment variable
        3. Use deepseek-reasoner for architecture analysis tasks
        4. Use deepseek-chat for general task generation
    """

    PROVIDER_KEY = "deepseek"

    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat") -> None:
        super().__init__(name=self.PROVIDER_KEY)
        self.api_key = api_key
        self.model = model

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name=self.name,
            role=ProviderRole.PRODUCER,
            supports_streaming=False,
            supports_batch=False,
            supports_cancellation=False,
            supports_structured_output=True,
            max_context_tokens=65536,
            max_output_tokens=8192,
            default_model=self.model,
            description="DeepSeek API -- reasoning models for architecture analysis (OpenAI-compatible)",
        )

    def submit_task(self, task: Any, context: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError(
            "DeepSeekProvider.submit_task() is not implemented. "
            "Install openai SDK (pip install openai) and use base_url='https://api.deepseek.com' to enable."
        )

    def get_status(self, task_id: str) -> TaskStatus:
        raise NotImplementedError("DeepSeekProvider.get_status() is not implemented.")

    def get_result(self, task_id: str) -> TaskResult:
        raise NotImplementedError("DeepSeekProvider.get_result() is not implemented.")

    def health_check(self) -> bool:
        raise NotImplementedError("DeepSeekProvider.health_check() is not implemented.")
