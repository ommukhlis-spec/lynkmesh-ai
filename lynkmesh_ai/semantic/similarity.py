"""
SimilarityAnalyzer — computes structural similarity between modules.

All similarity measures are pure heuristics; no embeddings or ML.
Uses Jaccard similarity, naming overlap, co-coupling, and structural
equivalence to find modules that are "similar" in purpose or design.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from lynkmesh_ai.core.graph import DependencyGraph, Node
from lynkmesh_ai.semantic.graph import SimilarityScore

logger = logging.getLogger(__name__)


class SimilarityAnalyzer:
    """
    Computes pairwise structural similarity between modules.

    Dimensions:
    1. Shared dependencies (Jaccard similarity of import sets)
    2. Naming similarity (token overlap in module paths)
    3. Co-coupling (shared dependents — "used together")
    4. Structural equivalence (similar LOC, class count, function count)
    """

    def __init__(self, graph: DependencyGraph) -> None:
        self.graph = graph
        self._nodes = list(graph.iter_nodes())

        # Precompute node data for efficient pairwise computation
        self._import_sets: Dict[str, Set[str]] = {}
        self._dependent_sets: Dict[str, Set[str]] = {}
        for node in self._nodes:
            self._import_sets[node.name] = set(graph.immediate_dependencies(node.name))
            self._dependent_sets[node.name] = set(graph.immediate_dependents(node.name))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_all(self, min_score: float = 0.2) -> List[SimilarityScore]:
        """
        Compute similarity for all pairs of modules.

        For N modules, this does O(N^2) comparisons. Each comparison
        is O(D) where D is average dependency count. For codebases
        under 500 modules, this takes milliseconds.

        Args:
            min_score: Minimum combined score to include in results.

        Returns:
            List of SimilarityScore, sorted by score descending.
        """
        results: List[SimilarityScore] = []
        n = len(self._nodes)

        for i in range(n):
            for j in range(i + 1, n):
                node_a = self._nodes[i]
                node_b = self._nodes[j]

                score = self.compute_similarity(node_a.name, node_b.name)
                if score.score >= min_score:
                    results.append(score)

        results.sort(key=lambda s: s.score, reverse=True)
        logger.info(f"Computed {len(results)} similarity pairs above threshold {min_score}")
        return results

    def compute_similarity(self, module_a: str, module_b: str) -> SimilarityScore:
        """
        Compute combined similarity between two modules.

        Returns a single SimilarityScore with aggregate score and
        the dominant basis.
        """
        if module_a == module_b:
            return SimilarityScore(module_a=module_a, module_b=module_b, score=1.0, basis="identity")

        scores: Dict[str, float] = {}
        scores["shared_deps"] = self._shared_dependency_jaccard(module_a, module_b)
        scores["naming"] = self._naming_similarity(module_a, module_b)
        scores["co_coupling"] = self._co_coupling_similarity(module_a, module_b)
        scores["structural"] = self._structural_equivalence(module_a, module_b)

        # Weighted combination
        composite = (
            scores["shared_deps"] * 0.35 +
            scores["naming"] * 0.30 +
            scores["co_coupling"] * 0.20 +
            scores["structural"] * 0.15
        )

        # Determine primary basis
        basis = max(scores, key=lambda k: scores[k])

        return SimilarityScore(
            module_a=module_a,
            module_b=module_b,
            score=round(composite, 3),
            basis=basis,
        )

    # ------------------------------------------------------------------
    # Similarity dimensions
    # ------------------------------------------------------------------

    def _shared_dependency_jaccard(self, a: str, b: str) -> float:
        """
        Jaccard similarity of dependency sets.

        If two modules import the same things, they likely serve
        similar purposes.
        """
        imports_a = self._import_sets.get(a, set())
        imports_b = self._import_sets.get(b, set())

        if not imports_a and not imports_b:
            return 0.0

        intersection = len(imports_a & imports_b)
        union = len(imports_a | imports_b)

        if union == 0:
            return 0.0
        return intersection / union

    def _naming_similarity(self, a: str, b: str) -> float:
        """
        Token overlap in module path segments.

        Two modules in similar packages or with similar names
        (e.g., 'auth.service' and 'auth.controller') get higher scores.
        """
        tokens_a = set(_tokenize_module_name(a))
        tokens_b = set(_tokenize_module_name(b))

        if not tokens_a or not tokens_b:
            return 0.0

        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)

        # Bonus for shared package prefix
        prefix_len = _common_prefix_length(a.split("."), b.split("."))
        prefix_bonus = min(prefix_len * 0.15, 0.3)

        if union == 0:
            return prefix_bonus

        base = intersection / union
        return min(base + prefix_bonus, 1.0)

    def _co_coupling_similarity(self, a: str, b: str) -> float:
        """
        Co-coupling: modules are similar if they share dependents.

        If many modules depend on both A and B, A and B are likely
        used together and serve related purposes.
        """
        dependents_a = self._dependent_sets.get(a, set())
        dependents_b = self._dependent_sets.get(b, set())

        if not dependents_a and not dependents_b:
            return 0.0

        intersection = len(dependents_a & dependents_b)
        union = len(dependents_a | dependents_b)

        if union == 0:
            return 0.0
        return intersection / union

    def _structural_equivalence(self, a: str, b: str) -> float:
        """
        Structural similarity based on code metrics.

        Compares: lines of code, class count, function count, import count.
        """
        node_a = self.graph.get_node(a)
        node_b = self.graph.get_node(b)

        if not node_a or not node_b:
            return 0.0

        scores = []

        def _ratio(x: int, y: int) -> float:
            if x == 0 and y == 0:
                return 1.0
            if x == 0 or y == 0:
                return 0.0
            return min(x, y) / max(x, y)

        scores.append(_ratio(node_a.lines_of_code, node_b.lines_of_code))
        scores.append(_ratio(len(node_a.classes), len(node_b.classes)))
        scores.append(_ratio(len(node_a.functions), len(node_b.functions)))
        scores.append(_ratio(len(node_a.imports), len(node_b.imports)))

        return sum(scores) / len(scores)


# ------------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------------


def _tokenize_module_name(name: str) -> List[str]:
    """Split a dotted module name into tokens, filtering noise."""
    tokens = []
    for part in name.lower().replace("-", "_").split("."):
        # Split on underscores for compound names
        sub_parts = part.split("_")
        for sp in sub_parts:
            if len(sp) >= 2 and sp not in ("py", "the", "and", "for", "src"):
                tokens.append(sp)
    return tokens


def _common_prefix_length(a: List[str], b: List[str]) -> int:
    """Count the length of the common prefix of two sequences."""
    n = 0
    for x, y in zip(a, b):
        if x == y:
            n += 1
        else:
            break
    return n
