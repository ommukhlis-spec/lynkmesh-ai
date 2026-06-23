# ADR-002: Storage Architecture

**Status:** Accepted
**Date:** 2026-06-23
**Deciders:** LynkMesh AI architecture team

## Context

LynkMesh AI currently stores all persistent data as flat JSON files — task metadata (`.ai/tasks/task_*.json`), graph cache (`.ai/graph.json`), knowledge base (`.ai/knowledge_base.json`), and state (`.ai/state.json`). This works well for development and small codebases but has known limitations:

- No concurrent access support (file-level reads can race with writes)
- Linear scan for queries (no indexing)
- No transaction support (partial writes possible on crash)
- Scaling bottleneck for large task counts (>10,000 tasks)

As the system evolves toward the Agent Loop Engine (Phase 2), which will persist execution history, provider statistics, and learning data, a more robust storage abstraction is needed.

## Decision

Implement a **StorageAdapter** abstraction (`storage/adapters.py`) with two implementations:

1. **FileStorageAdapter** — Current production backend. Each record is a separate `.json` file. Fully implemented and tested. Used for development and single-user deployments.

2. **SQLiteStorageAdapter** — Skeleton for future embedded database backend. Single-file database with indexed queries, WAL mode for concurrent reads, and ACID transactions. Skeleton only — raises `NotImplementedError` until Phase 2 or later.

Both implement the same `StorageAdapter` ABC: `put()`, `get()`, `delete()`, `exists()`, `list_keys()`, `count()`, `clear()`.

The `AgentMemory` schema (`agents/memory.py`) uses `StorageAdapter` as its backend, making it agnostic to the underlying storage implementation. Four collections are defined:
- `patterns/` — Learned task patterns
- `providers/` — Provider success/failure statistics
- `history/` — Execution cycle records
- `decisions/` — Architecture decision references

## Rationale

- **Gradual migration path.** FileStorageAdapter works today. SQLiteStorageAdapter can be swapped in when needed without changing AgentMemory or any consumer.
- **Zero new dependencies.** `sqlite3` is in the Python stdlib. No ORM, no migration tool, no external database server.
- **Schema flexibility.** The `StorageRecord` format (key → JSON data) is compatible with the existing flat-file pattern — data can be migrated file-by-file.
- **Testability.** The ABC enables a `MemoryStorageAdapter` stub for unit tests (dictionary-backed, zero I/O).

## Consequences

- **Positive:** Storage backend can be swapped without changing any data-layer code.
- **Positive:** SQLite provides indexing, transactions, and concurrent reads for production deployments.
- **Positive:** AgentMemory is backend-agnostic — it works identically with files or SQLite.
- **Negative:** Adding SQLite support later requires implementing all 7 ABC methods (estimated 150 lines).
- **Negative:** The ABC adds one layer of indirection for every `get`/`put` call.

## Alternatives Considered

- **PostgreSQL / external database.** Rejected — violates zero-dependency principle. Would require a running server.
- **No abstraction — always flat files.** Rejected — locks us into the scaling limitations of flat files.
- **Using Python's `shelve` module.** Rejected — `shelve` has known corruption issues on concurrent access.
