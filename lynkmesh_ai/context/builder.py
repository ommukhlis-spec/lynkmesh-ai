"""
ContextBuilder — assembles ContextPackage objects from graph and change data.

This is the bridge between raw code analysis and structured AI context.
It consumes graph nodes, change records, and file data to produce
canonical ContextPackage objects.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from lynkmesh_ai.core.graph import DependencyGraph, Node
from lynkmesh_ai.core.change_tracker import ChangeRecord, ChangeTracker
from lynkmesh_ai.context.schema import (
    ContextPackage,
    ContextFile,
    ContextDependency,
    RecentChange,
    SemanticEdge,
)

logger = logging.getLogger(__name__)

# Max lines to include as a content snippet per file
MAX_SNIPPET_LINES = 60


class ContextBuilder:
    """
    Builds ContextPackage objects from graph and change analysis.

    Usage:
        builder = ContextBuilder(graph, change_tracker)
        pkg = builder.build_for_module("auth.service")
        pkg = builder.build_for_changes()
        pkg = builder.build_full_context()
    """

    def __init__(
        self,
        graph: DependencyGraph,
        change_tracker: Optional[ChangeTracker] = None,
        target_dir: Optional[Path] = None,
        semantic_graph: Any = None,
        knowledge_base: Any = None,
        reasoning_report: Any = None,
    ) -> None:
        self.graph = graph
        self.change_tracker = change_tracker
        self.target_dir = target_dir or Path.cwd()
        self.semantic_graph = semantic_graph
        self.knowledge_base = knowledge_base
        self.reasoning_report = reasoning_report

    # ------------------------------------------------------------------
    # Build methods
    # ------------------------------------------------------------------

    def build_for_module(
        self,
        module_name: str,
        include_dependencies: bool = True,
        include_dependents: bool = True,
        depth: int = 1,
    ) -> ContextPackage:
        """
        Build a context package focused on a specific module.

        Args:
            module_name: The target module (e.g., "auth.service").
            include_dependencies: Include upstream dependencies.
            include_dependents: Include downstream dependents.
            depth: How many levels of dependencies to traverse.

        Returns:
            A ContextPackage with the module and its neighborhood.
        """
        node = self.graph.get_node(module_name)
        if not node:
            logger.warning(f"Module '{module_name}' not found in graph")
            return ContextPackage(module=module_name)

        pkg = ContextPackage(module=module_name)
        seen_files: Set[str] = set()

        # Add the target module
        self._add_file_to_package(pkg, node.file_path, seen_files)

        # Add upstream dependencies
        if include_dependencies:
            dep_modules = self.graph.upstream_dependencies(module_name, depth=depth)
            for dep_name in dep_modules:
                dep_node = self.graph.get_node(dep_name)
                if dep_node:
                    self._add_file_to_package(pkg, dep_node.file_path, seen_files)

        # Add downstream dependents
        if include_dependents:
            dependent_modules = self.graph.downstream_dependents(module_name, depth=depth)
            for dep_name in dependent_modules:
                dep_node = self.graph.get_node(dep_name)
                if dep_node:
                    self._add_file_to_package(pkg, dep_node.file_path, seen_files)

        # Build dependency relationships
        self._build_dependencies(pkg, module_name, depth)

        # Add recent changes if available
        self._add_recent_changes(pkg)

        # Compute risk score
        pkg.risk_score = self._compute_risk(module_name)

        # Metadata
        pkg.metadata.update({
            "build_mode": "single_module",
            "depth": depth,
            "include_dependencies": include_dependencies,
            "include_dependents": include_dependents,
            "graph_stats": self.graph.stats(),
        })

        logger.info(f"Built context for '{module_name}': {pkg.file_count} files, "
                     f"{pkg.dependency_count} deps, risk={pkg.risk_score}")
        self._enrich_with_semantics(pkg, module_name)
        self._enrich_with_reasoning(pkg, module_name)
        return pkg

    def build_for_changes(
        self,
        base_ref: str = "HEAD~1",
        target_ref: str = "HEAD",
    ) -> ContextPackage:
        """
        Build a context package for all modules changed between two refs.

        Args:
            base_ref: Older git ref.
            target_ref: Newer git ref.

        Returns:
            A ContextPackage covering all changed modules.
        """
        if not self.change_tracker or not self.change_tracker.has_git:
            logger.warning("No change tracker available; building full context instead")
            return self.build_full_context()

        changes = self.change_tracker.detect_changes(base_ref, target_ref)
        if not changes:
            logger.info("No changes detected; returning empty package")
            return ContextPackage()

        # Map changes to graph nodes
        mapping = self.change_tracker.map_to_graph(self.graph, changes)

        # Collect all affected module names
        changed_modules = set()
        for item in mapping.get("changed_nodes", []):
            if item.get("module"):
                changed_modules.add(item["module"])
        changed_modules.update(mapping.get("affected_nodes", []))

        if not changed_modules:
            return ContextPackage()

        # Use the first changed module as the package anchor
        primary_module = sorted(changed_modules)[0]
        pkg = ContextPackage(module=primary_module)
        seen_files: Set[str] = set()

        for mod_name in changed_modules:
            node = self.graph.get_node(mod_name)
            if node:
                self._add_file_to_package(pkg, node.file_path, seen_files)

        # Add dependency edges between changed modules
        for mod_name in changed_modules:
            deps = self.graph.immediate_dependencies(mod_name)
            for dep in deps:
                if dep in changed_modules:
                    pkg.dependencies.append(ContextDependency(
                        source=mod_name,
                        target=dep,
                        relation_type="import",
                    ))

        # Add change records
        for record in changes:
            pkg.recent_changes.append(RecentChange(
                file_path=record.file_path,
                change_type=record.change_type,
                timestamp=record.timestamp,
                commit_hash=record.commit_hash,
                lines_added=record.lines_added,
                lines_removed=record.lines_removed,
            ))

        # Risk is high when multiple modules changed
        risk_scores = [self._compute_risk(m) for m in changed_modules]
        pkg.risk_score = self._highest_risk(risk_scores)

        pkg.metadata.update({
            "build_mode": "changes",
            "base_ref": base_ref,
            "target_ref": target_ref,
            "changed_modules": sorted(changed_modules),
            "total_changes": len(changes),
            "graph_stats": self.graph.stats(),
        })

        logger.info(f"Built context for changes: {pkg.file_count} files, "
                     f"{len(changed_modules)} modules affected")
        self._enrich_with_semantics(pkg, primary_module)
        return pkg

    def build_full_context(self) -> ContextPackage:
        """
        Build a context package covering the entire graph.

        Use with caution for large codebases — consider build_for_module instead.
        """
        if self.graph.node_count == 0:
            logger.warning("Graph is empty; nothing to build")
            return ContextPackage()

        pkg = ContextPackage()
        seen_files: Set[str] = set()

        for node in self.graph.iter_nodes():
            pkg.module = pkg.module or node.name
            self._add_file_to_package(pkg, node.file_path, seen_files)

        # Add all edges as dependencies
        for edge in self.graph.iter_edges():
            pkg.dependencies.append(ContextDependency(
                source=edge.source,
                target=edge.target,
                relation_type=edge.relation_type,
                weight=edge.weight,
            ))

        pkg.risk_score = "low"
        pkg.metadata.update({
            "build_mode": "full_context",
            "graph_stats": self.graph.stats(),
        })

        logger.info(f"Built full context: {pkg.file_count} files, {pkg.dependency_count} deps")
        self._enrich_with_semantics(pkg, pkg.module)
        return pkg

    def build_for_modules(self, module_names: List[str]) -> ContextPackage:
        """
        Build a context package covering specific modules and their intersections.

        Useful for multi-module feature work.
        """
        if not module_names:
            return ContextPackage()

        pkg = ContextPackage(module=module_names[0])
        seen_files: Set[str] = set()
        all_dep_modules: Set[str] = set()

        for name in module_names:
            node = self.graph.get_node(name)
            if not node:
                continue
            self._add_file_to_package(pkg, node.file_path, seen_files)
            # Include immediate neighbors
            for dep in self.graph.immediate_dependencies(name):
                all_dep_modules.add(dep)
            for dep in self.graph.immediate_dependents(name):
                all_dep_modules.add(dep)

        # Add neighbor files
        for dep_name in all_dep_modules:
            node = self.graph.get_node(dep_name)
            if node:
                self._add_file_to_package(pkg, node.file_path, seen_files)

        # Build dependencies
        all_modules = set(module_names) | all_dep_modules
        for mod in all_modules:
            for dep in self.graph.immediate_dependencies(mod):
                if dep in all_modules:
                    pkg.dependencies.append(ContextDependency(
                        source=mod,
                        target=dep,
                        relation_type="import",
                    ))

        risk_scores = [self._compute_risk(m) for m in module_names if self.graph.has_node(m)]
        pkg.risk_score = self._highest_risk(risk_scores) if risk_scores else "none"

        pkg.metadata.update({
            "build_mode": "multi_module",
            "target_modules": module_names,
            "total_deps_considered": len(all_dep_modules),
            "graph_stats": self.graph.stats(),
        })

        self._enrich_with_semantics(pkg, module_names[0])
        return pkg

    # ------------------------------------------------------------------
    # Semantic enrichment
    # ------------------------------------------------------------------

    def _enrich_with_semantics(self, pkg: ContextPackage, module_name: str) -> None:
        """
        Enrich a ContextPackage with semantic data.

        No-op if no semantic source (SemanticGraph or KnowledgeBase) is available.
        The existing pipeline remains completely unaffected.
        """
        # From SemanticGraph
        if self.semantic_graph:
            # Semantic edges
            edges = self.semantic_graph.get_semantic_edges(module=module_name)
            for e in edges:
                pkg.semantic_edges.append(SemanticEdge(
                    source=e.source,
                    target=e.target,
                    relation_type=e.relation_type,
                    description=e.description,
                ))

            # Design patterns
            patterns = self.semantic_graph.get_patterns(module_name)
            for p in patterns:
                pkg.design_patterns.append(p.to_dict())

            # Architectural role
            role = self.semantic_graph.get_role(module_name)
            if role:
                pkg.architectural_role = role.role

        # From KnowledgeBase
        if self.knowledge_base:
            concepts = self.knowledge_base.get_domain_concepts(module_name)
            for c in concepts:
                pkg.domain_concepts.append({"concept": c, "module": module_name})

    # ------------------------------------------------------------------
    # Reasoning enrichment
    # ------------------------------------------------------------------

    def _enrich_with_reasoning(self, pkg: ContextPackage, module_name: str) -> None:
        """
        Enrich a ContextPackage with reasoning data.

        No-op if no reasoning report is available.
        """
        if not self.reasoning_report:
            return

        # Extract module-specific reasoning from the report
        reasoning_data: Dict[str, Any] = {}

        if hasattr(self.reasoning_report, "to_dict"):
            full = self.reasoning_report.to_dict()
            # Filter to relevant sections for this module
            if "risk_assessment" in full:
                reasoning_data["risk"] = full["risk_assessment"]
            if "impact" in full:
                reasoning_data["impact"] = full["impact"]
            if "recommendations" in full:
                # Filter recommendations targeting this module
                module_recs = [
                    r for r in full.get("recommendations", [])
                    if r.get("target_module") == module_name
                ]
                if module_recs:
                    reasoning_data["recommendations"] = module_recs
            if "architecture_narrative" in full:
                reasoning_data["architecture_narrative"] = full["architecture_narrative"]

        pkg.reasoning = reasoning_data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_file_to_package(self, pkg: ContextPackage, file_path: str, seen: Set[str]) -> None:
        """Add a ContextFile to the package, deduplicating by path."""
        if file_path in seen:
            return
        seen.add(file_path)

        path = Path(file_path)
        snippet = self._read_snippet(path)

        # Look up node for richer metadata
        node = self._find_node_by_path(file_path)
        if node:
            cf = ContextFile(
                path=file_path,
                module_name=node.name,
                lines_of_code=node.lines_of_code,
                classes=node.classes,
                functions=node.functions,
                imports=node.imports,
                docstring=node.metadata.get("docstring"),
                content_snippet=snippet,
            )
        else:
            cf = ContextFile(
                path=file_path,
                module_name=path.stem,
                lines_of_code=len(snippet.splitlines()) if snippet else 0,
                content_snippet=snippet,
            )

        pkg.files.append(cf)

    def _build_dependencies(self, pkg: ContextPackage, module_name: str, depth: int) -> None:
        """Build ContextDependency list for the package."""
        deps = self.graph.upstream_dependencies(module_name, depth=depth)
        for dep_name in deps:
            pkg.dependencies.append(ContextDependency(
                source=module_name,
                target=dep_name,
                relation_type="import",
            ))

        dependents = self.graph.downstream_dependents(module_name, depth=1)
        for dep_name in dependents:
            pkg.dependencies.append(ContextDependency(
                source=dep_name,
                target=module_name,
                relation_type="import",
            ))

        # Also add direct edges from the graph
        for edge in self.graph.iter_edges():
            if edge.source == module_name or edge.target == module_name:
                already_present = any(
                    d.source == edge.source and d.target == edge.target
                    for d in pkg.dependencies
                )
                if not already_present:
                    pkg.dependencies.append(ContextDependency(
                        source=edge.source,
                        target=edge.target,
                        relation_type=edge.relation_type,
                        weight=edge.weight,
                    ))

    def _add_recent_changes(self, pkg: ContextPackage) -> None:
        """Add recent change records if a change tracker is available."""
        if not self.change_tracker or not self.change_tracker.has_git:
            return

        # Try to get recent commits
        commits = self.change_tracker.get_recent_commits(count=5)
        for commit in commits:
            # For each recent commit, see if it touched our files
            pass  # Detailed per-file diff is expensive; skip by default

        # Add unstaged changes for relevant files
        unstaged = self.change_tracker.detect_unstaged_changes()
        for record in unstaged:
            for cf in pkg.files:
                if record.file_path.endswith(cf.path) or cf.path.endswith(record.file_path):
                    pkg.recent_changes.append(RecentChange(
                        file_path=record.file_path,
                        change_type=record.change_type,
                        timestamp=record.timestamp,
                    ))

    def _compute_risk(self, module_name: str) -> str:
        """Compute risk score for a module change."""
        node = self.graph.get_node(module_name)
        if not node:
            return "none"

        dependents = self.graph.downstream_dependents(module_name)
        dep_count = len(dependents)

        # Also consider number of files imported
        import_count = len(node.imports)

        if dep_count > 10 or import_count > 20:
            return "critical"
        elif dep_count > 5 or import_count > 10:
            return "high"
        elif dep_count > 2:
            return "medium"
        elif dep_count > 0:
            return "low"
        return "none"

    def _find_node_by_path(self, file_path: str) -> Optional[Node]:
        """Find a graph node by its file path."""
        for node in self.graph.iter_nodes():
            if node.file_path == file_path:
                return node
        return None

    def _read_snippet(self, path: Path) -> str:
        """Read the first few lines of a file as a content snippet."""
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            return "\n".join(lines[:MAX_SNIPPET_LINES])
        except (OSError, UnicodeDecodeError):
            return ""

    @staticmethod
    def _highest_risk(scores: List[str]) -> str:
        """Return the highest risk score from a list."""
        order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        return max(scores, key=lambda s: order.get(s, 0), default="none")
