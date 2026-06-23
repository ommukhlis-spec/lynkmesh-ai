"""
PatternDetector — detects design patterns from module structure and AST data.

Detects: Singleton, Factory, Repository, Observer, Strategy,
         Facade, Adapter, Command, Decorator, Template Method.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from lynkmesh_ai.core.graph import DependencyGraph, Node
from lynkmesh_ai.core.parser import ModuleInfo
from lynkmesh_ai.semantic.graph import PatternMatch

logger = logging.getLogger(__name__)


class PatternDetector:
    """
    Detects design patterns using heuristic analysis of class names,
    method names, inheritance hierarchies, and graph structure.
    """

    # Indicator sets for pattern detection
    SINGLETON_INDICATORS = {"_instance", "instance", "get_instance", "__new__"}
    FACTORY_NAMES = {"factory", "builder", "creator", "provider"}
    REPOSITORY_NAMES = {"repository", "store", "dao", "datastore", "persistence"}
    REPOSITORY_METHODS = {"save", "find", "get", "delete", "update", "create", "list", "query", "count", "exists"}
    OBSERVER_METHODS = {"subscribe", "unsubscribe", "notify", "emit", "listen", "add_listener", "remove_listener", "fire"}
    STRATEGY_NAMES = {"strategy", "policy", "algorithm", "handler"}
    ADAPTER_NAMES = {"adapter", "wrapper", "adaptor", "bridge"}
    COMMAND_METHODS = {"execute", "undo", "redo"}

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_all(
        self,
        node: Node,
        info: ModuleInfo,
        graph: DependencyGraph,
    ) -> List[PatternMatch]:
        """Run all pattern detectors for a module node."""
        matches: List[PatternMatch] = []
        matches.extend(self._detect_singleton(node, info))
        matches.extend(self._detect_factory(node, info))
        matches.extend(self._detect_repository(node, info))
        matches.extend(self._detect_observer(node, info))
        matches.extend(self._detect_strategy(node, info))
        matches.extend(self._detect_facade(node, info, graph))
        matches.extend(self._detect_adapter(node, info))
        matches.extend(self._detect_command(node, info))
        matches.extend(self._detect_decorator(node, info))
        matches.extend(self._detect_template_method(node, info))
        return matches

    # ------------------------------------------------------------------
    # Individual detectors
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_singleton(node: Node, info: ModuleInfo) -> List[PatternMatch]:
        """Detect Singleton: class with instance attribute or get_instance method."""
        matches = []
        for cls_name, methods in info.class_methods.items():
            evidence = []
            # Check for _instance / instance attribute
            method_set = set(methods)
            if method_set & PatternDetector.SINGLETON_INDICATORS:
                evidence.append(f"Class '{cls_name}' has singleton indicator method: "
                                f"{method_set & PatternDetector.SINGLETON_INDICATORS}")
            # Check __new__ override
            if "__new__" in method_set:
                evidence.append(f"Class '{cls_name}' overrides __new__")
            if evidence:
                matches.append(PatternMatch(
                    pattern="singleton",
                    module=node.name,
                    class_name=cls_name,
                    confidence=min(0.6 + len(evidence) * 0.15, 0.95),
                    evidence=evidence,
                    location=node.file_path,
                ))
        return matches

    @staticmethod
    def _detect_factory(node: Node, info: ModuleInfo) -> List[PatternMatch]:
        """Detect Factory: class/method name contains factory keywords."""
        matches = []
        for cls_name in info.classes:
            cls_lower = cls_name.lower()
            for kw in PatternDetector.FACTORY_NAMES:
                if kw in cls_lower:
                    evidence = [f"Class name '{cls_name}' contains factory keyword '{kw}'"]
                    # Check if it has a creation method
                    methods = info.class_methods.get(cls_name, [])
                    creator_methods = [
                        m for m in methods
                        if any(c in m.lower() for c in ("create", "build", "make", "new"))
                    ]
                    if creator_methods:
                        evidence.append(f"Has creator methods: {creator_methods}")
                    matches.append(PatternMatch(
                        pattern="factory",
                        module=node.name,
                        class_name=cls_name,
                        confidence=0.65 if creator_methods else 0.5,
                        evidence=evidence,
                        location=node.file_path,
                    ))
                    break  # One factory pattern match per class
        return matches

    @staticmethod
    def _detect_repository(node: Node, info: ModuleInfo) -> List[PatternMatch]:
        """Detect Repository: CRUD method set or repository naming."""
        matches = []
        for cls_name in info.classes:
            cls_lower = cls_name.lower()
            methods = set(info.class_methods.get(cls_name, []))
            evidence = []

            # Naming heuristic
            for kw in PatternDetector.REPOSITORY_NAMES:
                if kw in cls_lower:
                    evidence.append(f"Class name contains repository keyword '{kw}'")
                    break

            # Method set heuristic: at least 4 CRUD methods
            crud_hits = methods & PatternDetector.REPOSITORY_METHODS
            if len(crud_hits) >= 4:
                evidence.append(f"Has {len(crud_hits)} CRUD methods: {sorted(crud_hits)}")

            if evidence:
                conf = min(0.5 + len(evidence) * 0.2, 0.95)
                matches.append(PatternMatch(
                    pattern="repository",
                    module=node.name,
                    class_name=cls_name,
                    confidence=conf,
                    evidence=evidence,
                    location=node.file_path,
                ))
        return matches

    @staticmethod
    def _detect_observer(node: Node, info: ModuleInfo) -> List[PatternMatch]:
        """Detect Observer: subscribe/notify method pairs."""
        matches = []
        for cls_name, methods in info.class_methods.items():
            method_set = set(methods)
            observer_hits = method_set & PatternDetector.OBSERVER_METHODS
            if len(observer_hits) >= 2:
                has_sub = any(m in method_set for m in ("subscribe", "add_listener", "listen"))
                has_pub = any(m in method_set for m in ("notify", "emit", "fire"))
                evidence = [f"Observer methods: {sorted(observer_hits)}"]
                if has_sub and has_pub:
                    evidence.append("Has subscription + notification pair")
                    conf = 0.85
                else:
                    conf = 0.55
                matches.append(PatternMatch(
                    pattern="observer",
                    module=node.name,
                    class_name=cls_name,
                    confidence=conf,
                    evidence=evidence,
                    location=node.file_path,
                ))
        return matches

    @staticmethod
    def _detect_strategy(node: Node, info: ModuleInfo) -> List[PatternMatch]:
        """Detect Strategy: class name or constructor accepting callable."""
        matches = []
        for cls_name in info.classes:
            cls_lower = cls_name.lower()
            evidence = []
            for kw in PatternDetector.STRATEGY_NAMES:
                if kw in cls_lower:
                    evidence.append(f"Class name contains strategy keyword '{kw}'")
                    break
            if evidence:
                matches.append(PatternMatch(
                    pattern="strategy",
                    module=node.name,
                    class_name=cls_name,
                    confidence=0.6,
                    evidence=evidence,
                    location=node.file_path,
                ))
        return matches

    @staticmethod
    def _detect_facade(
        node: Node, info: ModuleInfo, graph: DependencyGraph,
    ) -> List[PatternMatch]:
        """Detect Facade: module with many imports but few exported classes."""
        matches = []
        import_count = len(node.imports)
        class_count = len(info.classes)
        if import_count >= 5 and class_count <= 3 and class_count > 0:
            evidence = [
                f"High import count ({import_count}) with only {class_count} class(es)",
                f"Likely re-exports or simplifies external interfaces",
            ]
            matches.append(PatternMatch(
                pattern="facade",
                module=node.name,
                confidence=min(0.5 + import_count * 0.03, 0.85),
                evidence=evidence,
                location=node.file_path,
            ))
        return matches

    @staticmethod
    def _detect_adapter(node: Node, info: ModuleInfo) -> List[PatternMatch]:
        """Detect Adapter: class wrapping/delegating to another; naming convention."""
        matches = []
        for cls_name in info.classes:
            cls_lower = cls_name.lower()
            evidence = []
            for kw in PatternDetector.ADAPTER_NAMES:
                if kw in cls_lower:
                    evidence.append(f"Class name contains adapter keyword '{kw}'")
                    break
            # Check if it wraps another class (has one constructor param named 'wrapped' etc.)
            methods = info.class_methods.get(cls_name, [])
            if evidence and len(methods) >= 3:
                evidence.append(f"Has {len(methods)} methods — likely delegation pattern")
            if evidence:
                matches.append(PatternMatch(
                    pattern="adapter",
                    module=node.name,
                    class_name=cls_name,
                    confidence=0.6,
                    evidence=evidence,
                    location=node.file_path,
                ))
        return matches

    @staticmethod
    def _detect_command(node: Node, info: ModuleInfo) -> List[PatternMatch]:
        """Detect Command: class with execute/undo methods."""
        matches = []
        for cls_name, methods in info.class_methods.items():
            method_set = set(methods)
            cmd_hits = method_set & PatternDetector.COMMAND_METHODS
            if "execute" in method_set:
                evidence = [f"Has 'execute' method"]
                if "undo" in method_set:
                    evidence.append("Has 'undo' method — full command pattern")
                    conf = 0.85
                else:
                    conf = 0.6
                matches.append(PatternMatch(
                    pattern="command",
                    module=node.name,
                    class_name=cls_name,
                    confidence=conf,
                    evidence=evidence,
                    location=node.file_path,
                ))
        return matches

    @staticmethod
    def _detect_decorator(node: Node, info: ModuleInfo) -> List[PatternMatch]:
        """Detect Decorator: class wrapping same interface as base class."""
        matches = []
        for cls_name, bases in info.class_bases.items():
            # If a class inherits from a base and has methods matching that base,
            # it might be a decorator wrapping the base
            methods = set(info.class_methods.get(cls_name, []))
            if bases and len(methods) >= 2:
                # Check if the base is also defined in this module (decorator wraps same interface)
                for base in bases:
                    base_methods = set(info.class_methods.get(base, []))
                    if base_methods and methods & base_methods:
                        matches.append(PatternMatch(
                            pattern="decorator",
                            module=node.name,
                            class_name=cls_name,
                            confidence=0.55,
                            evidence=[
                                f"Class '{cls_name}' inherits '{base}' and shares method signatures",
                                f"Shared methods: {sorted(methods & base_methods)}",
                            ],
                            location=node.file_path,
                        ))
                        break
        return matches

    @staticmethod
    def _detect_template_method(node: Node, info: ModuleInfo) -> List[PatternMatch]:
        """Detect Template Method: abstract base with concrete subclasses implementing _ methods."""
        matches = []
        # Find classes with "private" _method patterns that override base
        for cls_name, methods in info.class_methods.items():
            private_methods = [m for m in methods if m.startswith("_") and not m.startswith("__")]
            public_methods = [m for m in methods if not m.startswith("_")]
            if private_methods and public_methods and info.class_bases.get(cls_name):
                matches.append(PatternMatch(
                    pattern="template_method",
                    module=node.name,
                    class_name=cls_name,
                    confidence=0.5,
                    evidence=[
                        f"Class '{cls_name}' has {len(private_methods)} hook methods "
                        f"and inherits from {info.class_bases[cls_name]}",
                    ],
                    location=node.file_path,
                ))
        return matches
