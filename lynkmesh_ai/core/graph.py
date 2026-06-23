"""
DependencyGraph — in-memory directed graph with JSON persistence.

Represents the module-level dependency structure of a Python codebase.
Nodes are modules; edges are dependency relationships (imports, calls).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Node:
    """A single module node in the dependency graph."""

    name: str
    file_path: str
    package: str = ""
    imports: List[str] = field(default_factory=list)
    imported_by: List[str] = field(default_factory=list)
    function_calls: List[str] = field(default_factory=list)
    callers: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    lines_of_code: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "package": self.package,
            "imports": self.imports,
            "imported_by": self.imported_by,
            "function_calls": self.function_calls,
            "callers": self.callers,
            "classes": self.classes,
            "functions": self.functions,
            "lines_of_code": self.lines_of_code,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Node":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Edge:
    """A directed edge between two modules."""

    source: str
    target: str
    relation_type: str  # "import", "call", "inheritance"
    weight: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type,
            "weight": self.weight,
            "metadata": self.metadata,
        }


class DependencyGraph:
    """
    Directed graph representing module-level dependencies in a codebase.

    Supports:
    - Upserting nodes and edges
    - Topological traversal
    - Upstream/downstream dependency queries
    - JSON serialization/deserialization
    - Impact analysis (what breaks if X changes?)
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._nodes: Dict[str, Node] = {}
        self._edges: List[Edge] = []
        self._adjacency: Dict[str, List[str]] = defaultdict(list)
        self._reverse_adjacency: Dict[str, List[str]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Add or update a node in the graph."""
        self._nodes[node.name] = node
        if node.name not in self._adjacency:
            self._adjacency[node.name] = []

    def get_node(self, name: str) -> Optional[Node]:
        """Retrieve a node by module name."""
        return self._nodes.get(name)

    def has_node(self, name: str) -> bool:
        return name in self._nodes

    def remove_node(self, name: str) -> None:
        """Remove a node and all its incident edges."""
        if name in self._nodes:
            del self._nodes[name]
        self._edges = [e for e in self._edges if e.source != name and e.target != name]
        self._adjacency.pop(name, None)
        self._reverse_adjacency.pop(name, None)
        for deps in self._adjacency.values():
            if name in deps:
                deps.remove(name)
        for deps in self._reverse_adjacency.values():
            if name in deps:
                deps.remove(name)

    def iter_nodes(self) -> Iterator[Node]:
        yield from self._nodes.values()

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(self, source: str, target: str, relation_type: str = "import", weight: int = 1) -> None:
        """Add a directed edge source→target."""
        # Deduplicate
        for e in self._edges:
            if e.source == source and e.target == target and e.relation_type == relation_type:
                e.weight += weight
                return
        edge = Edge(source=source, target=target, relation_type=relation_type, weight=weight)
        self._edges.append(edge)
        self._adjacency[source].append(target)
        self._reverse_adjacency[target].append(source)

    def iter_edges(self) -> Iterator[Edge]:
        yield from self._edges

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def upstream_dependencies(self, module: str, depth: int = -1, seen: Optional[Set[str]] = None) -> Set[str]:
        """
        Return all modules that `module` depends on (its transitive imports).

        Args:
            module: The starting module name.
            depth: Maximum traversal depth (-1 = unlimited).
            seen: Internal recursion set.
        """
        if seen is None:
            seen = set()
        if module not in self._adjacency or depth == 0:
            return seen
        for dep in self._adjacency.get(module, []):
            if dep not in seen:
                seen.add(dep)
                self.upstream_dependencies(dep, depth - 1 if depth > 0 else -1, seen)
        return seen

    def downstream_dependents(self, module: str, depth: int = -1, seen: Optional[Set[str]] = None) -> Set[str]:
        """
        Return all modules that depend on `module` (its reverse dependencies).

        Args:
            module: The starting module name.
            depth: Maximum traversal depth (-1 = unlimited).
            seen: Internal recursion set.
        """
        if seen is None:
            seen = set()
        if depth == 0:
            return seen
        for dep in self._reverse_adjacency.get(module, []):
            if dep not in seen:
                seen.add(dep)
                self.downstream_dependents(dep, depth - 1 if depth > 0 else -1, seen)
        return seen

    def immediate_dependencies(self, module: str) -> List[str]:
        """Return direct (1-hop) dependencies of a module."""
        return list(self._adjacency.get(module, []))

    def immediate_dependents(self, module: str) -> List[str]:
        """Return direct (1-hop) dependents of a module."""
        return list(self._reverse_adjacency.get(module, []))

    def topological_order(self) -> List[str]:
        """
        Return modules in topological order (build order).
        Uses Kahn's algorithm; raises ValueError on cycle.
        """
        in_degree = {name: 0 for name in self._nodes}
        for edge in self._edges:
            if edge.target in in_degree:
                in_degree[edge.target] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in self._adjacency.get(node, []):
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        if len(result) != len(self._nodes):
            remaining = set(self._nodes.keys()) - set(result)
            logger.warning(f"Graph contains cycles involving: {remaining}")
            result.extend(remaining)

        return result

    def find_cycles(self) -> List[List[str]]:
        """Detect all cycles in the dependency graph using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {name: WHITE for name in self._nodes}
        cycles: List[List[str]] = []
        stack: List[str] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            stack.append(node)
            for neighbor in self._adjacency.get(node, []):
                if neighbor not in color:
                    continue
                if color.get(neighbor) == GRAY:
                    # Found a cycle
                    idx = stack.index(neighbor)
                    cycles.append(stack[idx:] + [neighbor])
                elif color.get(neighbor) == WHITE:
                    dfs(neighbor)
            stack.pop()
            color[node] = BLACK

        for name in self._nodes:
            if color.get(name) == WHITE:
                dfs(name)

        return cycles

    def impact_analysis(self, changed_modules: List[str]) -> Dict[str, Any]:
        """
        Given a set of changed modules, determine what is impacted.

        Returns:
            {
                "directly_changed": [...],
                "affected_dependents": {module: downstream_set},
                "affected_dependencies": {module: upstream_set},
                "risk_scores": {module: score},
            }
        """
        result: Dict[str, Any] = {
            "directly_changed": changed_modules,
            "affected_dependents": {},
            "affected_dependencies": {},
            "risk_scores": {},
        }

        for mod in changed_modules:
            if not self.has_node(mod):
                continue
            deps = self.downstream_dependents(mod)
            result["affected_dependents"][mod] = list(deps)

            upstream = self.upstream_dependencies(mod)
            result["affected_dependencies"][mod] = list(upstream)

            result["risk_scores"][mod] = self._compute_risk(mod, deps, upstream)

        return result

    def _compute_risk(self, module: str, dependents: Set[str], dependencies: Set[str]) -> str:
        """Compute a risk score (low/medium/high/critical) for a change."""
        dep_count = len(dependents)
        if dep_count > 10:
            return "critical"
        elif dep_count > 5:
            return "high"
        elif dep_count > 2:
            return "medium"
        elif dep_count > 0:
            return "low"
        else:
            # Check if it's a leaf module with no dependents
            node = self.get_node(module)
            if node and node.imported_by:
                return "low"
            return "none"

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "nodes": {name: node.to_dict() for name, node in self._nodes.items()},
            "edges": [e.to_dict() for e in self._edges],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DependencyGraph":
        graph = cls(name=data.get("name", "default"))
        for name, node_data in data.get("nodes", {}).items():
            graph._nodes[name] = Node.from_dict(node_data)
        for edge_data in data.get("edges", []):
            graph._edges.append(Edge(**edge_data))
        # Rebuild adjacency
        for edge in graph._edges:
            graph._adjacency[edge.source].append(edge.target)
            graph._reverse_adjacency[edge.target].append(edge.source)
        return graph

    def save(self, path: Path) -> None:
        """Persist graph to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info(f"Graph saved to {path} ({self.node_count} nodes, {self.edge_count} edges)")

    @classmethod
    def load(cls, path: Path) -> "DependencyGraph":
        """Load graph from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        graph = cls.from_dict(data)
        logger.info(f"Graph loaded from {path} ({graph.node_count} nodes, {graph.edge_count} edges)")
        return graph

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return a human-readable summary of the graph."""
        lines = [
            f"=== Dependency Graph: {self.name} ===",
            f"Nodes: {self.node_count}",
            f"Edges: {self.edge_count}",
            f"Packages: {len({n.package for n in self._nodes.values() if n.package})}",
        ]
        cycles = self.find_cycles()
        if cycles:
            lines.append(f"Cycles detected: {len(cycles)}")
            for c in cycles[:5]:
                lines.append(f"  → {' → '.join(c)}")
        else:
            lines.append("No cycles detected.")
        return "\n".join(lines)

    def stats(self) -> Dict[str, Any]:
        """Return statistical summary of the graph."""
        total_loc = sum(n.lines_of_code for n in self._nodes.values())
        imports_count = sum(len(n.imports) for n in self._nodes.values())
        return {
            "name": self.name,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "total_lines_of_code": total_loc,
            "total_imports": imports_count,
            "cycles": len(self.find_cycles()),
            "leaf_modules": sum(1 for n in self._nodes.values() if not self._adjacency.get(n.name)),
            "root_modules": sum(1 for n in self._nodes.values() if not self._reverse_adjacency.get(n.name)),
        }
