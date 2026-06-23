"""
KnowledgeBase — schema-less fact store with typed query capabilities.

Follows the StateStore persistence pattern (to_dict/from_dict/save/load).
Provides querying by fact_type, subject, predicate, and full-text search.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

from lynkmesh_ai.knowledge.fact import KnowledgeFact

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    Persistent, queryable store of architectural knowledge facts.

    Schema-less: facts are stored as a flat list with in-memory indexes
    for efficient typed queries. Follows the StateStore serialization
    pattern exactly.
    """

    def __init__(self) -> None:
        self._facts: List[KnowledgeFact] = []
        self._by_type: Dict[str, List[KnowledgeFact]] = defaultdict(list)
        self._by_subject: Dict[str, List[KnowledgeFact]] = defaultdict(list)
        self._by_predicate: Dict[str, List[KnowledgeFact]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Fact management
    # ------------------------------------------------------------------

    def add_fact(self, fact: KnowledgeFact) -> None:
        """Add a single fact (deduplicates by identity)."""
        if fact in self._facts:
            # Update existing fact's confidence
            existing = self._facts[self._facts.index(fact)]
            existing.confidence = max(existing.confidence, fact.confidence)
            return
        self._facts.append(fact)
        self._by_type[fact.fact_type].append(fact)
        self._by_subject[fact.subject].append(fact)
        self._by_predicate[fact.predicate].append(fact)

    def add_facts(self, facts: List[KnowledgeFact]) -> None:
        """Add multiple facts."""
        for fact in facts:
            self.add_fact(fact)
        logger.debug(f"Added {len(facts)} facts; total: {self.fact_count}")

    def remove_fact(self, fact_id: str) -> None:
        """Remove a fact by ID."""
        for i, fact in enumerate(self._facts):
            if fact.fact_id == fact_id:
                del self._facts[i]
                self._by_type[fact.fact_type].remove(fact)
                self._by_subject[fact.subject].remove(fact)
                self._by_predicate[fact.predicate].remove(fact)
                return

    def all_facts(self) -> List[KnowledgeFact]:
        """Return all facts."""
        return list(self._facts)

    def iter_facts(self) -> Iterator[KnowledgeFact]:
        yield from self._facts

    @property
    def fact_count(self) -> int:
        return len(self._facts)

    # ------------------------------------------------------------------
    # Typed queries
    # ------------------------------------------------------------------

    def query(
        self,
        fact_type: Optional[str] = None,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
    ) -> List[KnowledgeFact]:
        """
        Query facts with optional filters.

        All filters are ANDed together. Returns facts matching all
        specified criteria.
        """
        # Start with the smallest candidate set
        candidates: Optional[List[KnowledgeFact]] = None

        if fact_type:
            candidates = self._by_type.get(fact_type, [])
        if subject:
            sub_facts = self._by_subject.get(subject, [])
            if candidates is None:
                candidates = sub_facts
            else:
                candidates = [f for f in candidates if f in sub_facts]
        if predicate:
            pred_facts = self._by_predicate.get(predicate, [])
            if candidates is None:
                candidates = pred_facts
            else:
                candidates = [f for f in candidates if f in pred_facts]

        if candidates is None:
            return self.all_facts()

        return sorted(candidates, key=lambda f: f.confidence, reverse=True)

    def get_facts_for_module(self, module: str) -> List[KnowledgeFact]:
        """Get all facts about a specific module."""
        return self._by_subject.get(module, [])

    def get_facts_by_type(self, fact_type: str) -> List[KnowledgeFact]:
        """Get all facts of a given type."""
        return self._by_type.get(fact_type, [])

    def get_facts_by_predicate(self, predicate: str) -> List[KnowledgeFact]:
        """Get all facts with a given predicate."""
        return self._by_predicate.get(predicate, [])

    # ------------------------------------------------------------------
    # Convenience queries
    # ------------------------------------------------------------------

    def get_role(self, module: str) -> Optional[str]:
        """Get the architectural role of a module, if known."""
        for fact in self._by_subject.get(module, []):
            if fact.predicate == "has_role":
                return fact.object_value
        return None

    def get_patterns(self, module: str) -> List[str]:
        """Get design patterns implemented by a module."""
        patterns = []
        for fact in self._by_subject.get(module, []):
            if fact.predicate == "implements_pattern":
                patterns.append(fact.object_value)
        return patterns

    def get_domain_concepts(self, module: str) -> List[str]:
        """Get domain concepts for a module."""
        concepts = []
        for fact in self._by_subject.get(module, []):
            if fact.predicate == "belongs_to_domain":
                concepts.append(fact.object_value)
        return concepts

    def get_modules_for_domain(self, domain: str) -> List[str]:
        """Get all modules belonging to a specific domain."""
        modules: Set[str] = set()
        for fact in self._by_predicate.get("belongs_to_domain", []):
            if fact.object_value == domain:
                modules.add(fact.subject)
        return sorted(modules)

    def get_all_domains(self) -> List[str]:
        """Get all unique domain concepts."""
        domains: Set[str] = set()
        for fact in self._by_predicate.get("belongs_to_domain", []):
            domains.add(fact.object_value)
        return sorted(domains)

    def get_all_roles(self) -> Dict[str, str]:
        """Get module → role mapping."""
        roles: Dict[str, str] = {}
        for fact in self._by_predicate.get("has_role", []):
            roles[fact.subject] = fact.object_value
        return roles

    def get_all_patterns(self) -> Dict[str, List[str]]:
        """Get module → patterns mapping."""
        patterns: Dict[str, List[str]] = defaultdict(list)
        for fact in self._by_predicate.get("implements_pattern", []):
            patterns[fact.subject].append(fact.object_value)
        return dict(patterns)

    def get_all_relationships(self) -> List[KnowledgeFact]:
        """Get all semantic relationship facts."""
        return self._by_predicate.get("semantic_relationship", [])

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, text: str) -> List[KnowledgeFact]:
        """
        Full-text search across all fact fields.

        Matches against subject, predicate, object_value, evidence,
        and fact_type. Case-insensitive.
        """
        text_lower = text.lower()
        results = []
        for fact in self._facts:
            if (
                text_lower in fact.subject.lower()
                or text_lower in fact.predicate.lower()
                or text_lower in fact.object_value.lower()
                or text_lower in fact.fact_type.lower()
                or any(text_lower in e.lower() for e in fact.evidence)
            ):
                results.append(fact)
        return sorted(results, key=lambda f: f.confidence, reverse=True)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def compute_risk_scores(self) -> Dict[str, str]:
        """
        Augment risk using semantic factors.

        Factors:
        - Modules implementing multiple patterns → higher risk
        - Controller/Service roles → higher risk
        - Modules in core_domain → higher risk
        - Modules with high dependency count → higher risk
        """
        scores: Dict[str, str] = {}

        for module, facts in self._by_subject.items():
            risk_points = 0

            # Pattern complexity
            pattern_count = sum(1 for f in facts if f.predicate == "implements_pattern")
            risk_points += pattern_count

            # Role centrality
            for f in facts:
                if f.predicate == "has_role":
                    if f.object_value in ("controller", "service"):
                        risk_points += 2
                    elif f.object_value in ("middleware", "repository"):
                        risk_points += 1
                    break

            # Domain criticality
            for f in facts:
                if f.predicate == "belongs_to_domain" and f.object_value == "core_domain":
                    risk_points += 1
                    break

            # Classify
            if risk_points >= 5:
                scores[module] = "critical"
            elif risk_points >= 3:
                scores[module] = "high"
            elif risk_points >= 2:
                scores[module] = "medium"
            elif risk_points >= 1:
                scores[module] = "low"
            else:
                scores[module] = "none"

        return scores

    # ------------------------------------------------------------------
    # Decision Memory — architecture decisions, constraints, learned patterns
    # ------------------------------------------------------------------

    def get_decisions(self) -> List[KnowledgeFact]:
        """Get all architecture decision facts."""
        return self._by_type.get("architecture_decision", [])

    def get_design_constraints(self, module: Optional[str] = None) -> List[KnowledgeFact]:
        """Get all design constraint facts, optionally filtered by module."""
        facts = self._by_type.get("design_constraint", [])
        if module:
            facts = [f for f in facts if f.subject == module]
        return facts

    def get_learned_patterns(self) -> List[KnowledgeFact]:
        """Get all learned pattern facts."""
        return self._by_type.get("learned_pattern", [])

    def record_decision(
        self,
        title: str,
        context: str,
        decision: str,
        rationale: str,
        related_modules: Optional[List[str]] = None,
    ) -> KnowledgeFact:
        """Record an architecture decision as a knowledge fact."""
        subject = ",".join(related_modules) if related_modules else "system"
        fact = KnowledgeFact(
            fact_id=f"adr_{len(self._by_type.get('architecture_decision', [])) + 1:04d}",
            fact_type="architecture_decision",
            subject=subject,
            predicate="has_decision",
            object_value=title,
            confidence=0.9,
            evidence=[
                f"Context: {context[:200]}",
                f"Decision: {decision[:200]}",
                f"Rationale: {rationale[:200]}",
            ],
            source="KnowledgeBase",
        )
        self.add_fact(fact)
        return fact

    def record_constraint(
        self,
        module: str,
        constraint: str,
        rationale: str = "",
    ) -> KnowledgeFact:
        """Record a design constraint for a module."""
        fact = KnowledgeFact(
            fact_id=f"dc_{module}_{len(self._by_subject.get(module, []))}",
            fact_type="design_constraint",
            subject=module,
            predicate="has_constraint",
            object_value=constraint,
            confidence=0.85,
            evidence=[rationale] if rationale else [],
            source="KnowledgeBase",
        )
        self.add_fact(fact)
        return fact

    def record_learned_pattern(
        self,
        module: str,
        pattern: str,
        evidence: Optional[List[str]] = None,
    ) -> KnowledgeFact:
        """Record a learned pattern from architectural analysis."""
        fact = KnowledgeFact(
            fact_id=f"lp_{module}_{len(self._by_type.get('learned_pattern', []))}",
            fact_type="learned_pattern",
            subject=module,
            predicate="exhibits_pattern",
            object_value=pattern,
            confidence=0.8,
            evidence=evidence or [],
            source="KnowledgeBase",
        )
        self.add_fact(fact)
        return fact

    def get_decision_memory_summary(self) -> str:
        """Summary of the decision memory."""
        lines = [
            f"Architecture Decisions: {len(self.get_decisions())}",
            f"Design Constraints: {len(self.get_design_constraints())}",
            f"Learned Patterns: {len(self.get_learned_patterns())}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Serialization — same pattern as StateStore
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": [f.to_dict() for f in self._facts],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeBase":
        kb = cls()
        for f_data in data.get("facts", []):
            fact = KnowledgeFact.from_dict(f_data)
            kb.add_fact(fact)
        return kb

    def save(self, path: Path) -> None:
        """Persist knowledge base to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info(f"KnowledgeBase saved to {path} ({self.fact_count} facts)")

    @classmethod
    def load(cls, path: Path) -> "KnowledgeBase":
        """Load knowledge base from JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        kb = cls.from_dict(data)
        logger.info(f"KnowledgeBase loaded from {path} ({kb.fact_count} facts)")
        return kb

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = [
            f"=== Knowledge Base ===",
            f"Total Facts: {self.fact_count}",
        ]

        # Type breakdown
        type_counts: Dict[str, int] = {}
        for fact_type, facts in self._by_type.items():
            type_counts[fact_type] = len(facts)
        if type_counts:
            lines.append("Facts by Type:")
            for t, c in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {t}: {c}")

        # Domain coverage
        domains = self.get_all_domains()
        if domains:
            lines.append(f"Domains: {', '.join(domains[:20])}")

        # Unique modules
        modules = set(f.subject for f in self._facts)
        lines.append(f"Modules with Knowledge: {len(modules)}")

        return "\n".join(lines)
