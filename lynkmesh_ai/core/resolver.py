"""
GraphResolver — builds the full dependency graph from parsed module info.

Resolves imports to actual graph nodes, computes cross-references,
and populates the DependencyGraph with complete relationship data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from lynkmesh_ai.core.graph import DependencyGraph, Node
from lynkmesh_ai.core.parser import ModuleInfo, ModuleParser

logger = logging.getLogger(__name__)


class GraphResolver:
    """
    Resolves parsed module information into a fully connected DependencyGraph.

    Responsibilities:
    1. Build nodes from ModuleInfo
    2. Resolve import statements to graph edges
    3. Cross-reference function calls to owning modules
    4. Compute reverse edges (imported_by, callers)
    5. Detect orphaned modules and dangling references
    """

    def __init__(self, parser: Optional[ModuleParser] = None) -> None:
        self.parser = parser or ModuleParser()
        self.graph = DependencyGraph()
        # Maps short module names → list of fully qualified names
        self._name_index: Dict[str, List[str]] = {}
        # Maps fully qualified names → function names defined there
        self._function_index: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Build pipeline
    # ------------------------------------------------------------------

    def build(self, directory: Optional[Path] = None) -> DependencyGraph:
        """
        Execute the full build pipeline on a directory.

        Steps:
        1. Parse all Python files
        2. Create graph nodes
        3. Resolve import edges
        4. Resolve call edges
        5. Compute reverse relationships
        6. Return the graph
        """
        target = directory or Path.cwd()
        logger.info(f"Building dependency graph for {target}")

        # Step 1: Parse
        modules = self.parser.parse_directory(target)
        if not modules:
            logger.warning(f"No Python files found in {target}")
            return self.graph

        # Step 2: Create nodes
        self._create_nodes(modules)

        # Step 3: Resolve imports → edges
        self._resolve_imports(modules)

        # Step 4: Resolve function calls → edges
        self._resolve_calls(modules)

        # Step 5: Compute reverse edges
        self._compute_reverse_edges()

        logger.info(
            f"Graph built: {self.graph.node_count} nodes, {self.graph.edge_count} edges"
        )
        return self.graph

    def rebuild(self, directory: Optional[Path] = None) -> DependencyGraph:
        """Full rebuild (clears and rebuilds from scratch)."""
        self.graph = DependencyGraph()
        self._name_index.clear()
        self._function_index.clear()
        return self.build(directory)

    # ------------------------------------------------------------------
    # Node creation
    # ------------------------------------------------------------------

    def _create_nodes(self, modules: List[ModuleInfo]) -> None:
        """Create graph nodes from parsed module info and build name indices."""
        for mod in modules:
            node = Node(
                name=mod.name,
                file_path=mod.file_path,
                package=mod.package,
                imports=list(set(mod.imports)),
                classes=mod.classes,
                functions=mod.functions,
                lines_of_code=mod.lines_of_code,
                metadata={
                    "docstring": mod.docstring,
                    "has_entry_point": mod.has_entry_point,
                    "async_functions": mod.async_functions,
                },
            )
            self.graph.add_node(node)

            # Index by fully qualified name
            self._name_index.setdefault(mod.name, []).append(mod.name)

            # Index by short name for fuzzy matching
            short = mod.name.split(".")[-1]
            if short != mod.name:
                self._name_index.setdefault(short, []).append(mod.name)

            # Index functions
            self._function_index[mod.name] = set(mod.functions) | set(mod.async_functions)

            # Also index top-level names
            for name in mod.top_level_names:
                self._name_index.setdefault(name, []).append(mod.name)

    # ------------------------------------------------------------------
    # Import resolution
    # ------------------------------------------------------------------

    def _resolve_imports(self, modules: List[ModuleInfo]) -> None:
        """Resolve import statements to graph edges."""
        for mod in modules:
            seen_targets: Set[str] = set()
            for imp in mod.imports:
                # Skip stdlib
                if ModuleParser.is_stdlib(imp):
                    continue

                # Try to find the target module
                targets = self._resolve_import_target(imp)
                for target in targets:
                    if target and target != mod.name and target not in seen_targets:
                        seen_targets.add(target)
                        self.graph.add_edge(
                            source=mod.name,
                            target=target,
                            relation_type="import",
                        )

            # Also resolve from-imports for finer granularity
            for module, name in mod.from_imports:
                if ModuleParser.is_stdlib(module):
                    continue
                targets = self._resolve_import_target(module)
                for target in targets:
                    if target and target != mod.name and target not in seen_targets:
                        seen_targets.add(target)
                        self.graph.add_edge(
                            source=mod.name,
                            target=target,
                            relation_type="import",
                        )

    def _resolve_import_target(self, import_name: str) -> List[str]:
        """
        Resolve an import name to one or more fully-qualified module names.

        Strategy:
        1. Exact match in node names
        2. Suffix match (e.g., `core.graph` matches `lynkmesh_ai.core.graph`)
        3. Short name match via _name_index
        """
        # Exact match
        if self.graph.has_node(import_name):
            return [import_name]

        # Suffix match
        candidates = []
        for node_name in self.graph._nodes:
            if node_name == import_name or node_name.endswith("." + import_name):
                candidates.append(node_name)

        if candidates:
            return candidates

        # Short-name index lookup
        return self._name_index.get(import_name, [])

    # ------------------------------------------------------------------
    # Call resolution
    # ------------------------------------------------------------------

    def _resolve_calls(self, modules: List[ModuleInfo]) -> None:
        """Resolve function calls to graph edges between modules."""
        for mod in modules:
            seen_targets: Set[str] = set()
            for call_name in mod.function_calls:
                # Find which modules define this function
                targets = self._resolve_call_target(call_name)
                for target in targets:
                    if target and target != mod.name and target not in seen_targets:
                        seen_targets.add(target)
                        self.graph.add_edge(
                            source=mod.name,
                            target=target,
                            relation_type="call",
                        )

    def _resolve_call_target(self, call_name: str) -> List[str]:
        """
        Resolve a function call name to owning modules.

        Handles dotted calls like `module.function` and bare calls like `function`.
        """
        targets: List[str] = []

        # Dotted call: `mymodule.some_function`
        if "." in call_name:
            parts = call_name.split(".")
            # Try the fully qualified import path
            for i in range(len(parts) - 1, 0, -1):
                module_path = ".".join(parts[:i])
                func_name = parts[i]
                resolved = self._resolve_import_target(module_path)
                for r in resolved:
                    if r in self._function_index and func_name in self._function_index[r]:
                        targets.append(r)
                if targets:
                    break

        # Bare call: search all function indices
        else:
            for mod_name, funcs in self._function_index.items():
                if call_name in funcs:
                    targets.append(mod_name)

        return targets

    # ------------------------------------------------------------------
    # Reverse edge computation
    # ------------------------------------------------------------------

    def _compute_reverse_edges(self) -> None:
        """Compute reverse relationships (imported_by, callers) for all nodes."""
        # Build imported_by from import edges
        for edge in self.graph.iter_edges():
            if edge.relation_type == "import":
                target_node = self.graph.get_node(edge.target)
                if target_node and edge.source not in target_node.imported_by:
                    target_node.imported_by.append(edge.source)

            elif edge.relation_type == "call":
                target_node = self.graph.get_node(edge.target)
                if target_node and edge.source not in target_node.callers:
                    target_node.callers.append(edge.source)

    # ------------------------------------------------------------------
    # Utility queries
    # ------------------------------------------------------------------

    def find_entry_points(self) -> List[Node]:
        """Find all modules that have `if __name__ == '__main__'` blocks."""
        entry_points = []
        for node in self.graph.iter_nodes():
            if node.metadata.get("has_entry_point"):
                entry_points.append(node)
        return entry_points

    def find_orphans(self) -> List[Node]:
        """
        Find orphan modules: those with no imports and no dependents.
        These may indicate dead code or utilities yet to be integrated.
        """
        orphans = []
        for node in self.graph.iter_nodes():
            deps = self.graph.immediate_dependencies(node.name)
            dependents = self.graph.immediate_dependents(node.name)
            if not deps and not dependents:
                orphans.append(node)
        return orphans

    def find_most_depended_upon(self, top_n: int = 10) -> List[Tuple[str, int]]:
        """Return the top-N most-depended-upon modules."""
        scores = []
        for node in self.graph.iter_nodes():
            scores.append((node.name, len(node.imported_by) + len(node.callers)))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]
