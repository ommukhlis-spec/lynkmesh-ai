"""
InboxManager — manages the lifecycle of Claude Code task files in .ai/

Directory structure:
    .ai/
      inbox/       ← New tasks awaiting execution
      executing/   ← Tasks currently being processed
      done/        ← Completed tasks (archive)
      state.json   ← Persistent state metadata
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


class InboxManager:
    """
    Manages the .ai/ directory for Claude Code task orchestration.

    Provides:
    - Task queuing (write to inbox/)
    - Task lifecycle (inbox → executing → done)
    - Task enumeration and status tracking
    - Stale task detection and cleanup
    """

    DIRS = ["inbox", "executing", "done"]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = Path(root_dir or Path.cwd() / ".ai")
        self._ensure_dirs()

    # ------------------------------------------------------------------
    # Directory management
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        """Create the .ai/ directory structure if it doesn't exist."""
        for subdir in self.DIRS:
            (self.root_dir / subdir).mkdir(parents=True, exist_ok=True)

    @property
    def inbox_dir(self) -> Path:
        return self.root_dir / "inbox"

    @property
    def executing_dir(self) -> Path:
        return self.root_dir / "executing"

    @property
    def done_dir(self) -> Path:
        return self.root_dir / "done"

    @property
    def state_file(self) -> Path:
        return self.root_dir / "state.json"

    # ------------------------------------------------------------------
    # Task file operations
    # ------------------------------------------------------------------

    def list_tasks(self, state: str = "inbox") -> List[Path]:
        """
        List all task files in a given state directory.

        Args:
            state: One of "inbox", "executing", "done".

        Returns:
            Sorted list of task file paths.
        """
        target_dir = self.root_dir / state
        if not target_dir.exists():
            return []
        tasks = sorted(target_dir.glob("task_*.md"))
        return tasks

    def list_all_tasks(self) -> Dict[str, List[Path]]:
        """List tasks across all states."""
        return {
            state: self.list_tasks(state)
            for state in self.DIRS
        }

    def read_task(self, task_path: Path) -> Optional[str]:
        """Read the contents of a task file."""
        try:
            return task_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.error(f"Failed to read task {task_path}: {exc}")
            return None

    def get_task_metadata(self, task_path: Path) -> Dict[str, Any]:
        """
        Extract YAML frontmatter metadata from a task file.

        Returns:
            Dict of metadata keys, or empty dict on failure.
        """
        try:
            content = task_path.read_text(encoding="utf-8")
        except OSError:
            return {}

        metadata: Dict[str, Any] = {}
        if content.startswith("---"):
            # Extract frontmatter between --- markers
            end_idx = content.find("---", 3)
            if end_idx > 0:
                frontmatter = content[3:end_idx].strip()
                for line in frontmatter.split("\n"):
                    line = line.strip()
                    if ":" in line:
                        key, _, value = line.partition(":")
                        key = key.strip()
                        value = value.strip()
                        metadata[key] = value
        return metadata

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------

    def move_to_executing(self, task_path: Path) -> Path:
        """
        Move a task from inbox to executing.

        Args:
            task_path: Path to the task file (must be in inbox/).

        Returns:
            New path in executing/.
        """
        dest = self.executing_dir / task_path.name
        shutil.move(str(task_path), str(dest))
        logger.info(f"Task moved to executing: {dest.name}")
        return dest

    def move_to_done(self, task_path: Path, result_note: str = "") -> Path:
        """
        Move a task from inbox or executing to done.

        Args:
            task_path: Path to the task file.
            result_note: Optional note to append to the task file.

        Returns:
            New path in done/.
        """
        dest = self.done_dir / task_path.name

        if result_note:
            content = self.read_task(task_path) or ""
            content += f"\n\n## Execution Result\n\n{result_note}\n"
            # Write updated content before moving
            task_path.write_text(content, encoding="utf-8")

        shutil.move(str(task_path), str(dest))
        logger.info(f"Task moved to done: {dest.name}")
        return dest

    def delete_task(self, task_path: Path) -> None:
        """Delete a task file permanently."""
        task_path.unlink(missing_ok=True)
        logger.info(f"Task deleted: {task_path.name}")

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def push_task(self, content: str, task_id: str) -> Path:
        """
        Write a new task file to the inbox.

        Args:
            content: Task file content (markdown).
            task_id: Unique task identifier.

        Returns:
            Path to the created file.
        """
        file_path = self.inbox_dir / f"task_{task_id}.md"
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"Task pushed to inbox: {file_path.name}")
        return file_path

    def pop_next_task(self) -> Optional[Path]:
        """
        Get the next task from the inbox and move it to executing.

        Returns:
            Path to the task in executing/, or None if inbox is empty.
        """
        tasks = self.list_tasks("inbox")
        if not tasks:
            return None
        # FIFO: oldest first
        return self.move_to_executing(tasks[0])

    def queue_size(self) -> int:
        return len(self.list_tasks("inbox"))

    def executing_count(self) -> int:
        return len(self.list_tasks("executing"))

    def done_count(self) -> int:
        return len(self.list_tasks("done"))

    # ------------------------------------------------------------------
    # Stale task management
    # ------------------------------------------------------------------

    def find_stale_tasks(self, max_age_hours: int = 24) -> List[Path]:
        """
        Find tasks in executing/ that exceed max_age_hours.

        Args:
            max_age_hours: Maximum age before a task is considered stale.

        Returns:
            List of stale task paths.
        """
        stale = []
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)

        for task in self.list_tasks("executing"):
            try:
                mtime = task.stat().st_mtime
                if mtime < cutoff:
                    stale.append(task)
            except OSError:
                pass

        return stale

    def requeue_stale_tasks(self, max_age_hours: int = 24) -> List[Path]:
        """
        Move stale tasks back to inbox.

        Returns:
            List of requeued task paths.
        """
        requeued = []
        for task in self.find_stale_tasks(max_age_hours):
            dest = self.inbox_dir / task.name
            shutil.move(str(task), str(dest))
            requeued.append(dest)
            logger.info(f"Stale task requeued: {task.name}")
        return requeued

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def save_state(self, metadata: Dict[str, Any]) -> None:
        """Save state metadata to .ai/state.json."""
        state = self.load_state()
        state.update(metadata)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.state_file.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    def load_state(self) -> Dict[str, Any]:
        """Load state metadata from .ai/state.json."""
        if not self.state_file.exists():
            return {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "inbox_count": 0,
                "executing_count": 0,
                "done_count": 0,
            }
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def sync_state(self) -> Dict[str, Any]:
        """Synchronize state file with actual directory contents."""
        state = {
            "inbox_count": self.queue_size(),
            "executing_count": self.executing_count(),
            "done_count": self.done_count(),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save_state(state)
        return state

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def status_report(self) -> str:
        """Return a human-readable status report."""
        inbox = self.list_tasks("inbox")
        executing = self.list_tasks("executing")
        done = self.list_tasks("done")

        lines = [
            "╔══════════════════════════════════════╗",
            "║     LynkMesh AI — Inbox Status       ║",
            "╚══════════════════════════════════════╝",
            "",
            f"  📥  Inbox:     {len(inbox)} tasks",
            f"  ⚙️   Executing: {len(executing)} tasks",
            f"  ✅  Done:      {len(done)} tasks",
            f"  📍  Root:      {self.root_dir}",
            "",
        ]

        if inbox:
            lines.append("  Pending tasks:")
            for t in inbox:
                meta = self.get_task_metadata(t)
                module = meta.get("module", "?")
                risk = meta.get("risk_score", "?")
                lines.append(f"    - {t.name}  (module={module}, risk={risk})")

        if executing:
            lines.append("")
            lines.append("  Executing:")
            for t in executing:
                lines.append(f"    - {t.name}")

        lines.append("")
        return "\n".join(lines)
