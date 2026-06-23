# Provider Architecture

## Overview

LynkMesh AI is a **provider-agnostic AI orchestration framework**. Any AI agent that implements the `AgentProvider` interface can join the orchestration bus — regardless of vendor, model, or protocol.

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATION BUS                               │
│                                                                      │
│  ┌──────────────────┐                           ┌──────────────────┐ │
│  │   PRODUCERS      │                           │   CONSUMERS      │ │
│  │                  │                           │                  │ │
│  │  ┌────────────┐  │                           │  ┌────────────┐  │ │
│  │  │ ChatGPT    │  │      ┌──────────────┐     │  │ Claude     │  │ │
│  │  │ Bridge     │──┼─────▶│              │─────┼──│ Code       │  │ │
│  │  └────────────┘  │      │  TaskRouter  │     │  └────────────┘  │ │
│  │                  │      │              │     │                  │ │
│  │  ┌────────────┐  │      │ .ai/tasks/   │     │  ┌────────────┐  │ │
│  │  │ OpenAI     │──┼─────▶│   task_*.json│─────┼──│ Anthropic  │  │ │
│  │  │ Provider   │  │      └──────────────┘     │  │ Provider   │  │ │
│  │  └────────────┘  │                           │  └────────────┘  │ │
│  │                  │                           │                  │ │
│  │  ┌────────────┐  │      ┌──────────────┐     │  ┌────────────┐  │ │
│  │  │ Gemini     │──┼─────▶│   Provider   │◀────┼──│ DeepSeek   │  │ │
│  │  │ Provider   │  │      │   Registry   │     │  │ Provider   │  │ │
│  │  └────────────┘  │      └──────────────┘     │  └────────────┘  │ │
│  │                  │                           │                  │ │
│  │  ┌────────────┐  │      Producers create     │  ┌────────────┐  │ │
│  │  │ Ollama     │  │      tasks. Consumers     │  │ Ollama     │  │ │
│  │  │ (Producer) │  │      execute them.        │  │ (Consumer) │  │ │
│  │  └────────────┘  │                           │  └────────────┘  │ │
│  └──────────────────┘                           └──────────────────┘ │
│                                                                      │
│  ProviderRegistry manages discovery, routing, and capability query.  │
└──────────────────────────────────────────────────────────────────────┘
```

## Provider Lifecycle

```
1. REGISTER
   registry.register("openai", OpenAIProvider())

2. DISCOVER
   consumers = registry.list_by_role(ProviderRole.CONSUMER)
   producer = registry.find_producer()

3. SUBMIT
   task_id = provider.submit_task({"title": "...", "module": "..."})
   # Task is now in .ai/tasks/task_xxx.json with status=pending

4. EXECUTE (consumer side)
   task = claude_bridge.pull_next_task()
   claude_bridge.mark_running(task.id)
   # ... AI agent does the work ...
   claude_bridge.mark_done(task.id, result=...)

5. QUERY (producer side)
   status = chatgpt_bridge.get_task_status(task_id)
   result = chatgpt_bridge.get_result(task_id)
```

## Task Flow

```
ChatGPT (architect)                  LynkMesh AI Bus                  Claude Code (executor)
       │                                   │                                │
       │  1. create_chatgpt_task()         │                                │
       ├──────────────────────────────────▶│                                │
       │                                   │  Task created in .ai/tasks/    │
       │                                   │  status=pending                │
       │                                   │                                │
       │                                   │  2. pull_next_task()           │
       │                                   │◀───────────────────────────────┤
       │                                   │                                │
       │                                   │  3. mark_running(task_id)      │
       │                                   │◀───────────────────────────────┤
       │                                   │  status=executing              │
       │                                   │                                │
       │  4. get_task_status(id)           │                                │
       │◀──────────────────────────────────┤  (ChatGPT checks progress)     │
       │                                   │                                │
       │                                   │  5. mark_done(task_id, result) │
       │                                   │◀───────────────────────────────┤
       │                                   │  status=done                   │
       │                                   │                                │
       │  6. get_completed_tasks()         │                                │
       │◀──────────────────────────────────┤  (ChatGPT retrieves results)   │
```

## AgentProvider Interface

Every provider must implement:

```python
class AgentProvider(ABC):
    def capabilities(self) -> ProviderCapabilities: ...
    def submit_task(self, task, context=None) -> str: ...
    def get_status(self, task_id) -> TaskStatus: ...
    def get_result(self, task_id) -> TaskResult: ...

    # Optional overrides
    def cancel_task(self, task_id) -> bool: ...
    def validate_task(self, task) -> bool: ...
    def health_check(self) -> bool: ...
```

## Provider Capabilities

| Provider | Role | Streaming | Max Context | Status |
|----------|------|-----------|-------------|--------|
| `claude-code` | Consumer | No | 200K | **Implemented** |
| `anthropic` | Both | Yes | 200K | Skeleton |
| `openai` | Producer | Yes | 128K | Skeleton |
| `gemini` | Both | Yes | 1M | Skeleton |
| `deepseek` | Producer | No | 65K | Skeleton |
| `ollama` | Both | Yes | Varies | Skeleton |

## Extension Guide

### Adding a New Provider

1. **Create a provider class** in `lynkmesh_ai/bridges/providers/`:

```python
from lynkmesh_ai.bridges.base import (
    AgentProvider, ProviderCapabilities, ProviderRole, TaskStatus, TaskResult
)

class MyProvider(AgentProvider):
    PROVIDER_KEY = "my-provider"

    def __init__(self, **kwargs):
        super().__init__(name=self.PROVIDER_KEY)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name=self.name,
            role=ProviderRole.BOTH,
            default_model="my-model-v1",
            description="My custom AI provider",
        )

    def submit_task(self, task, context=None) -> str:
        # Implement: send task to your AI agent
        ...

    def get_status(self, task_id) -> TaskStatus:
        # Implement: check task status
        ...

    def get_result(self, task_id) -> TaskResult:
        # Implement: retrieve task result
        ...
```

2. **Register it:**

```python
from lynkmesh_ai.bridges.registry import ProviderRegistry
from lynkmesh_ai.bridges.providers.my_provider import MyProvider

registry = ProviderRegistry()
registry.register("my-provider", MyProvider())
```

3. **Use it:**

```python
provider = registry.get("my-provider")
task_id = provider.submit_task({"title": "Fix auth bug"})
result = provider.get_result(task_id)
```

### Design Constraints

- **Zero external dependencies.** Provider skeletons use `NotImplementedError`. When implementing, add SDK imports inside the method or document the dependency in the class docstring.
- **Provider-agnostic routing.** The orchestration layer never hardcodes a provider name. Always use `registry.find_consumer()` or `registry.route_task()`.
- **Backward compatibility.** Existing bridge APIs (ClaudeBridge, ChatGPTBridge) remain unchanged. The AgentProvider interface is additive.
