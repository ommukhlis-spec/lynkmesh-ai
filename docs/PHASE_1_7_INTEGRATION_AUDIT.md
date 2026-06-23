# Phase 1.7 Integration Audit

## Dependency Map: StorageAdapter Usage

| Component | Uses StorageAdapter? | Status |
|-----------|---------------------|--------|
| `TaskRouter` | **Yes** — `FileStorageAdapter` by default, injectable | Integrated (Phase 1.7) |
| `AgentMemory` | **Yes** — `FileStorageAdapter` by default, injectable | Integrated (Phase 1.6) |
| `MemoryCollector` | **No** — delegates to AgentMemory | N/A (consumer) |
| `KnowledgeBase` | **No** — uses `json.dump` / `json.load` directly | Not yet migrated |
| `DependencyGraph` | **No** — uses `json.dump` / `json.load` directly | Not yet migrated |
| `SemanticGraph` | **No** — uses `json.dump` / `json.load` directly | Not yet migrated |
| `StateStore` | **No** — uses `json.dump` / `json.load` directly | Not yet migrated |
| `InboxManager` | **No** — uses `json.dump` / `json.load` directly | Not yet migrated |

**Why KnowledgeBase, Graph, StateStore are not yet migrated:** These components serialize/deserialize entire objects (not key-value records). They would need a `StorageAdapter.put_all()` / `StorageAdapter.get_all()` bulk API, which is planned for Phase 2. The current `put(key, data)` / `get(key)` API is a natural fit for TaskRouter's record-per-task model and AgentMemory's collection-per-prefix model.

## EventBus Integration

| Event | Emitter | Subscriber | Status |
|-------|---------|-----------|--------|
| `task_created` | TaskRouter.create_task() | MemoryCollector (no-op) | Wired |
| `task_claimed` | TaskRouter.move_to_executing() | MemoryCollector._on_task_claimed() | Wired |
| `task_completed` | TaskRouter.move_to_done() | MemoryCollector._on_task_completed() | Wired |
| `task_failed` | TaskRouter.move_to_failed() | MemoryCollector._on_task_failed() | Wired |
| `task_blocked` | TaskRouter.move_to_blocked() | MemoryCollector._on_task_blocked() | Wired |

**Event emission is opt-in.** If no `EventBus` is passed to `TaskRouter.__init__()`, no events are emitted. The existing API surface is unchanged. Backward compatibility is preserved.

## AgentMemory Auto-Update

| Trigger | Action |
|---------|--------|
| `task_claimed` event | Records start time for duration tracking |
| `task_completed` event | Creates ExecutionRecord(status=done), updates ProviderStats(success), learns TaskPattern(success) |
| `task_failed` event | Creates ExecutionRecord(status=failed), updates ProviderStats(failure), learns TaskPattern(failure) |
| `task_blocked` event | Creates ExecutionRecord(status=blocked) |

**ProviderStats** are updated using exponential moving average for duration (alpha=0.3) and incremental counts for success/failure.

**TaskPatterns** are learned by module prefix + action type (e.g., "auth.service" → pattern_id="auth__refactor"). Success and failure counts are accumulated across all executions for that pattern.

## Event Flow Diagram

```
┌──────────────┐     create_task()      ┌──────────────┐
│              │ ──── task_created ────▶│              │
│  TaskRouter  │                        │   EventBus   │
│              │                        │              │
│  (emitter)   │ move_to_executing()    │  (broker)    │
│              │ ──── task_claimed ────▶│              │
│              │                        │              │
│              │ move_to_done()         │              │
│              │ ──── task_completed ──▶│              │
│              │                        │              │
│              │ move_to_failed()       │              │
│              │ ──── task_failed ─────▶│              │
│              │                        │              │
│              │ move_to_blocked()      │              │
│              │ ──── task_blocked ────▶│              │
└──────────────┘                        └──────┬───────┘
                                              │
                                     subscribes to all 5 events
                                              │
                                              ▼
                                     ┌────────────────┐
                                     │MemoryCollector │
                                     │                │
                                     │ (subscriber)   │
                                     │                │
                                     │ _on_task_*()   │
                                     └───────┬────────┘
                                             │
                               auto-updates │
                                             ▼
                                     ┌────────────────┐
                                     │  AgentMemory   │
                                     │                │
                                     │ patterns/      │
                                     │ providers/     │
                                     │ history/       │
                                     │ decisions/     │
                                     └────────────────┘
```

## Test Coverage

| Test file | Tests | Focus |
|-----------|-------|-------|
| `test_storage_adapter.py` | 16 | StorageAdapter CRUD, SQLite skeleton |
| `test_event_bus.py` | 22 | EventBus publish/subscribe/history |
| `test_agent_memory.py` | 17 | AgentMemory 4-collection CRUD |
| `test_provider_registry.py` | 18 | ProviderRegistry registration/routing |
| `test_agent_provider_contract.py` | 32 | ClaudeBridge/ChatGPTBridge AgentProvider contract |
| `test_bridge_lifecycle.py` | 27 | TaskRouter lifecycle, priority order, provider discovery |
| **`test_integration_phase17.py`** | **19** | **StorageAdapter + EventBus + AgentMemory all wired** |
| **TOTAL** | **157** | **0 failures** |

## Backward Compatibility Verification

- [x] `lynkmesh-ai scan --dir examples/sample_project` — works
- [x] `lynkmesh-ai run --module auth.service --dir examples/sample_project` — works
- [x] `lynkmesh-ai bridge create --title "test"` — works
- [x] `TaskRouter()` without EventBus — no events emitted, no crash
- [x] `TaskRouter()` without explicit StorageAdapter — defaults to FileStorageAdapter
- [x] Existing 138 pre-Phase-1.7 tests still pass
