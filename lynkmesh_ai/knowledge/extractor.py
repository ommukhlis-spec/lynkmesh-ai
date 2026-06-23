"""
KnowledgeExtractor — bridges SemanticGraph data into KnowledgeBase facts.

Converts each dimension of semantic analysis (patterns, roles, domains,
edges, similarity) into canonical KnowledgeFact objects.
"""

from __future__ import annotations

import logging
from typing import List

from lynkmesh_ai.semantic.graph import SemanticGraph
from lynkmesh_ai.knowledge.fact import KnowledgeFact
from lynkmesh_ai.knowledge.base import KnowledgeBase

logger = logging.getLogger(__name__)


class KnowledgeExtractor:
    """
    Extracts KnowledgeFacts from a populated SemanticGraph.

    Transforms rich semantic analysis into queryable, persistable
    subject-predicate-object facts.
    """

    def __init__(self, semantic_graph: SemanticGraph) -> None:
        self.sgraph = semantic_graph
        self._fact_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_all(self) -> List[KnowledgeFact]:
        """Run all extractors and return merged, deduplicated fact list."""
        facts: List[KnowledgeFact] = []
        facts.extend(self._extract_pattern_facts())
        facts.extend(self._extract_role_facts())
        facts.extend(self._extract_domain_facts())
        facts.extend(self._extract_edge_facts())
        facts.extend(self._extract_similarity_facts())
        return facts

    def build_knowledge_base(self) -> KnowledgeBase:
        """Convenience: extract facts into a new KnowledgeBase."""
        kb = KnowledgeBase()
        kb.add_facts(self.extract_all())
        return kb

    # ------------------------------------------------------------------
    # Fact extractors
    # ------------------------------------------------------------------

    def _extract_pattern_facts(self) -> List[KnowledgeFact]:
        """Extract pattern facts: {module} implements_pattern {pattern_name}."""
        facts: List[KnowledgeFact] = []
        for module, patterns in self.sgraph.get_all_patterns().items():
            for pm in patterns:
                facts.append(KnowledgeFact(
                    fact_id=self._next_id(),
                    fact_type="pattern",
                    subject=module,
                    predicate="implements_pattern",
                    object_value=pm.pattern,
                    confidence=pm.confidence,
                    evidence=pm.evidence,
                    source="PatternDetector",
                ))
        return facts

    def _extract_role_facts(self) -> List[KnowledgeFact]:
        """Extract role facts: {module} has_role {role_name}."""
        facts: List[KnowledgeFact] = []
        for module, role in self.sgraph.get_all_roles().items():
            facts.append(KnowledgeFact(
                fact_id=self._next_id(),
                fact_type="role",
                subject=module,
                predicate="has_role",
                object_value=role.role,
                confidence=role.confidence,
                evidence=role.evidence,
                source="RoleClassifier",
            ))
        return facts

    def _extract_domain_facts(self) -> List[KnowledgeFact]:
        """Extract domain facts: {module} belongs_to_domain {concept}."""
        facts: List[KnowledgeFact] = []
        for module, concepts in self.sgraph.get_all_domains().items():
            for dc in concepts:
                facts.append(KnowledgeFact(
                    fact_id=self._next_id(),
                    fact_type="domain",
                    subject=module,
                    predicate="belongs_to_domain",
                    object_value=dc.concept,
                    confidence=dc.confidence,
                    evidence=[f"Source: {dc.source}"],
                    source="DomainAnalyzer",
                ))
        return facts

    def _extract_edge_facts(self) -> List[KnowledgeFact]:
        """Extract relationship facts from semantic edges."""
        facts: List[KnowledgeFact] = []
        for edge in self.sgraph.iter_semantic_edges():
            # Map edge relation_type to predicate
            predicate_map = {
                "inherits": "inherits_from",
                "implements": "implements_interface",
                "creates": "creates_instance_of",
                "belongs_to_domain": "belongs_to_domain",
            }
            predicate = predicate_map.get(edge.relation_type, "semantic_relationship")
            facts.append(KnowledgeFact(
                fact_id=self._next_id(),
                fact_type="relationship",
                subject=edge.source,
                predicate=predicate,
                object_value=edge.target,
                confidence=edge.confidence,
                evidence=[edge.description] if edge.description else [],
                source="SemanticGraph",
            ))
        return facts

    def _extract_similarity_facts(self) -> List[KnowledgeFact]:
        """Extract similarity facts: {module_a} is_similar_to {module_b}. Only high-confidence pairs."""
        facts: List[KnowledgeFact] = []
        for sim in self.sgraph.get_similarities(min_score=0.4):
            facts.append(KnowledgeFact(
                fact_id=self._next_id(),
                fact_type="similarity",
                subject=sim.module_a,
                predicate="is_similar_to",
                object_value=sim.module_b,
                confidence=sim.score,
                evidence=[f"Basis: {sim.basis}"],
                source="SimilarityAnalyzer",
            ))
        return facts

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> str:
        self._fact_counter += 1
        return f"fact_{self._fact_counter:06d}"
