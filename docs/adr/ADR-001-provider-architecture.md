# ADR-001: Provider Architecture

**Status:** Accepted
**Date:** 2026-06-23
**Deciders:** LynkMesh AI architecture team

## Context

LynkMesh AI needs to orchestrate tasks across multiple AI agents — Claude Code for execution, ChatGPT for architecture analysis, and potentially Anthropic API, OpenAI API, Gemini, DeepSeek, and local Ollama models in the future. Without a provider abstraction, each integration would require bespoke code and the orchestration layer would be tightly coupled to specific vendors.

## Decision

Implement a **provider-agnostic architecture** using the `AgentProvider` abstract base class (ABC). Every AI agent — whether it produces tasks (architect role), consumes tasks (executor role), or both — must implement this interface.

The architecture consists of:

1. **AgentProvider** (`bridges/base.py`) — ABC defining the contract: `capabilities()`, `submit_task()`, `get_status()`, `get_result()`, with optional `cancel_task()`, `validate_task()`, `health_check()`.

2. **ProviderRegistry** (`bridges/registry.py`) — Central registry for discovery, routing, and capability querying. Producers and consumers register by name.

3. **Reference implementations** — `ClaudeBridge` (consumer) and `ChatGPTBridge` (producer) implement `AgentProvider` with full task lifecycle. `ClaudeCodeProvider` wraps `ClaudeBridge` as a registry-compatible provider.

4. **Provider skeletons** — `AnthropicProvider`, `OpenAIProvider`, `GeminiProvider`, `DeepSeekProvider`, `OllamaProvider` document integration points with `NotImplementedError`. No external SDKs imported at module level.

## Rationale

- **Vendor independence.** The orchestration layer routes tasks to `registry.find_consumer()`, never to a hardcoded provider name.
- **Testability.** The ABC enables stub providers for unit testing. The 77-test suite verifies the contract without any real AI agent.
- **Zero-dependency guarantee.** Provider skeletons raise `NotImplementedError` but never import optional SDKs. The registry loads without any provider SDKs installed.
- **Backward compatibility.** `ClaudeBridge.pull_next_task()` and `ChatGPTBridge.create_chatgpt_task()` continue to work. The `AgentProvider` methods are additive.

## Consequences

- **Positive:** Any AI agent can join the bus by implementing 4-7 methods.
- **Positive:** Provider discovery, routing, and capability querying are standardized.
- **Positive:** Skeleton providers serve as living documentation for future integrations.
- **Negative:** The ABC adds abstraction overhead — simple one-off scripts must understand the interface.
- **Negative:** Provider skeletons are dead code until implemented. They exist as documentation and architectural guidance.

## Alternatives Considered

- **Hardcoded Claude Code integration only.** Rejected — limits the framework to a single vendor.
- **Plugin system with entry points.** Rejected — adds complexity; the registry pattern is simpler and sufficient.
- **No ABC — duck typing only.** Rejected — the ABC enforces the contract at import time and enables `isinstance` checks.
