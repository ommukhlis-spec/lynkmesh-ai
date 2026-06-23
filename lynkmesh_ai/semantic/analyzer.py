"""
SemanticAnalyzer — orchestrates all semantic analysis on a DependencyGraph.

Runs PatternDetector, RoleClassifier, DomainAnalyzer, and SimilarityAnalyzer
for every node in the graph, then populates a SemanticGraph with the results.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from lynkmesh_ai.core.graph import DependencyGraph
from lynkmesh_ai.core.parser import ModuleParser, ModuleInfo
from lynkmesh_ai.semantic.graph import SemanticGraph
from lynkmesh_ai.semantic.patterns import PatternDetector
from lynkmesh_ai.semantic.roles import RoleClassifier
from lynkmesh_ai.semantic.domains import DomainAnalyzer
from lynkmesh_ai.semantic.similarity import SimilarityAnalyzer

logger = logging.getLogger(__name__)


class SemanticAnalyzer:
    """
    Orchestrates full semantic analysis of a DependencyGraph.

    Usage:
        analyzer = SemanticAnalyzer(graph, parser)
        sgraph = analyzer.analyze()
        sgraph.save(Path(".ai/semantic_graph.json"))
    """

    def __init__(
        self,
        graph: DependencyGraph,
        parser: Optional[ModuleParser] = None,
    ) -> None:
        self.graph = graph
        self.parser = parser or ModuleParser()
        self.pattern_detector = PatternDetector()
        self.role_classifier = RoleClassifier()
        self.domain_analyzer = DomainAnalyzer()
        self.similarity_analyzer = SimilarityAnalyzer(graph)

    # ------------------------------------------------------------------
    # Full analysis pipeline
    # ------------------------------------------------------------------

    def analyze(self) -> SemanticGraph:
        """
        Run the full semantic analysis pipeline.

        Steps:
        1. Parse each module to get ModuleInfo (if not already available)
        2. Detect design patterns
        3. Classify architectural roles
        4. Extract domain concepts
        5. Build semantic edges (inheritance, implements, creates)
        6. Compute pairwise structural similarity
        7. Return populated SemanticGraph
        """
        t0 = time.perf_counter()
        sgraph = SemanticGraph(graph=self.graph)

        module_count = 0
        pattern_count = 0

        # Step 1-4: Per-module analysis
        for node in self.graph.iter_nodes():
            module_count += 1
            module_name = node.name

            # Get (or re-parse) ModuleInfo for AST-level data
            info = self._get_module_info(node)

            if not info:
                logger.debug(f"Skipping {module_name}: could not parse")
                continue

            # Detect patterns
            patterns = self.pattern_detector.detect_all(node, info, self.graph)
            if patterns:
                sgraph.add_patterns(module_name, patterns)
                pattern_count += len(patterns)

            # Classify role
            role = self.role_classifier.classify(node, info, self.graph)
            sgraph.set_role(module_name, role)

            # Extract domain concepts
            domains = self.domain_analyzer.extract_concepts(node, info)
            if domains:
                sgraph.add_domain_concepts(module_name, domains)

            # Build semantic edges from class_bases
            self._build_inheritance_edges(sgraph, node, info)

        # Step 5: Compute pairwise similarity
        similarities = self.similarity_analyzer.compute_all(min_score=0.2)
        sgraph.set_similarities(similarities)

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            f"Semantic analysis complete: {module_count} modules, "
            f"{pattern_count} patterns, {len(similarities)} similarity pairs "
            f"in {elapsed:.0f}ms"
        )

        return sgraph

    def analyze_module(self, module_name: str) -> Dict[str, Any]:
        """
        Deep analysis of a single module.

        Returns the enriched node dict from SemanticGraph.get_enriched_node().
        """
        node = self.graph.get_node(module_name)
        if not node:
            return {"error": f"Module '{module_name}' not found in graph"}

        info = self._get_module_info(node)

        # Run per-module analysis
        patterns = self.pattern_detector.detect_all(node, info, self.graph) if info else []
        role = self.role_classifier.classify(node, info, self.graph) if info else None
        domains = self.domain_analyzer.extract_concepts(node, info) if info else []

        # Build a temporary SemanticGraph with just this module's data
        sgraph = SemanticGraph(graph=self.graph)
        if patterns:
            sgraph.add_patterns(module_name, patterns)
        if role:
            sgraph.set_role(module_name, role)
        if domains:
            sgraph.add_domain_concepts(module_name, domains)
        if info:
            self._build_inheritance_edges(sgraph, node, info)

        # Compute similarity for this module against all others
        for other_node in self.graph.iter_nodes():
            if other_node.name == module_name:
                continue
            score = self.similarity_analyzer.compute_similarity(module_name, other_node.name)
            if score.score >= 0.2:
                sgraph._similarities.append(score)

        return sgraph.get_enriched_node(module_name)

    # ------------------------------------------------------------------
    # Semantic edge construction
    # ------------------------------------------------------------------

    def _build_inheritance_edges(
        self,
        sgraph: SemanticGraph,
        node: Node,
        info: ModuleInfo,
    ) -> None:
        """Build semantic edges from class hierarchy data."""
        for cls_name, bases in info.class_bases.items():
            for base in bases:
                # Try to find which module defines the base class
                target_module = self._resolve_class_module(base, node.name)
                if target_module and target_module != node.name:
                    sgraph.add_semantic_edge(
                        source=node.name,
                        target=target_module,
                        relation_type="inherits",
                        description=f"'{cls_name}' inherits from '{base}'",
                        confidence=0.95,
                    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_module_info(self, node: Node) -> Optional[ModuleInfo]:
        """Get ModuleInfo for a node, parsing if needed."""
        # Try parser cache first
        info = self.parser.get_info(node.name)
        if info:
            return info

        # Parse the file directly
        file_path = Path(node.file_path)
        if file_path.exists():
            return self.parser.parse_file(file_path)

        return None

    def _resolve_class_module(self, class_name: str, current_module: str) -> Optional[str]:
        """
        Try to find which module defines a given class name.

        Strategy:
        1. Check if it's defined in the same module
        2. Check immediate imports for matching module names
        3. Scan all nodes for the class name in their class list
        """
        # Check same module
        node = self.graph.get_node(current_module)
        if node and class_name in node.classes:
            return current_module

        # Check immediate dependencies
        for dep_name in self.graph.immediate_dependencies(current_module):
            dep_node = self.graph.get_node(dep_name)
            if dep_node and class_name in dep_node.classes:
                return dep_name

        # Broader scan (limited to 50 nodes for performance)
        count = 0
        for node in self.graph.iter_nodes():
            if count >= 50:
                break
            if class_name in node.classes:
                return node.name
            count += 1

        return None
