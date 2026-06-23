"""Semantic AI layer — design patterns, architectural roles, domain analysis, similarity."""

from lynkmesh_ai.semantic.graph import (
    SemanticGraph,
    SemanticEdgeInfo,
    PatternMatch,
    RoleClassification,
    DomainConcept,
    SimilarityScore,
)
from lynkmesh_ai.semantic.patterns import PatternDetector
from lynkmesh_ai.semantic.roles import RoleClassifier, ArchitecturalRole
from lynkmesh_ai.semantic.domains import DomainAnalyzer
from lynkmesh_ai.semantic.similarity import SimilarityAnalyzer
from lynkmesh_ai.semantic.analyzer import SemanticAnalyzer

__all__ = [
    "SemanticGraph",
    "SemanticEdgeInfo",
    "PatternMatch",
    "RoleClassification",
    "DomainConcept",
    "SimilarityScore",
    "PatternDetector",
    "RoleClassifier",
    "ArchitecturalRole",
    "DomainAnalyzer",
    "SimilarityAnalyzer",
    "SemanticAnalyzer",
]
