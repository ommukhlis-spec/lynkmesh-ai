"""Storage layer — persistent state management for LynkMesh AI."""

from lynkmesh_ai.storage.state import StateStore
from lynkmesh_ai.storage.adapters import (
    StorageAdapter, StorageRecord,
    FileStorageAdapter, SQLiteStorageAdapter,
)

__all__ = [
    "StateStore",
    "StorageAdapter",
    "StorageRecord",
    "FileStorageAdapter",
    "SQLiteStorageAdapter",
]
