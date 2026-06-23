"""
DomainAnalyzer — extracts domain concepts from module names, class names,
docstrings, and package structures.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set

from lynkmesh_ai.core.graph import Node
from lynkmesh_ai.core.parser import ModuleInfo
from lynkmesh_ai.semantic.graph import DomainConcept

logger = logging.getLogger(__name__)


class DomainAnalyzer:
    """
    Extracts domain-level concepts from code artifacts.

    Domain concepts are business-relevant terms (like "authentication",
    "payment", "billing") that describe what the code is about, not how
    it's implemented.
    """

    # Common domain keywords mapped to categories
    DOMAIN_KEYWORDS: Dict[str, str] = {
        # Core business domains
        "auth": "core_domain",
        "authentication": "core_domain",
        "authorization": "core_domain",
        "login": "core_domain",
        "user": "core_domain",
        "account": "core_domain",
        "profile": "core_domain",
        "payment": "core_domain",
        "billing": "core_domain",
        "invoice": "core_domain",
        "transaction": "core_domain",
        "order": "core_domain",
        "checkout": "core_domain",
        "subscription": "core_domain",
        "product": "core_domain",
        "inventory": "core_domain",
        "catalog": "core_domain",
        "customer": "core_domain",
        "merchant": "core_domain",
        "content": "core_domain",
        "search": "core_domain",
        "recommendation": "core_domain",
        "review": "core_domain",
        "rating": "core_domain",

        # Supporting domains
        "notification": "supporting",
        "email": "supporting",
        "sms": "supporting",
        "messaging": "supporting",
        "message": "supporting",
        "report": "supporting",
        "analytics": "supporting",
        "metrics": "supporting",
        "monitoring": "supporting",
        "audit": "supporting",
        "compliance": "supporting",
        "workflow": "supporting",
        "scheduling": "supporting",
        "scheduler": "supporting",
        "export": "supporting",
        "import": "supporting",
        "upload": "supporting",
        "download": "supporting",

        # Infrastructure
        "log": "infrastructure",
        "logging": "infrastructure",
        "cache": "infrastructure",
        "caching": "infrastructure",
        "database": "infrastructure",
        "storage": "infrastructure",
        "queue": "infrastructure",
        "worker": "infrastructure",
        "task": "infrastructure",
        "job": "infrastructure",
        "pipeline": "infrastructure",
        "backup": "infrastructure",
        "migration": "infrastructure",
        "deployment": "infrastructure",
        "health": "infrastructure",
        "status": "infrastructure",

        # Generic / cross-cutting
        "util": "generic",
        "utils": "generic",
        "utility": "generic",
        "helper": "generic",
        "common": "generic",
        "shared": "generic",
        "base": "generic",
        "core": "generic",
        "types": "generic",
        "constant": "generic",
        "constants": "generic",
    }

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_concepts(self, node: Node, info: ModuleInfo) -> List[DomainConcept]:
        """
        Extract all domain concepts from a module.

        Returns a list of DomainConcept objects, deduplicated by concept string.
        """
        concepts: List[DomainConcept] = []
        seen: Set[str] = set()

        for concept in (
            self._from_module_name(node) +
            self._from_class_names(node) +
            self._from_docstring(info) +
            self._from_package_structure(node)
        ):
            if concept.concept not in seen:
                seen.add(concept.concept)
                concepts.append(concept)

        return concepts

    # ------------------------------------------------------------------
    # Extraction sources
    # ------------------------------------------------------------------

    @classmethod
    def _from_module_name(cls, node: Node) -> List[DomainConcept]:
        """Extract concepts from the module's dotted path segments."""
        concepts: List[DomainConcept] = []
        path_parts = node.name.lower().replace("-", "_").replace("/", ".").split(".")

        for part in path_parts:
            # Skip empty, private, and very short segments
            if not part or part.startswith("_") or len(part) < 2:
                continue

            # Direct match
            if part in cls.DOMAIN_KEYWORDS:
                concepts.append(DomainConcept(
                    concept=part,
                    module=node.name,
                    source="module_name",
                    category=cls.DOMAIN_KEYWORDS[part],
                    confidence=0.8,
                ))
                continue

            # Partial match (e.g., "github_auth" → auth)
            for keyword, category in cls.DOMAIN_KEYWORDS.items():
                if len(keyword) >= 3 and keyword in part and keyword != part:
                    concepts.append(DomainConcept(
                        concept=keyword,
                        module=node.name,
                        source="module_name_partial",
                        category=category,
                        confidence=0.5,
                    ))
                    break

        return concepts

    @classmethod
    def _from_class_names(cls, node: Node) -> List[DomainConcept]:
        """Extract concepts from class names."""
        concepts: List[DomainConcept] = []

        for cls_name in node.classes:
            # Split CamelCase into tokens
            tokens = _split_camel_case(cls_name)
            for token in tokens:
                token_lower = token.lower()
                if token_lower in cls.DOMAIN_KEYWORDS:
                    concepts.append(DomainConcept(
                        concept=token_lower,
                        module=node.name,
                        source="class_name",
                        category=cls.DOMAIN_KEYWORDS[token_lower],
                        confidence=0.7,
                    ))

        return concepts

    @classmethod
    def _from_docstring(cls, info: ModuleInfo) -> List[DomainConcept]:
        """Extract concepts from module docstring."""
        concepts: List[DomainConcept] = []
        if not info.docstring:
            return concepts

        doc_lower = info.docstring.lower()
        # Split into words
        words = set(re.findall(r'\b[a-z][a-z_]{2,}\b', doc_lower))

        for word in words:
            if word in cls.DOMAIN_KEYWORDS:
                concepts.append(DomainConcept(
                    concept=word,
                    module=info.name,
                    source="docstring",
                    category=cls.DOMAIN_KEYWORDS[word],
                    confidence=0.6,
                ))

        return concepts

    @classmethod
    def _from_package_structure(cls, node: Node) -> List[DomainConcept]:
        """Extract concepts from the package hierarchy."""
        concepts: List[DomainConcept] = []
        if not node.package:
            return concepts

        package_lower = node.package.lower()
        if package_lower in cls.DOMAIN_KEYWORDS:
            concepts.append(DomainConcept(
                concept=package_lower,
                module=node.name,
                source="package",
                category=cls.DOMAIN_KEYWORDS[package_lower],
                confidence=0.75,
            ))

        return concepts


def _split_camel_case(name: str) -> List[str]:
    """Split a CamelCase or PascalCase name into tokens."""
    if not name:
        return []
    # Insert space before uppercase letters following lowercase
    s1 = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    # Insert space before uppercase following uppercase then lowercase
    s2 = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', s1)
    return s2.split()
