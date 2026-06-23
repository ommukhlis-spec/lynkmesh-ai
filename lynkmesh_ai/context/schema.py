"""
Context schema — structured data classes for AI context packages.

The ContextPackage is the canonical data format exchanged between
the graph analysis layer and the AI task generation layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ContextFile:
    """Metadata about a single file in the context package."""

    path: str
    module_name: str = ""
    lines_of_code: int = 0
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    content_snippet: str = ""  # First N lines of the file

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextFile":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ContextDependency:
    """A single dependency relationship."""

    source: str  # The module that depends
    target: str  # The module being depended on
    relation_type: str = "import"  # import, call, inheritance
    weight: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecentChange:
    """A recent code change affecting this module."""

    file_path: str
    change_type: str  # added, modified, deleted
    timestamp: str = ""
    commit_hash: str = ""
    lines_added: int = 0
    lines_removed: int = 0
    diff_snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SemanticEdge:
    """A semantic relationship between modules (for context packages)."""

    source: str
    target: str
    relation_type: str = ""  # inherits, implements, creates, belongs_to_domain
    weight: int = 1
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticEdge":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ContextPackage:
    """
    Complete AI context package for a module or set of modules.

    This is the canonical structured context format consumed by:
    - ClaudeTaskGenerator (task file creation)
    - Any downstream AI agent that needs codebase context

    JSON Schema:
    {
      "module": "auth.service",
      "files": [...],
      "dependencies": [...],
      "recent_changes": [...],
      "risk_score": "medium",
      "metadata": {...}
    }
    """

    module: str = ""
    files: List[ContextFile] = field(default_factory=list)
    dependencies: List[ContextDependency] = field(default_factory=list)
    recent_changes: List[RecentChange] = field(default_factory=list)
    risk_score: str = "none"  # none, low, medium, high, critical
    # --- Semantic fields (all have defaults for backward compat) ---
    semantic_edges: List[SemanticEdge] = field(default_factory=list)
    design_patterns: List[Dict[str, Any]] = field(default_factory=list)
    domain_concepts: List[Dict[str, Any]] = field(default_factory=list)
    architectural_role: str = ""
    # --- Reasoning fields (all have defaults for backward compat) ---
    reasoning: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.metadata:
            self.metadata = {}
        self.metadata.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        self.metadata.setdefault("schema_version", "1.0")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "files": [f.to_dict() for f in self.files],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "recent_changes": [c.to_dict() for c in self.recent_changes],
            "risk_score": self.risk_score,
            "semantic_edges": [s.to_dict() for s in self.semantic_edges],
            "design_patterns": self.design_patterns,
            "domain_concepts": self.domain_concepts,
            "architectural_role": self.architectural_role,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextPackage":
        pkg = cls(
            module=data.get("module", ""),
            files=[ContextFile.from_dict(f) for f in data.get("files", [])],
            dependencies=[ContextDependency(**d) for d in data.get("dependencies", [])],
            recent_changes=[RecentChange(**c) for c in data.get("recent_changes", [])],
            risk_score=data.get("risk_score", "none"),
            semantic_edges=[SemanticEdge.from_dict(s) for s in data.get("semantic_edges", [])],
            design_patterns=data.get("design_patterns", []),
            domain_concepts=data.get("domain_concepts", []),
            architectural_role=data.get("architectural_role", ""),
            reasoning=data.get("reasoning", {}),
            metadata=data.get("metadata", {}),
        )
        return pkg

    @classmethod
    def from_json(cls, json_str: str) -> "ContextPackage":
        return cls.from_dict(json.loads(json_str))

    def save(self, path: Path) -> None:
        """Persist context package to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ContextPackage":
        """Load context package from JSON file."""
        return cls.from_json(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def dependency_count(self) -> int:
        return len(self.dependencies)

    @property
    def has_changes(self) -> bool:
        return len(self.recent_changes) > 0

    @property
    def total_loc(self) -> int:
        return sum(f.lines_of_code for f in self.files)

    def summary(self) -> str:
        lines = [
            f"=== Context Package: {self.module} ===",
            f"Files: {self.file_count}",
            f"Dependencies: {self.dependency_count}",
            f"Changes: {len(self.recent_changes)}",
            f"Risk Score: {self.risk_score}",
            f"Total LoC: {self.total_loc}",
        ]
        return "\n".join(lines)
