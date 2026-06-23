"""
ProviderRegistry -- central registry for all AgentProvider implementations.

Enables LynkMesh AI to discover, register, and route tasks to any
provider that implements the AgentProvider interface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

from lynkmesh_ai.bridges.base import AgentProvider, ProviderCapabilities, ProviderRole

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Central registry of all AgentProvider implementations.

    The registry is a singleton-like key-value store mapping provider
    names to AgentProvider instances. It supports registration,
    lookup, and enumeration.

    Usage:
        registry = ProviderRegistry()
        registry.register("claude-code", ClaudeCodeProvider())
        registry.register("chatgpt", ChatGPTProvider())

        provider = registry.get("claude-code")
        all_providers = registry.list()
        consumers = registry.list_by_role(ProviderRole.CONSUMER)
    """

    def __init__(self) -> None:
        self._providers: Dict[str, AgentProvider] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, provider: AgentProvider) -> None:
        """
        Register a provider under a given name.

        If a provider with the same name already exists, it is replaced
        and a warning is logged.

        Args:
            name: Unique name for this provider (e.g., "claude-code").
            provider: An AgentProvider instance.
        """
        if name in self._providers:
            logger.warning(
                f"Provider '{name}' is already registered "
                f"({type(self._providers[name]).__name__}). Replacing."
            )
        self._providers[name] = provider
        logger.info(f"Provider registered: {name} ({type(provider).__name__})")

    def unregister(self, name: str) -> bool:
        """
        Remove a provider from the registry.

        Returns:
            True if the provider was removed, False if it wasn't found.
        """
        if name in self._providers:
            del self._providers[name]
            logger.info(f"Provider unregistered: {name}")
            return True
        return False

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[AgentProvider]:
        """
        Get a registered provider by name.

        Returns:
            The AgentProvider instance, or None if not registered.
        """
        return self._providers.get(name)

    def __getitem__(self, name: str) -> AgentProvider:
        """Dict-style access. Raises KeyError if not found."""
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' is not registered")
        return self._providers[name]

    def __contains__(self, name: str) -> bool:
        return name in self._providers

    # ------------------------------------------------------------------
    # Enumeration
    # ------------------------------------------------------------------

    def list(self) -> List[str]:
        """
        Return all registered provider names, sorted alphabetically.
        """
        return sorted(self._providers.keys())

    def list_all(self) -> List[AgentProvider]:
        """
        Return all registered provider instances.
        """
        return list(self._providers.values())

    def iter_providers(self) -> Iterator[AgentProvider]:
        yield from self._providers.values()

    def list_by_role(self, role: ProviderRole) -> List[str]:
        """
        List providers that match a given role (producer, consumer, both).

        Args:
            role: The ProviderRole to filter by.

        Returns:
            Sorted list of provider names with the given role.
        """
        result: List[str] = []
        for name, provider in self._providers.items():
            caps = provider.capabilities()
            if caps.role == role or caps.role == ProviderRole.BOTH:
                result.append(name)
        return sorted(result)

    def get_capabilities(self, name: str) -> Optional[ProviderCapabilities]:
        """
        Get the capabilities of a registered provider.

        Returns:
            ProviderCapabilities, or None if provider not found.
        """
        provider = self.get(name)
        if provider:
            return provider.capabilities()
        return None

    def get_all_capabilities(self) -> Dict[str, ProviderCapabilities]:
        """
        Get capabilities for all registered providers.

        Returns:
            Dict mapping provider name to ProviderCapabilities.
        """
        return {
            name: provider.capabilities()
            for name, provider in self._providers.items()
        }

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def find_consumer(self) -> Optional[AgentProvider]:
        """
        Find the first registered consumer provider.

        Returns:
            An AgentProvider with role CONSUMER or BOTH, or None.
        """
        for provider in self._providers.values():
            caps = provider.capabilities()
            if caps.role in (ProviderRole.CONSUMER, ProviderRole.BOTH):
                return provider
        return None

    def find_producer(self) -> Optional[AgentProvider]:
        """
        Find the first registered producer provider.

        Returns:
            An AgentProvider with role PRODUCER or BOTH, or None.
        """
        for provider in self._providers.values():
            caps = provider.capabilities()
            if caps.role in (ProviderRole.PRODUCER, ProviderRole.BOTH):
                return provider
        return None

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route_task(self, task: Any, preferred_provider: Optional[str] = None) -> Optional[str]:
        """
        Route a task to an appropriate provider.

        If preferred_provider is specified and registered, use it.
        Otherwise, find the first consumer provider.

        Args:
            task: The task to route (BridgeTask or dict).
            preferred_provider: Optional provider name to prefer.

        Returns:
            The provider name that was selected, or None if no suitable provider.
        """
        if preferred_provider and preferred_provider in self._providers:
            return preferred_provider

        consumer = self.find_consumer()
        if consumer:
            return consumer.name

        logger.warning("No consumer provider registered -- task cannot be routed")
        return None

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Number of registered providers."""
        return len(self._providers)

    def report(self) -> str:
        """Human-readable registry report."""
        if not self._providers:
            return "No providers registered."

        lines = ["Available Providers", "-------------------"]
        for name in self.list():
            caps = self.get_capabilities(name)
            if caps:
                role_icon = {
                    ProviderRole.PRODUCER: "[P]",
                    ProviderRole.CONSUMER: "[C]",
                    ProviderRole.BOTH: "[B]",
                }.get(caps.role, "[?]")
                lines.append(
                    f"  {role_icon} {name:20s}  "
                    f"model={caps.default_model or 'N/A':12s}  "
                    f"{caps.description[:60]}"
                )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Serialization (capabilities snapshot only -- providers are not serializable)
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Export all provider capabilities as a dict."""
        return {
            name: caps.to_dict()
            for name, caps in self.get_all_capabilities().items()
        }
