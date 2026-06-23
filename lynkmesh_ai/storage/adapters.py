"""
StorageAdapter -- abstract storage backend with file and SQLite implementations.

Enables swapping storage backends without changing the data layer.
FileStorageAdapter is the current production implementation.
SQLiteStorageAdapter is a skeleton for future embedded database support.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Types
# ══════════════════════════════════════════════════════════════════════

@dataclass
class StorageRecord:
    """A single record stored in any storage backend."""
    key: str
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "data": self.data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StorageRecord":
        return cls(
            key=d.get("key", ""),
            data=d.get("data", {}),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


# ══════════════════════════════════════════════════════════════════════
# Abstract Base
# ══════════════════════════════════════════════════════════════════════

class StorageAdapter(ABC):
    """
    Abstract storage backend.

    Implementations: FileStorageAdapter, SQLiteStorageAdapter.

    This abstraction allows LynkMesh AI to switch between flat-file
    and embedded database storage without changing the data layer.
    """

    @abstractmethod
    def put(self, key: str, data: Dict[str, Any]) -> None:
        """Store a record by key. Overwrites if exists."""
        ...

    @abstractmethod
    def get(self, key: str) -> Optional[StorageRecord]:
        """Retrieve a record by key. Returns None if not found."""
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a record by key. Returns True if deleted."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check whether a record exists."""
        ...

    @abstractmethod
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Total number of records."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all records."""
        ...

    def iter_records(self) -> Iterator[StorageRecord]:
        """Iterate over all records."""
        for key in self.list_keys():
            rec = self.get(key)
            if rec:
                yield rec


# ══════════════════════════════════════════════════════════════════════
# File Storage (current implementation)
# ══════════════════════════════════════════════════════════════════════

class FileStorageAdapter(StorageAdapter):
    """
    JSON file-based storage adapter.

    Each record is stored as a separate .json file in the storage
    directory. This is the current production implementation used
    by TaskRouter, InboxManager, StateStore, and KnowledgeBase.

    Usage:
        adapter = FileStorageAdapter(Path(".ai/storage"))
        adapter.put("task_001", {"title": "Fix bug", "status": "pending"})
        record = adapter.get("task_001")
    """

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.root_dir / f"{safe}.json"

    def put(self, key: str, data: Dict[str, Any]) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get(key)
        record = StorageRecord(
            key=key,
            data=data,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        path = self._key_path(key)
        path.write_text(json.dumps(record.to_dict(), indent=2, default=str), encoding="utf-8")

    def get(self, key: str) -> Optional[StorageRecord]:
        path = self._key_path(key)
        if not path.exists():
            return None
        try:
            return StorageRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Corrupted storage record {key}: {exc}")
            return None

    def delete(self, key: str) -> bool:
        path = self._key_path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self._key_path(key).exists()

    def list_keys(self, prefix: str = "") -> List[str]:
        keys = []
        for p in sorted(self.root_dir.glob("*.json")):
            try:
                record = StorageRecord.from_dict(json.loads(p.read_text(encoding="utf-8")))
                if not prefix or record.key.startswith(prefix):
                    keys.append(record.key)
            except (json.JSONDecodeError, OSError):
                pass
        return keys

    def count(self) -> int:
        return len(list(self.root_dir.glob("*.json")))

    def clear(self) -> None:
        for p in self.root_dir.glob("*.json"):
            p.unlink()

    def __repr__(self) -> str:
        return f"FileStorageAdapter({self.root_dir})"


# ══════════════════════════════════════════════════════════════════════
# SQLite Storage (skeleton for future embedded DB support)
# ══════════════════════════════════════════════════════════════════════

class SQLiteStorageAdapter(StorageAdapter):
    """
    SQLite-based storage adapter skeleton.

    Provides a single-file embedded database backend for production
    deployments that need concurrent access, indexing, or large
    record counts beyond flat-file performance.

    To implement:
        1. Create schema on __init__ (CREATE TABLE IF NOT EXISTS)
        2. Implement put() as INSERT OR REPLACE
        3. Implement get() as SELECT by key
        4. Add index on created_at for time-range queries
        5. Add WAL mode for concurrent reads

    This skeleton demonstrates the interface contract. The actual
    SQLite implementation requires no external dependencies (sqlite3
    is in the Python stdlib).
    """

    TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS storage (
        key TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_storage_created ON storage(created_at);
    CREATE INDEX IF NOT EXISTS idx_storage_updated ON storage(updated_at);
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        # Skeleton: connection is created on first use, not at init time.
        # Uncomment and implement:
        # self._conn = sqlite3.connect(str(self.db_path))
        # self._conn.execute("PRAGMA journal_mode=WAL")
        # self._conn.executescript(self.TABLE_SCHEMA)
        # self._conn.commit()

    def _ensure_connection(self) -> None:
        """Lazy connection. Implement to open on first use."""
        raise NotImplementedError(
            "SQLiteStorageAdapter is a skeleton. "
            "Implement _ensure_connection() to open sqlite3.connect()."
        )

    def put(self, key: str, data: Dict[str, Any]) -> None:
        raise NotImplementedError(
            "SQLiteStorageAdapter.put() is a skeleton. "
            "Implement as: INSERT OR REPLACE INTO storage VALUES (?, ?, ?, ?)"
        )

    def get(self, key: str) -> Optional[StorageRecord]:
        raise NotImplementedError(
            "SQLiteStorageAdapter.get() is a skeleton. "
            "Implement as: SELECT * FROM storage WHERE key = ?"
        )

    def delete(self, key: str) -> bool:
        raise NotImplementedError(
            "SQLiteStorageAdapter.delete() is a skeleton."
        )

    def exists(self, key: str) -> bool:
        raise NotImplementedError(
            "SQLiteStorageAdapter.exists() is a skeleton."
        )

    def list_keys(self, prefix: str = "") -> List[str]:
        raise NotImplementedError(
            "SQLiteStorageAdapter.list_keys() is a skeleton."
        )

    def count(self) -> int:
        raise NotImplementedError(
            "SQLiteStorageAdapter.count() is a skeleton."
        )

    def clear(self) -> None:
        raise NotImplementedError(
            "SQLiteStorageAdapter.clear() is a skeleton."
        )

    def __repr__(self) -> str:
        return f"SQLiteStorageAdapter({self.db_path}) [SKELETON]"
