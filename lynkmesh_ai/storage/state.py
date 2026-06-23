"""
StateStore — persistent key-value store for LynkMesh AI operational state.

Provides:
- Run history (what was analyzed, when, by whom)
- Graph cache metadata
- Configuration persistence
- Session tracking
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StateStore:
    """
    Persistent state store backed by a JSON file.

    Tracks the operational state of LynkMesh AI across runs:
    - Last analysis timestamp
    - Graph build cache metadata
    - Run history with context snapshots
    - Configuration values
    """

    DEFAULT_STATE: Dict[str, Any] = {
        "version": "0.1.0",
        "created_at": "",
        "last_analysis": None,
        "last_graph_build": None,
        "graph_cache_path": "",
        "total_runs": 0,
        "run_history": [],
        "config": {},
    }

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self.file_path = Path(file_path or Path.cwd() / ".ai" / "state.json")
        self._state: Dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        """Load state from disk, merging with defaults."""
        if not self.file_path.exists():
            self._state = dict(self.DEFAULT_STATE)
            self._state["created_at"] = datetime.now(timezone.utc).isoformat()
            return self._state

        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            self._state = dict(self.DEFAULT_STATE)
            self._state.update(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Failed to load state: {exc}. Using defaults.")
            self._state = dict(self.DEFAULT_STATE)

        return self._state

    def save(self) -> None:
        """Persist current state to disk."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(self._state, indent=2, default=str),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Getters / Setters
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._state[key] = value

    def update(self, mapping: Dict[str, Any]) -> None:
        self._state.update(mapping)

    # ------------------------------------------------------------------
    # Analysis tracking
    # ------------------------------------------------------------------

    def record_analysis(self, directory: str, node_count: int, edge_count: int, duration_ms: float) -> None:
        """Record a completed analysis run."""
        entry = {
            "directory": directory,
            "node_count": node_count,
            "edge_count": edge_count,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "graph_cache_path": self._state.get("graph_cache_path", ""),
        }

        self._state["last_analysis"] = entry
        self._state["total_runs"] = self._state.get("total_runs", 0) + 1

        # Keep last 50 runs
        history = self._state.get("run_history", [])
        history.append(entry)
        if len(history) > 50:
            history = history[-50:]
        self._state["run_history"] = history

        self.save()
        logger.info(f"Analysis recorded: {node_count} nodes, {edge_count} edges, {duration_ms:.0f}ms")

    def record_graph_build(self, graph_path: str, node_count: int, edge_count: int) -> None:
        """Record a graph build for caching purposes."""
        self._state["last_graph_build"] = {
            "path": graph_path,
            "node_count": node_count,
            "edge_count": edge_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._state["graph_cache_path"] = graph_path
        self.save()

    def record_task_generation(self, task_id: str, module: str, task_path: str) -> None:
        """Record a task file generation."""
        self._state.setdefault("generated_tasks", []).append({
            "task_id": task_id,
            "module": module,
            "task_path": task_path,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 100
        tasks = self._state["generated_tasks"]
        if len(tasks) > 100:
            self._state["generated_tasks"] = tasks[-100:]
        self.save()

    # ------------------------------------------------------------------
    # Run history
    # ------------------------------------------------------------------

    def last_analysis(self) -> Optional[Dict[str, Any]]:
        """Return the last analysis record, if any."""
        return self._state.get("last_analysis")

    def recent_runs(self, count: int = 10) -> List[Dict[str, Any]]:
        """Return the N most recent runs."""
        history = self._state.get("run_history", [])
        return history[-count:]

    def total_runs(self) -> int:
        return self._state.get("total_runs", 0)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._state.get("config", {}).get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        if "config" not in self._state:
            self._state["config"] = {}
        self._state["config"][key] = value
        self.save()

    def get_all_config(self) -> Dict[str, Any]:
        return self._state.get("config", {})

    # ------------------------------------------------------------------
    # Graph cache
    # ------------------------------------------------------------------

    def get_graph_cache_info(self) -> Optional[Dict[str, Any]]:
        """Get info about the cached graph, if any."""
        info = self._state.get("last_graph_build")
        if not info:
            return None
        cache_path = Path(info.get("path", ""))
        if cache_path.exists():
            return info
        return None

    def is_graph_cache_valid(self, max_age_seconds: int = 3600) -> bool:
        """Check if the cached graph is still fresh."""
        info = self.get_graph_cache_info()
        if not info:
            return False

        ts = info.get("timestamp", "")
        if not ts:
            return False

        try:
            build_time = datetime.fromisoformat(ts)
            age = (datetime.now(timezone.utc) - build_time).total_seconds()
            return age < max_age_seconds
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear_history(self) -> None:
        """Clear run history (keep config)."""
        self._state["run_history"] = []
        self._state["total_runs"] = 0
        self._state["last_analysis"] = None
        self.save()

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._state)
