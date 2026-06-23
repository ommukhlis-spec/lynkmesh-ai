"""
RoleClassifier — classifies modules by architectural role.

Uses three heuristics: naming conventions, structural analysis,
and graph position (fan-in/fan-out centrality).
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, List, Optional, Set

from lynkmesh_ai.core.graph import DependencyGraph, Node
from lynkmesh_ai.core.parser import ModuleInfo
from lynkmesh_ai.semantic.graph import RoleClassification

logger = logging.getLogger(__name__)


class ArchitecturalRole(str, Enum):
    """Canonical architectural roles for modules."""

    CONTROLLER = "controller"      # Handles requests/input/routing
    SERVICE = "service"            # Business logic layer
    REPOSITORY = "repository"      # Data access / persistence
    MODEL = "model"                # Data models / entities / DTOs
    CONFIG = "config"              # Configuration / settings
    UTILITY = "utility"            # Helper / shared utilities
    INTERFACE = "interface"        # Abstract base / protocol definition
    MIDDLEWARE = "middleware"      # Processing pipeline / hooks
    ADAPTER = "adapter"            # External integration / wrapper
    FACTORY = "factory"            # Object creation / DI
    VIEW = "view"                  # Presentation / UI components
    CLI = "cli"                    # CLI entry point / script
    UNKNOWN = "unknown"            # Cannot classify


class RoleClassifier:
    """
    Classifies each module into an ArchitecturalRole.

    Combines three independent heuristics, weighted:
    - Naming: 0.45 weight (most reliable)
    - Structure: 0.35 weight
    - Graph position: 0.20 weight
    """

    # Path segment → role mappings
    NAMING_RULES: Dict[str, ArchitecturalRole] = {
        "controller": ArchitecturalRole.CONTROLLER,
        "controllers": ArchitecturalRole.CONTROLLER,
        "handler": ArchitecturalRole.CONTROLLER,
        "handlers": ArchitecturalRole.CONTROLLER,
        "router": ArchitecturalRole.CONTROLLER,
        "routes": ArchitecturalRole.CONTROLLER,
        "endpoint": ArchitecturalRole.CONTROLLER,
        "service": ArchitecturalRole.SERVICE,
        "services": ArchitecturalRole.SERVICE,
        "usecase": ArchitecturalRole.SERVICE,
        "use_case": ArchitecturalRole.SERVICE,
        "business": ArchitecturalRole.SERVICE,
        "logic": ArchitecturalRole.SERVICE,
        "repository": ArchitecturalRole.REPOSITORY,
        "repositories": ArchitecturalRole.REPOSITORY,
        "store": ArchitecturalRole.REPOSITORY,
        "dao": ArchitecturalRole.REPOSITORY,
        "datastore": ArchitecturalRole.REPOSITORY,
        "model": ArchitecturalRole.MODEL,
        "models": ArchitecturalRole.MODEL,
        "entity": ArchitecturalRole.MODEL,
        "entities": ArchitecturalRole.MODEL,
        "dto": ArchitecturalRole.MODEL,
        "schema": ArchitecturalRole.MODEL,
        "config": ArchitecturalRole.CONFIG,
        "configuration": ArchitecturalRole.CONFIG,
        "settings": ArchitecturalRole.CONFIG,
        "util": ArchitecturalRole.UTILITY,
        "utils": ArchitecturalRole.UTILITY,
        "utility": ArchitecturalRole.UTILITY,
        "helper": ArchitecturalRole.UTILITY,
        "helpers": ArchitecturalRole.UTILITY,
        "common": ArchitecturalRole.UTILITY,
        "shared": ArchitecturalRole.UTILITY,
        "interface": ArchitecturalRole.INTERFACE,
        "interfaces": ArchitecturalRole.INTERFACE,
        "abstract": ArchitecturalRole.INTERFACE,
        "protocol": ArchitecturalRole.INTERFACE,
        "base": ArchitecturalRole.INTERFACE,
        "middleware": ArchitecturalRole.MIDDLEWARE,
        "plugin": ArchitecturalRole.MIDDLEWARE,
        "hook": ArchitecturalRole.MIDDLEWARE,
        "hooks": ArchitecturalRole.MIDDLEWARE,
        "adapter": ArchitecturalRole.ADAPTER,
        "adapters": ArchitecturalRole.ADAPTER,
        "client": ArchitecturalRole.ADAPTER,
        "gateway": ArchitecturalRole.ADAPTER,
        "connector": ArchitecturalRole.ADAPTER,
        "factory": ArchitecturalRole.FACTORY,
        "builder": ArchitecturalRole.FACTORY,
        "provider": ArchitecturalRole.FACTORY,
        "container": ArchitecturalRole.FACTORY,
        "view": ArchitecturalRole.VIEW,
        "views": ArchitecturalRole.VIEW,
        "template": ArchitecturalRole.VIEW,
        "component": ArchitecturalRole.VIEW,
        "cli": ArchitecturalRole.CLI,
        "command": ArchitecturalRole.CLI,
        "commands": ArchitecturalRole.CLI,
        "main": ArchitecturalRole.CLI,
    }

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, node: Node, info: ModuleInfo, graph: Optional[DependencyGraph] = None) -> RoleClassification:
        """
        Classify a module into an architectural role.

        Args:
            node: The graph node.
            info: Parsed module info.
            graph: Optional graph for structural context.

        Returns:
            RoleClassification with role, confidence, and evidence.
        """
        evidence: List[str] = []
        scores: Dict[ArchitecturalRole, float] = {}

        # Heuristic 1: Naming (weight 0.45)
        name_role, name_evidence = self._by_naming(node)
        if name_role != ArchitecturalRole.UNKNOWN:
            scores[name_role] = scores.get(name_role, 0) + 0.45
            evidence.extend(name_evidence)

        # Heuristic 2: Structure (weight 0.35)
        struct_role, struct_evidence = self._by_structure(node, info)
        if struct_role != ArchitecturalRole.UNKNOWN:
            scores[struct_role] = scores.get(struct_role, 0) + 0.35
            evidence.extend(struct_evidence)

        # Heuristic 3: Graph position (weight 0.20)
        if graph:
            pos_role, pos_evidence = self._by_graph_position(node, graph)
            if pos_role != ArchitecturalRole.UNKNOWN:
                scores[pos_role] = scores.get(pos_role, 0) + 0.20
                evidence.extend(pos_evidence)

        if not scores:
            return RoleClassification(
                role=ArchitecturalRole.UNKNOWN.value,
                confidence=0.3,
                evidence=["No classification heuristics matched"],
                module=node.name,
            )

        # Select highest-scoring role
        best_role = max(scores, key=lambda k: scores[k])
        confidence = min(scores[best_role], 0.95)

        return RoleClassification(
            role=best_role.value,
            confidence=confidence,
            evidence=evidence,
            module=node.name,
        )

    # ------------------------------------------------------------------
    # Heuristic 1: Naming conventions
    # ------------------------------------------------------------------

    @classmethod
    def _by_naming(cls, node: Node) -> tuple[ArchitecturalRole, List[str]]:
        """Classify by path segment keywords."""
        evidence: List[str] = []
        path_parts = node.name.lower().replace("-", "_").replace("/", ".").split(".")

        # Check each path segment against naming rules
        matched_roles: List[ArchitecturalRole] = []
        for part in path_parts:
            if part in cls.NAMING_RULES:
                role = cls.NAMING_RULES[part]
                matched_roles.append(role)
                evidence.append(f"Path segment '{part}' maps to role '{role.value}'")

        # Also check the file name (last segment before .py)
        if node.name in cls.NAMING_RULES:
            role = cls.NAMING_RULES[node.name]
            matched_roles.append(role)
            evidence.append(f"Module name '{node.name}' maps to role '{role.value}'")

        if matched_roles:
            # Use the most specific (last) match
            return matched_roles[-1], evidence

        return ArchitecturalRole.UNKNOWN, []

    # ------------------------------------------------------------------
    # Heuristic 2: Structural analysis
    # ------------------------------------------------------------------

    @classmethod
    def _by_structure(cls, node: Node, info: ModuleInfo) -> tuple[ArchitecturalRole, List[str]]:
        """Classify by code structure patterns."""
        evidence: List[str] = []

        # Entry point → CLI
        if info.has_entry_point:
            evidence.append("Has __main__ entry point")
            return ArchitecturalRole.CLI, evidence

        # Heavy on classes that are Exceptions/Errors → SERVICE or MODEL
        if info.classes:
            error_classes = [c for c in info.classes if "Error" in c or "Exception" in c]
            if len(error_classes) >= len(info.classes) * 0.5:
                evidence.append(f"Mostly error/exception classes ({len(error_classes)}/{len(info.classes)})")
                return ArchitecturalRole.MODEL, evidence

        # Abstract classes (bases listed in class_bases like ABC, Protocol)
        has_abstract = any(
            "ABC" in bases or "Protocol" in bases
            for bases in info.class_bases.values()
        )
        if has_abstract:
            evidence.append("Contains abstract base classes or protocols")
            return ArchitecturalRole.INTERFACE, evidence

        # Many functions, few classes → UTILITY
        if len(info.functions) > len(info.classes) * 2 and len(info.functions) >= 3:
            evidence.append(f"Function-heavy: {len(info.functions)} functions, {len(info.classes)} classes")
            return ArchitecturalRole.UTILITY, evidence

        # Many classes with CRUD-like method names → REPOSITORY
        crud_methods = {"save", "find", "get", "delete", "update", "create", "list", "query"}
        repository_classes = 0
        for cls_name, methods in info.class_methods.items():
            if len(set(methods) & crud_methods) >= 3:
                repository_classes += 1
        if repository_classes >= 1 and len(info.classes) <= 3:
            evidence.append(f"Has {repository_classes} class(es) with CRUD method patterns")
            return ArchitecturalRole.REPOSITORY, evidence

        # All classes with "Config" or "Settings" → CONFIG
        config_classes = [c for c in info.classes if "config" in c.lower() or "setting" in c.lower()]
        if config_classes:
            evidence.append(f"Contains configuration classes: {config_classes}")
            return ArchitecturalRole.CONFIG, evidence

        return ArchitecturalRole.UNKNOWN, []

    # ------------------------------------------------------------------
    # Heuristic 3: Graph position
    # ------------------------------------------------------------------

    @classmethod
    def _by_graph_position(cls, node: Node, graph: DependencyGraph) -> tuple[ArchitecturalRole, List[str]]:
        """Classify by position in the dependency graph."""
        evidence: List[str] = []

        deps = graph.immediate_dependencies(node.name)
        dependents = graph.immediate_dependents(node.name)
        dep_count = len(deps)
        dependent_count = len(dependents)

        # High fan-in (many dependents), low fan-out → SERVICE (shared dependency)
        if dependent_count >= 5 and dep_count <= dependent_count:
            evidence.append(
                f"High fan-in ({dependent_count} dependents) with moderate fan-out ({dep_count} deps) — "
                f"likely a shared service"
            )
            return ArchitecturalRole.SERVICE, evidence

        # Low fan-in, low fan-out → UTILITY or MODEL
        if dependent_count == 0 and dep_count <= 2:
            evidence.append(
                f"Leaf module: no dependents, only {dep_count} dependencies"
            )
            return ArchitecturalRole.UTILITY, evidence

        # High fan-out (many dependencies), low fan-in → CONTROLLER or FACADE
        if dep_count >= 5 and dependent_count <= 2:
            evidence.append(
                f"Orchestrator pattern: {dep_count} dependencies, {dependent_count} dependents"
            )
            return ArchitecturalRole.CONTROLLER, evidence

        return ArchitecturalRole.UNKNOWN, []
