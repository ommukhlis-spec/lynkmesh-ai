"""
KnowledgeFact — canonical subject-predicate-object fact representation.

All knowledge in the system is stored as facts with typed predicates,
confidence scores, and provenance metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class KnowledgeFact:
    """
    A single architectural knowledge fact.

    Uses subject-predicate-object structure:
    - subject: The module this fact is about (e.g., "auth.service")
    - predicate: The relationship or property (e.g., "has_role", "implements_pattern")
    - object_value: The value (e.g., "service", "singleton")
    """

    fact_id: str
    fact_type: str       # "pattern", "role", "domain", "relationship", "inferred_risk"
    subject: str          # Module name
    predicate: str        # e.g., "implements_pattern", "has_role", "belongs_to_domain"
    object_value: str     # e.g., "singleton", "controller", "payment"
    confidence: float = 1.0
    evidence: List[str] = field(default_factory=list)
    source: str = ""      # Which analyzer produced this fact
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "fact_type": self.fact_type,
            "subject": self.subject,
            "predicate": self.predicate,
            "object_value": self.object_value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "source": self.source,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeFact":
        return cls(
            fact_id=data.get("fact_id", ""),
            fact_type=data.get("fact_type", ""),
            subject=data.get("subject", ""),
            predicate=data.get("predicate", ""),
            object_value=data.get("object_value", ""),
            confidence=data.get("confidence", 1.0),
            evidence=data.get("evidence", []),
            source=data.get("source", ""),
            timestamp=data.get("timestamp", ""),
        )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def __hash__(self) -> int:
        return hash((self.subject, self.predicate, self.object_value))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, KnowledgeFact):
            return NotImplemented
        return (
            self.subject == other.subject
            and self.predicate == other.predicate
            and self.object_value == other.object_value
        )

    def __repr__(self) -> str:
        return (
            f"KnowledgeFact({self.subject} --[{self.predicate}]--> {self.object_value})"
        )
