"""
TaskRouter -- core task lifecycle engine.

Manages the structured metadata layer for bridge tasks.
Each task has a JSON metadata record in .ai/tasks/ and a
corresponding Markdown task file in .ai/inbox/.

Schema:
{
  "id": "task_001",
  "source": "chatgpt",
  "assigned_to": "claude",
  "status": "pending",
  "created_at": "2026-06-23T...",
  "completed_at": null,
  "title": "",
  "module": "",
  "priority": "medium",
  "metadata": {}
}
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from lynkmesh_ai.storage.adapters import StorageAdapter, FileStorageAdapter

logger = logging.getLogger(__name__)

# Optional EventBus import — only used if injected
try:
    from lynkmesh_ai.events.bus import EventBus, EventType
    _HAS_EVENTS = True
except ImportError:
    _HAS_EVENTS = False

# Valid statuses and sources
VALID_STATUSES = {"pending", "executing", "done", "failed", "blocked"}
VALID_SOURCES = {"chatgpt", "claude", "manual", "lynkmesh"}
VALID_TARGETS = {"claude", "chatgpt", "manual", "lynkmesh"}


@dataclass
class BridgeTask:
    """Metadata for a single bridge task."""

    id: str
    source: str = "manual"             # Who created this task
    assigned_to: str = "claude"        # Who should execute it
    status: str = "pending"            # pending, executing, done, failed, blocked
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    title: str = ""
    module: str = ""
    priority: str = "medium"           # critical, high, medium, low
    description: str = ""
    instructions: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of {VALID_STATUSES}")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"Invalid source '{self.source}'. Must be one of {VALID_SOURCES}")
        if self.assigned_to not in VALID_TARGETS:
            raise ValueError(f"Invalid assigned_to '{self.assigned_to}'. Must be one of {VALID_TARGETS}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "assigned_to": self.assigned_to,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "title": self.title,
            "module": self.module,
            "priority": self.priority,
            "description": self.description,
            "instructions": self.instructions,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BridgeTask":
        fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**fields)

    @classmethod
    def from_json(cls, json_str: str) -> "BridgeTask":
        return cls.from_dict(json.loads(json_str))


class TaskRouter:
    """
    Core task lifecycle engine for the agent bridge layer.

    Manages structured task metadata in .ai/tasks/*.json,
    synchronized with Markdown task files in .ai/inbox/.

    Usage:
        router = TaskRouter(root_dir)
        task = router.create_task(source="chatgpt", assigned_to="claude", title="Fix auth bug")
        router.move_to_executing(task.id)
        router.move_to_done(task.id)
    """

    def __init__(
        self,
        root_dir: Optional[Path] = None,
        storage: Optional[StorageAdapter] = None,
        event_bus: Any = None,
    ) -> None:
        self.root_dir = Path(root_dir or Path.cwd() / ".ai")
        self.tasks_dir = self.root_dir / "tasks"
        self._ensure_dirs()
        # Storage backend (defaults to FileStorageAdapter for backward compat)
        self.storage = storage or FileStorageAdapter(self.tasks_dir)
        # Optional EventBus for lifecycle events
        self._bus = event_bus
        if self._bus and not _HAS_EVENTS:
            logger.warning("EventBus provided but events module not available")

    def _ensure_dirs(self) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def task_file(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_task(
        self,
        title: str = "",
        source: str = "manual",
        assigned_to: str = "claude",
        module: str = "",
        priority: str = "medium",
        description: str = "",
        instructions: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BridgeTask:
        """
        Create a new bridge task.

        Args:
            title: Short task title.
            source: Who created this task (chatgpt, claude, manual, lynkmesh).
            assigned_to: Who should execute it (claude, chatgpt, manual).
            module: Target module name.
            priority: critical, high, medium, low.
            description: Longer description.
            instructions: Execution instructions.
            tags: List of tags for categorization.
            metadata: Arbitrary extra data.

        Returns:
            The created BridgeTask.
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = BridgeTask(
            id=task_id,
            source=source,
            assigned_to=assigned_to,
            status="pending",
            title=title,
            module=module,
            priority=priority,
            description=description,
            instructions=instructions,
            tags=tags or [],
            metadata=metadata or {},
        )
        self._save_task(task)
        logger.info(f"Task created: {task_id} (source={source}, assigned_to={assigned_to})")
        self._emit("task_created", task_id, source=source, assigned_to=assigned_to,
                   module=module, priority=priority)
        return task

    def get_task(self, task_id: str) -> Optional[BridgeTask]:
        """Retrieve a task by ID (storage adapter first, legacy file fallback)."""
        # Try storage adapter first
        rec = self.storage.get(task_id)
        if rec and rec.data:
            try:
                return BridgeTask.from_dict(rec.data)
            except (ValueError, KeyError) as exc:
                logger.warning(f"Storage record for {task_id} corrupted: {exc}")
        # Fall back to legacy JSON file
        legacy_path = self.tasks_dir / f"{task_id}_legacy.json"
        if legacy_path.exists():
            try:
                return BridgeTask.from_json(legacy_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                logger.error(f"Failed to read legacy task {task_id}: {exc}")
        return None

    def update_task(self, task: BridgeTask) -> None:
        """Persist updated task metadata."""
        self._save_task(task)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task from storage and legacy files."""
        deleted = self.storage.delete(task_id)
        legacy_path = self.tasks_dir / f"{task_id}_legacy.json"
        if legacy_path.exists():
            legacy_path.unlink()
            deleted = True
        if deleted:
            logger.info(f"Task deleted: {task_id}")
        return deleted

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def move_to_executing(self, task_id: str) -> Optional[BridgeTask]:
        """Mark a task as executing."""
        task = self._transition(task_id, "executing")
        if task:
            self._emit("task_claimed", task_id,
                       provider=task.assigned_to, module=task.module,
                       source=task.source)
        return task

    def move_to_done(self, task_id: str) -> Optional[BridgeTask]:
        """Mark a task as done."""
        task = self._transition(task_id, "done")
        if task:
            task.completed_at = datetime.now(timezone.utc).isoformat()
            self._save_task(task)
            self._emit("task_completed", task_id,
                       provider=task.assigned_to, module=task.module,
                       source=task.source, priority=task.priority)
        return task

    def move_to_failed(self, task_id: str, error: str = "") -> Optional[BridgeTask]:
        """Mark a task as failed with an error message."""
        task = self._transition(task_id, "failed")
        if task:
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.metadata["error"] = error
            self._save_task(task)
            self._emit("task_failed", task_id,
                       error=error, provider=task.assigned_to, module=task.module,
                       source=task.source, priority=task.priority)
        return task

    def move_to_blocked(self, task_id: str, reason: str = "") -> Optional[BridgeTask]:
        """Mark a task as blocked with a reason."""
        task = self._transition(task_id, "blocked")
        if task:
            task.metadata["blocked_reason"] = reason
            self._save_task(task)
            self._emit("task_blocked", task_id,
                       reason=reason, provider=task.assigned_to, module=task.module,
                       source=task.source)
        return task

    def _transition(self, task_id: str, new_status: str) -> Optional[BridgeTask]:
        """Internal state transition."""
        task = self.get_task(task_id)
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return None
        task.status = new_status
        self._save_task(task)
        logger.info(f"Task {task_id}: pending -> {new_status}")
        return task

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_tasks(
        self,
        status: Optional[str] = None,
        source: Optional[str] = None,
        assigned_to: Optional[str] = None,
        module: Optional[str] = None,
    ) -> List[BridgeTask]:
        """
        List tasks with optional filters.

        Args:
            status: Filter by status (pending, executing, done, failed, blocked).
            source: Filter by source (chatgpt, claude, manual, lynkmesh).
            assigned_to: Filter by assigned_to.
            module: Filter by target module.

        Returns:
            Filtered list of BridgeTask.
        """
        tasks = self._load_all_tasks()

        if status:
            tasks = [t for t in tasks if t.status == status]
        if source:
            tasks = [t for t in tasks if t.source == source]
        if assigned_to:
            tasks = [t for t in tasks if t.assigned_to == assigned_to]
        if module:
            tasks = [t for t in tasks if t.module == module]

        # Sort: newest first, then by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        tasks.sort(key=lambda t: (
            priority_order.get(t.priority, 99),
            t.created_at,
        ))
        return tasks

    def get_pending_tasks(self, assigned_to: Optional[str] = None) -> List[BridgeTask]:
        """Get all pending tasks, optionally filtered by assignee."""
        return self.list_tasks(status="pending", assigned_to=assigned_to)

    def get_executing_tasks(self) -> List[BridgeTask]:
        """Get all currently executing tasks."""
        return self.list_tasks(status="executing")

    def get_completed_tasks(self) -> List[BridgeTask]:
        """Get all completed tasks."""
        return self.list_tasks(status="done")

    def get_next_task(self, assigned_to: str = "claude") -> Optional[BridgeTask]:
        """
        Get the next pending task for an assignee (highest priority, oldest first).
        Does NOT change status -- caller must call move_to_executing.
        """
        pending = self.get_pending_tasks(assigned_to=assigned_to)
        return pending[0] if pending else None

    def iter_tasks(self) -> Iterator[BridgeTask]:
        yield from self._load_all_tasks()

    def count_by_status(self) -> Dict[str, int]:
        """Return count of tasks per status."""
        counts: Dict[str, int] = {}
        for task in self._load_all_tasks():
            counts[task.status] = counts.get(task.status, 0) + 1
        return counts

    def count_by_source(self) -> Dict[str, int]:
        """Return count of tasks per source."""
        counts: Dict[str, int] = {}
        for task in self._load_all_tasks():
            counts[task.source] = counts.get(task.source, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Event emission helpers
    # ------------------------------------------------------------------

    def _emit(self, event_type_name: str, task_id: str, **data: Any) -> None:
        """Emit an event if EventBus is configured."""
        if self._bus and _HAS_EVENTS:
            from lynkmesh_ai.events.bus import Event, EventType
            try:
                et = EventType(event_type_name)
            except ValueError:
                return
            self._bus.publish(Event(
                event_type=et,
                task_id=task_id,
                source="TaskRouter",
                data=data,
            ))

    # ------------------------------------------------------------------
    # Persistence (StorageAdapter-backed, FileStorageAdapter default)
    # ------------------------------------------------------------------

    def _save_task(self, task: BridgeTask) -> None:
        """Save a task via the storage backend (primary) and legacy JSON file."""
        # Primary: storage adapter
        self.storage.put(task.id, task.to_dict())
        # Legacy JSON fallback (different path to avoid overwrite)
        legacy_path = self.tasks_dir / f"{task.id}_legacy.json"
        legacy_path.write_text(task.to_json(), encoding="utf-8")

    def _load_all_tasks(self) -> List[BridgeTask]:
        """Load all tasks from storage adapter (primary) and legacy files (fallback)."""
        tasks: List[BridgeTask] = []
        seen_ids: set = set()
        # Primary: storage adapter
        try:
            for key in self.storage.list_keys(prefix="task_"):
                rec = self.storage.get(key)
                if rec and rec.data:
                    try:
                        task = BridgeTask.from_dict(rec.data)
                        tasks.append(task)
                        seen_ids.add(task.id)
                    except (ValueError, KeyError) as exc:
                        logger.warning(f"Skipping corrupted storage record {key}: {exc}")
        except Exception:
            pass
        # Fallback: legacy JSON files (only for tasks not already loaded from storage)
        if self.tasks_dir.exists():
            for legacy_path in sorted(self.tasks_dir.glob("task_*_legacy.json")):
                try:
                    task = BridgeTask.from_json(legacy_path.read_text(encoding="utf-8"))
                    if task.id not in seen_ids:
                        tasks.append(task)
                        seen_ids.add(task.id)
                except (json.JSONDecodeError, OSError, ValueError) as exc:
                    logger.warning(f"Skipping corrupted legacy file {legacy_path.name}: {exc}")
        return tasks

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def create_batch(
        self,
        tasks: List[Dict[str, Any]],
        source: str = "chatgpt",
        assigned_to: str = "claude",
    ) -> List[BridgeTask]:
        """Create multiple tasks from a list of specification dicts."""
        created: List[BridgeTask] = []
        for spec in tasks:
            task = self.create_task(
                title=spec.get("title", ""),
                source=spec.get("source", source),
                assigned_to=spec.get("assigned_to", assigned_to),
                module=spec.get("module", ""),
                priority=spec.get("priority", "medium"),
                description=spec.get("description", ""),
                instructions=spec.get("instructions", ""),
                tags=spec.get("tags", []),
                metadata=spec.get("metadata", {}),
            )
            created.append(task)
        return created

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def status_report(self) -> str:
        """Return a human-readable status report."""
        counts = self.count_by_status()
        source_counts = self.count_by_source()
        lines = [
            "=== Bridge Task Status ===",
            f"  Pending:   {counts.get('pending', 0)}",
            f"  Executing: {counts.get('executing', 0)}",
            f"  Done:      {counts.get('done', 0)}",
            f"  Failed:    {counts.get('failed', 0)}",
            f"  Blocked:   {counts.get('blocked', 0)}",
            f"  Total:     {sum(counts.values())}",
            "",
            "By Source:",
        ]
        for src, cnt in sorted(source_counts.items()):
            lines.append(f"  {src}: {cnt}")
        return "\n".join(lines)
