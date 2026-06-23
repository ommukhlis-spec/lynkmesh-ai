# ADR-003: Event Bus Architecture

**Status:** Accepted
**Date:** 2026-06-23
**Deciders:** LynkMesh AI architecture team

## Context

As LynkMesh AI grows from a CLI tool into an agent orchestration framework, components need to communicate without direct imports. For example:

- When `TaskRouter` creates a task, `AgentMemory` should record it.
- When `ClaudeBridge` marks a task done, `ProviderRegistry` should update provider statistics.
- When a task fails, the review queue should be notified.

Without an event system, each component would need to import every other component that needs to know about its state changes. This creates a tightly coupled dependency graph that is hard to test and impossible to extend.

## Decision

Implement a **synchronous, in-process EventBus** (`events/bus.py`) with five event types:

1. **TaskCreated** — Emitted when `TaskRouter.create_task()` completes.
2. **TaskClaimed** — Emitted when a consumer marks a task as executing.
3. **TaskCompleted** — Emitted when a task finishes successfully.
4. **TaskFailed** — Emitted when a task fails.
5. **TaskBlocked** — Emitted when a task is blocked.

The EventBus is:
- **Synchronous.** Handlers are called immediately when an event is published. This keeps the mental model simple — no async, no threads, no message queues.
- **In-process.** No external broker (no Redis, no Kafka). This preserves the zero-dependency guarantee.
- **Fire-and-continue.** If a handler raises an exception, it is logged and the remaining handlers continue. One misbehaving handler cannot break the system.
- **Ring-buffered history.** The last 1,000 events are retained for debugging and replay.

Convenience methods are provided: `bus.task_created(task_id, source, **data)` wraps `bus.publish(Event(...))`.

## Rationale

- **Decoupled communication.** `TaskRouter` does not import `AgentMemory`. `AgentMemory` subscribes to `TaskCreated` events. They are connected through the bus, not through imports.
- **Testability.** In tests, you create a fresh `EventBus`, subscribe a spy handler, publish an event, and assert the spy was called. No mocking, no patching.
- **Extensibility.** Adding a new subscriber requires zero changes to the publisher. Add a new handler to `EventBus.subscribe()` and it receives all events of that type.
- **Observability.** The event history provides an audit trail. `bus.history(EventType.TASK_FAILED, limit=10)` answers "what were the last 10 failures?"
- **Zero dependencies.** The implementation uses only Python stdlib: `dataclasses`, `enum`, `logging`, `uuid`.

## Consequences

- **Positive:** Components communicate through a shared bus, not direct imports.
- **Positive:** Event history provides an audit trail for debugging.
- **Positive:** New subscribers can be added without modifying publishers.
- **Negative:** Synchronous execution means slow handlers block the publisher. This is intentional for Phase 1.6 — the Agent Loop Engine (Phase 2) can introduce async dispatch if needed.
- **Negative:** Event ordering is guaranteed within a single publish call, but not across concurrent publishers (not yet relevant — single-threaded CLI).
- **Negative:** The event history is in-memory only. It does not survive process restart. Persistent event storage is a Phase 2 concern.

## Alternatives Considered

- **Asyncio-based event loop.** Rejected — adds complexity without a clear need. The CLI is synchronous.
- **External message broker (Redis, RabbitMQ).** Rejected — violates zero-dependency principle.
- **No event system — direct imports.** Rejected — the current architecture already shows this pattern becoming unwieldy.
- **Observer pattern on each component.** Rejected — each component would need its own subscription management, duplicating code.
