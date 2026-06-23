"""
ChangeTracker — detects source changes via git diff and maps them to graph nodes.

Uses subprocess to invoke git commands. Falls back gracefully when
no git repository is available.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ChangeRecord:
    """A single tracked change."""

    __slots__ = ("file_path", "module_name", "change_type", "timestamp", "commit_hash", "lines_added", "lines_removed")

    def __init__(
        self,
        file_path: str,
        module_name: str = "",
        change_type: str = "modified",
        timestamp: Optional[str] = None,
        commit_hash: str = "",
        lines_added: int = 0,
        lines_removed: int = 0,
    ) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.change_type = change_type  # "added", "modified", "deleted", "renamed"
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.commit_hash = commit_hash
        self.lines_added = lines_added
        self.lines_removed = lines_removed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "module_name": self.module_name,
            "change_type": self.change_type,
            "timestamp": self.timestamp,
            "commit_hash": self.commit_hash,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
        }


class ChangeTracker:
    """
    Tracks source code changes using git diff.

    Provides:
    - Diff between any two refs (HEAD~1..HEAD, branch..main, etc.)
    - Changed file enumeration
    - Change-to-graph-node mapping
    - Structured change records
    """

    def __init__(self, repo_path: Optional[Path] = None) -> None:
        self.repo_path = Path(repo_path or Path.cwd())
        self._git_dir = self._find_git_dir()
        self._changes: List[ChangeRecord] = []

    def _find_git_dir(self) -> Optional[Path]:
        """Find the .git directory for the given path."""
        current = self.repo_path.resolve()
        for _ in range(32):  # Max depth
            if (current / ".git").exists():
                return current / ".git"
            if current.parent == current:
                break
            current = current.parent
        return None

    @property
    def has_git(self) -> bool:
        return self._git_dir is not None

    # ------------------------------------------------------------------
    # Git command execution
    # ------------------------------------------------------------------

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        """
        Run a git command and return (exit_code, stdout, stderr).

        Returns (1, "", error_message) if git is unavailable.
        """
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd or self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except FileNotFoundError:
            return 1, "", "git command not found"
        except subprocess.TimeoutExpired:
            return 1, "", "git command timed out"
        except Exception as exc:
            return 1, "", str(exc)

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    def detect_changes(
        self,
        base_ref: str = "HEAD~1",
        target_ref: str = "HEAD",
        file_pattern: str = "*.py",
    ) -> List[ChangeRecord]:
        """
        Detect changed Python files between two git refs.

        Args:
            base_ref: The older ref (e.g., HEAD~1, main, origin/main).
            target_ref: The newer ref (e.g., HEAD, feature-branch).
            file_pattern: Glob pattern to filter files.

        Returns:
            List of ChangeRecord for each changed file.
        """
        self._changes.clear()

        if not self.has_git:
            logger.warning("No git repository found; change tracking disabled.")
            return self._fallback_changes(file_pattern)

        # Get the list of changed files
        exit_code, stdout, stderr = self._run_git([
            "diff", "--name-status", f"{base_ref}...{target_ref}",
            "--", file_pattern,
        ])

        if exit_code != 0:
            logger.error(f"git diff failed: {stderr}")
            return self._changes

        if not stdout:
            logger.info(f"No changes detected between {base_ref} and {target_ref}")
            return self._changes

        for line in stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            record = self._parse_diff_line(line, base_ref, target_ref)
            if record:
                self._changes.append(record)

        logger.info(f"Detected {len(self._changes)} changed files")
        return self._changes

    def detect_unstaged_changes(self) -> List[ChangeRecord]:
        """Detect unstaged changes in the working tree."""
        self._changes.clear()

        if not self.has_git:
            return self._fallback_changes("*.py")

        exit_code, stdout, stderr = self._run_git([
            "diff", "--name-only", "--", "*.py",
        ])

        if exit_code != 0 or not stdout:
            return self._changes

        for line in stdout.split("\n"):
            line = line.strip()
            if line:
                file_path = str(self.repo_path / line)
                record = ChangeRecord(
                    file_path=file_path,
                    change_type="modified",
                )
                self._changes.append(record)

        return self._changes

    def detect_staged_changes(self) -> List[ChangeRecord]:
        """Detect staged (but uncommitted) changes."""
        self._changes.clear()

        if not self.has_git:
            return self._fallback_changes("*.py")

        exit_code, stdout, stderr = self._run_git([
            "diff", "--cached", "--name-only", "--", "*.py",
        ])

        if exit_code != 0 or not stdout:
            return self._changes

        for line in stdout.split("\n"):
            line = line.strip()
            if line:
                file_path = str(self.repo_path / line)
                record = ChangeRecord(
                    file_path=file_path,
                    change_type="staged",
                )
                self._changes.append(record)

        return self._changes

    # ------------------------------------------------------------------
    # Diff detail
    # ------------------------------------------------------------------

    def get_file_diff(self, file_path: str, base_ref: str = "HEAD~1", target_ref: str = "HEAD") -> str:
        """Get the detailed diff for a specific file."""
        exit_code, stdout, stderr = self._run_git([
            "diff", f"{base_ref}...{target_ref}", "--", file_path,
        ])
        if exit_code != 0:
            logger.error(f"Failed to get diff for {file_path}: {stderr}")
            return ""
        return stdout

    def get_recent_commits(self, count: int = 10) -> List[Dict[str, str]]:
        """Get recent commit messages for context."""
        exit_code, stdout, stderr = self._run_git([
            "log", f"-{count}", "--format=%H|%ai|%s",
        ])

        if exit_code != 0 or not stdout:
            return []

        commits = []
        for line in stdout.split("\n"):
            line = line.strip()
            if "|" in line:
                parts = line.split("|", 2)
                if len(parts) == 3:
                    commits.append({
                        "hash": parts[0],
                        "date": parts[1],
                        "message": parts[2],
                    })
        return commits

    # ------------------------------------------------------------------
    # Graph mapping
    # ------------------------------------------------------------------

    def map_to_graph(self, graph: Any, changes: Optional[List[ChangeRecord]] = None) -> Dict[str, Any]:
        """
        Map detected changes to graph nodes.

        Args:
            graph: A DependencyGraph instance.
            changes: Change records (defaults to self._changes).

        Returns:
            Mapping of changed modules to their graph context.
        """
        changes = changes or self._changes
        mapping: Dict[str, Any] = {
            "changed_nodes": [],
            "affected_nodes": set(),
            "unchanged_dependents": [],
        }

        for record in changes:
            # Try to find which graph node this file belongs to
            module_name = record.module_name
            if not module_name:
                module_name = self._file_to_module(record.file_path)

            node = graph.get_node(module_name) if graph else None
            if node:
                mapping["changed_nodes"].append({
                    "module": module_name,
                    "node": node.to_dict(),
                    "change": record.to_dict(),
                })
                # Find what else is affected
                affected = graph.downstream_dependents(module_name)
                mapping["affected_nodes"].update(affected)
            else:
                mapping["changed_nodes"].append({
                    "module": module_name,
                    "node": None,
                    "change": record.to_dict(),
                })

        mapping["affected_nodes"] = list(mapping["affected_nodes"])
        return mapping

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_diff_line(self, line: str, base_ref: str, target_ref: str) -> Optional[ChangeRecord]:
        """Parse a line from `git diff --name-status` output."""
        parts = line.split("\t")
        if len(parts) < 2:
            return None

        status = parts[0]
        file_path = parts[1]

        change_type_map = {
            "A": "added",
            "M": "modified",
            "D": "deleted",
            "R": "renamed",
            "C": "copied",
            "T": "type_changed",
        }
        change_type = change_type_map.get(status[0], "modified")

        # Get diff stats
        exit_code, stdout, _ = self._run_git([
            "diff", f"{base_ref}...{target_ref}", "--numstat", "--", file_path,
        ])
        lines_added, lines_removed = 0, 0
        if exit_code == 0 and stdout:
            stat_parts = stdout.split("\t")
            if len(stat_parts) >= 2:
                try:
                    lines_added = int(stat_parts[0]) if stat_parts[0] != "-" else 0
                    lines_removed = int(stat_parts[1]) if stat_parts[1] != "-" else 0
                except ValueError:
                    pass

        return ChangeRecord(
            file_path=str(self.repo_path / file_path),
            change_type=change_type,
            lines_added=lines_added,
            lines_removed=lines_removed,
        )

    def _file_to_module(self, file_path: str) -> str:
        """Convert a file path to a dotted module name."""
        try:
            rel = Path(file_path).resolve().relative_to(self.repo_path.resolve())
        except ValueError:
            return Path(file_path).stem

        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]

        return ".".join(parts)

    def _fallback_changes(self, file_pattern: str) -> List[ChangeRecord]:
        """
        Fallback when git is unavailable: check file modification times.
        Useful for environments without git or for testing.
        """
        changes = []
        try:
            for py_file in self.repo_path.glob(file_pattern):
                stat = py_file.stat()
                changes.append(ChangeRecord(
                    file_path=str(py_file),
                    change_type="modified",
                    timestamp=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                ))
        except OSError:
            pass
        return changes
