"""
SemanticGraph — enriched dependency graph with semantic metadata.

Wraps DependencyGraph via composition (does NOT inherit).
Adds: semantic edges, design patterns, architectural roles,
domain concepts, and structural similarity data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

from lynkmesh_ai.core.graph import DependencyGraph, Node

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Type dataclasses
# ══════════════════════════════════════════════════════════════════════


@dataclass
class SemanticEdgeInfo:
    """A semantically-enriched relationship between two modules."""

    source: str
    target: str
    relation_type: str  # inherits, implements, creates, belongs_to_domain
    description: str = ""
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type,
            "description": self.description,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticEdgeInfo":
        return cls(
            source=data.get("source", ""),
            target=data.get("target", ""),
            relation_type=data.get("relation_type", ""),
            description=data.get("description", ""),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PatternMatch:
    """A design pattern detected in a module."""

    pattern: str  # e.g., "singleton", "factory", "repository"
    module: str
    class_name: str = ""
    confidence: float = 0.5
    evidence: List[str] = field(default_factory=list)
    location: str = ""  # file_path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern": self.pattern,
            "module": self.module,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "location": self.location,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatternMatch":
        return cls(
            pattern=data.get("pattern", ""),
            module=data.get("module", ""),
            class_name=data.get("class_name", ""),
            confidence=data.get("confidence", 0.5),
            evidence=data.get("evidence", []),
            location=data.get("location", ""),
        )


@dataclass
class RoleClassification:
    """Architectural role of a module."""

    role: str  # controller, service, repository, model, etc.
    confidence: float = 0.5
    evidence: List[str] = field(default_factory=list)
    module: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "module": self.module,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleClassification":
        return cls(
            role=data.get("role", "unknown"),
            confidence=data.get("confidence", 0.5),
            evidence=data.get("evidence", []),
            module=data.get("module", ""),
        )


@dataclass
class DomainConcept:
    """A domain concept extracted from code."""

    concept: str  # e.g., "authentication", "payment"
    module: str
    source: str = ""  # "name", "docstring", "class_name", "import"
    category: str = "generic"  # core_domain, supporting, generic, infrastructure
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept": self.concept,
            "module": self.module,
            "source": self.source,
            "category": self.category,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainConcept":
        return cls(
            concept=data.get("concept", ""),
            module=data.get("module", ""),
            source=data.get("source", ""),
            category=data.get("category", "generic"),
            confidence=data.get("confidence", 0.5),
        )


@dataclass
class SimilarityScore:
    """Structural similarity between two modules."""

    module_a: str
    module_b: str
    score: float  # 0.0 to 1.0
    basis: str = ""  # "shared_deps", "naming", "role", "co_change"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_a": self.module_a,
            "module_b": self.module_b,
            "score": self.score,
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimilarityScore":
        return cls(
            module_a=data.get("module_a", ""),
            module_b=data.get("module_b", ""),
            score=data.get("score", 0.0),
            basis=data.get("basis", ""),
        )


# ══════════════════════════════════════════════════════════════════════
# SemanticGraph
# ══════════════════════════════════════════════════════════════════════


class SemanticGraph:
    """
    Wraps a DependencyGraph with enriched semantic metadata.

    Composition (not inheritance) keeps semantic and core concerns separate.
    All core graph queries still go through self.graph.
    """

    def __init__(self, graph: DependencyGraph, name: str = "default") -> None:
        self.graph = graph
        self.name = name

        # Semantic edges (separate from core edges)
        self._semantic_edges: List[SemanticEdgeInfo] = []

        # Pattern matches: {module_name: [PatternMatch]}
        self._patterns: Dict[str, List[PatternMatch]] = {}

        # Role classifications: {module_name: RoleClassification}
        self._roles: Dict[str, RoleClassification] = {}

        # Domain concepts: {module_name: [DomainConcept]}
        self._domains: Dict[str, List[DomainConcept]] = {}

        # Similarity scores: flat list
        self._similarities: List[SimilarityScore] = []

    # ------------------------------------------------------------------
    # Semantic edge management
    # ------------------------------------------------------------------

    def add_semantic_edge(
        self,
        source: str,
        target: str,
        relation_type: str,
        description: str = "",
        confidence: float = 1.0,
    ) -> None:
        """Add a semantic relationship edge."""
        # Deduplicate
        for e in self._semantic_edges:
            if e.source == source and e.target == target and e.relation_type == relation_type:
                return
        edge = SemanticEdgeInfo(
            source=source,
            target=target,
            relation_type=relation_type,
            description=description,
            confidence=confidence,
        )
        self._semantic_edges.append(edge)

    def get_semantic_edges(
        self,
        relation_type: Optional[str] = None,
        module: Optional[str] = None,
    ) -> List[SemanticEdgeInfo]:
        """Query semantic edges with optional filters."""
        results = self._semantic_edges
        if relation_type:
            results = [e for e in results if e.relation_type == relation_type]
        if module:
            results = [e for e in results if e.source == module or e.target == module]
        return results

    def iter_semantic_edges(self) -> Iterator[SemanticEdgeInfo]:
        yield from self._semantic_edges

    @property
    def semantic_edge_count(self) -> int:
        return len(self._semantic_edges)

    # ------------------------------------------------------------------
    # Pattern management
    # ------------------------------------------------------------------

    def add_patterns(self, module: str, patterns: List[PatternMatch]) -> None:
        """Set pattern matches for a module (replaces existing)."""
        self._patterns[module] = patterns

    def get_patterns(self, module: str) -> List[PatternMatch]:
        """Get pattern matches for a module."""
        return self._patterns.get(module, [])

    def get_all_patterns(self) -> Dict[str, List[PatternMatch]]:
        """Get all pattern matches."""
        return dict(self._patterns)

    def get_patterns_by_type(self, pattern_type: str) -> Dict[str, List[PatternMatch]]:
        """Get all modules matching a specific pattern type."""
        result: Dict[str, List[PatternMatch]] = {}
        for mod, matches in self._patterns.items():
            filtered = [m for m in matches if m.pattern == pattern_type]
            if filtered:
                result[mod] = filtered
        return result

    def list_all_pattern_types(self) -> Set[str]:
        """Return all unique pattern types found across the codebase."""
        types: Set[str] = set()
        for matches in self._patterns.values():
            for m in matches:
                types.add(m.pattern)
        return types

    # ------------------------------------------------------------------
    # Role management
    # ------------------------------------------------------------------

    def set_role(self, module: str, role: RoleClassification) -> None:
        """Set architectural role for a module."""
        self._roles[module] = role

    def get_role(self, module: str) -> Optional[RoleClassification]:
        """Get architectural role for a module."""
        return self._roles.get(module)

    def get_all_roles(self) -> Dict[str, RoleClassification]:
        """Get all role classifications."""
        return dict(self._roles)

    def get_modules_by_role(self, role: str) -> List[str]:
        """Get all modules classified with a specific role."""
        return [mod for mod, r in self._roles.items() if r.role == role]

    # ------------------------------------------------------------------
    # Domain concept management
    # ------------------------------------------------------------------

    def add_domain_concepts(self, module: str, concepts: List[DomainConcept]) -> None:
        """Set domain concepts for a module."""
        self._domains[module] = concepts

    def get_domain_concepts(self, module: str) -> List[DomainConcept]:
        """Get domain concepts for a module."""
        return self._domains.get(module, [])

    def get_all_domains(self) -> Dict[str, List[DomainConcept]]:
        """Get all domain concept mappings."""
        return dict(self._domains)

    def get_unique_domains(self) -> List[str]:
        """Return all unique domain concept strings."""
        seen: Set[str] = set()
        for concepts in self._domains.values():
            for c in concepts:
                seen.add(c.concept)
        return sorted(seen)

    def get_modules_for_domain(self, domain: str) -> List[str]:
        """Get all modules belonging to a specific domain concept."""
        result = []
        for mod, concepts in self._domains.items():
            if any(c.concept == domain for c in concepts):
                result.append(mod)
        return result

    def get_domain_category_map(self) -> Dict[str, List[str]]:
        """Map category → list of domain concepts."""
        cat_map: Dict[str, Set[str]] = {}
        for concepts in self._domains.values():
            for c in concepts:
                cat_map.setdefault(c.category, set()).add(c.concept)
        return {k: sorted(v) for k, v in cat_map.items()}

    # ------------------------------------------------------------------
    # Similarity management
    # ------------------------------------------------------------------

    def set_similarities(self, similarities: List[SimilarityScore]) -> None:
        """Set similarity scores."""
        self._similarities = similarities

    def get_similarities(
        self,
        module: Optional[str] = None,
        min_score: float = 0.3,
    ) -> List[SimilarityScore]:
        """Query similarity scores."""
        results = self._similarities
        if module:
            results = [
                s for s in results
                if s.module_a == module or s.module_b == module
            ]
        results = [s for s in results if s.score >= min_score]
        return sorted(results, key=lambda s: s.score, reverse=True)

    def find_similar_modules(self, module: str, top_n: int = 5) -> List[SimilarityScore]:
        """Find the top-N most similar modules to a given module."""
        matches = []
        for s in self._similarities:
            if s.module_a == module:
                matches.append(SimilarityScore(module_a=s.module_b, module_b=module, score=s.score, basis=s.basis))
            elif s.module_b == module:
                matches.append(SimilarityScore(module_a=s.module_a, module_b=module, score=s.score, basis=s.basis))
        matches.sort(key=lambda s: s.score, reverse=True)
        return matches[:top_n]

    # ------------------------------------------------------------------
    # Enriched queries
    # ------------------------------------------------------------------

    def get_enriched_node(self, module: str) -> Dict[str, Any]:
        """Get a node with all semantic metadata attached."""
        node = self.graph.get_node(module)
        result: Dict[str, Any] = {
            "node": node.to_dict() if node else None,
            "role": None,
            "patterns": [],
            "domain_concepts": [],
            "semantic_edges_out": [],
            "semantic_edges_in": [],
            "similar_modules": [],
        }
        role = self.get_role(module)
        if role:
            result["role"] = role.to_dict()
        result["patterns"] = [p.to_dict() for p in self.get_patterns(module)]
        result["domain_concepts"] = [d.to_dict() for d in self.get_domain_concepts(module)]
        result["semantic_edges_out"] = [
            e.to_dict() for e in self.get_semantic_edges(module=module)
            if e.source == module
        ]
        result["semantic_edges_in"] = [
            e.to_dict() for e in self.get_semantic_edges(module=module)
            if e.target == module
        ]
        result["similar_modules"] = [
            s.to_dict() for s in self.find_similar_modules(module, top_n=5)
        ]
        return result

    def get_semantic_summary(self, module: str) -> str:
        """Human-readable semantic summary for a module."""
        lines = [f"=== Semantic Summary: {module} ===", ""]

        role = self.get_role(module)
        if role:
            lines.append(f"Architectural Role: {role.role} (confidence: {role.confidence:.0%})")
            if role.evidence:
                for e in role.evidence:
                    lines.append(f"  - {e}")
        else:
            lines.append("Architectural Role: unknown")
        lines.append("")

        patterns = self.get_patterns(module)
        if patterns:
            lines.append(f"Design Patterns ({len(patterns)}):")
            for p in patterns:
                lines.append(f"  - {p.pattern} (class: {p.class_name}, confidence: {p.confidence:.0%})")
        else:
            lines.append("Design Patterns: none detected")
        lines.append("")

        concepts = self.get_domain_concepts(module)
        if concepts:
            lines.append(f"Domain Concepts:")
            for c in concepts:
                lines.append(f"  - {c.concept} [{c.category}] (source: {c.source})")
        lines.append("")

        similar = self.find_similar_modules(module, top_n=3)
        if similar:
            lines.append("Most Similar Modules:")
            for s in similar:
                target = s.module_a if s.module_a != module else s.module_b
                lines.append(f"  - {target} (score: {s.score:.2f}, basis: {s.basis})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Serialization — same pattern as DependencyGraph
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "graph": self.graph.to_dict(),
            "semantic_edges": [e.to_dict() for e in self._semantic_edges],
            "patterns": {k: [p.to_dict() for p in v] for k, v in self._patterns.items()},
            "roles": {k: v.to_dict() for k, v in self._roles.items()},
            "domains": {k: [d.to_dict() for d in v] for k, v in self._domains.items()},
            "similarities": [s.to_dict() for s in self._similarities],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticGraph":
        graph = DependencyGraph.from_dict(data.get("graph", {}))
        sgraph = cls(graph=graph, name=data.get("name", "default"))

        sgraph._semantic_edges = [
            SemanticEdgeInfo.from_dict(e) for e in data.get("semantic_edges", [])
        ]
        sgraph._patterns = {
            k: [PatternMatch.from_dict(p) for p in v]
            for k, v in data.get("patterns", {}).items()
        }
        sgraph._roles = {
            k: RoleClassification.from_dict(v)
            for k, v in data.get("roles", {}).items()
        }
        sgraph._domains = {
            k: [DomainConcept.from_dict(d) for d in v]
            for k, v in data.get("domains", {}).items()
        }
        sgraph._similarities = [
            SimilarityScore.from_dict(s) for s in data.get("similarities", [])
        ]

        return sgraph

    def save(self, path: Path) -> None:
        """Persist semantic graph to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info(
            f"SemanticGraph saved to {path} "
            f"({self.graph.node_count} nodes, {self.semantic_edge_count} semantic edges)"
        )

    @classmethod
    def load(cls, path: Path) -> "SemanticGraph":
        """Load semantic graph from JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sgraph = cls.from_dict(data)
        logger.info(
            f"SemanticGraph loaded from {path} "
            f"({sgraph.graph.node_count} nodes, {sgraph.semantic_edge_count} semantic edges)"
        )
        return sgraph

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = [
            f"=== Semantic Graph: {self.name} ===",
            f"Base Graph Nodes: {self.graph.node_count}",
            f"Base Graph Edges: {self.graph.edge_count}",
            f"Semantic Edges: {self.semantic_edge_count}",
            f"Modules with Patterns: {len(self._patterns)}",
            f"Modules with Roles: {len(self._roles)}",
            f"Unique Domains: {len(self.get_unique_domains())}",
            f"Similarity Pairs: {len(self._similarities)}",
        ]
        # Role distribution
        role_counts: Dict[str, int] = {}
        for r in self._roles.values():
            role_counts[r.role] = role_counts.get(r.role, 0) + 1
        if role_counts:
            lines.append("Role Distribution:")
            for role, count in sorted(role_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {role}: {count}")
        # Pattern distribution
        if self._patterns:
            pattern_counts: Dict[str, int] = {}
            for matches in self._patterns.values():
                for m in matches:
                    pattern_counts[m.pattern] = pattern_counts.get(m.pattern, 0) + 1
            lines.append("Pattern Distribution:")
            for pat, count in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {pat}: {count}")
        return "\n".join(lines)
