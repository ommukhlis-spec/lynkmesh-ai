"""
ArchitectureAnalyzer — reasons about WHY the codebase is designed this way.

Consumes SemanticGraph + KnowledgeBase to produce:
- Layering assessment (does the code follow layered architecture?)
- Coupling hotspots (which modules are over-coupled?)
- Cohesion analysis (are packages cohesive?)
- Missing abstractions (where should interfaces exist?)
- Architecture style detection (layered, hexagonal, microservices, etc.)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from lynkmesh_ai.core.graph import DependencyGraph
from lynkmesh_ai.semantic.graph import SemanticGraph
from lynkmesh_ai.semantic.roles import ArchitecturalRole
from lynkmesh_ai.knowledge.base import KnowledgeBase

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Output types
# ══════════════════════════════════════════════════════════════════════

class ArchitectureStyle(str, Enum):
    LAYERED = "layered"
    HEXAGONAL = "hexagonal"
    MODULAR_MONOLITH = "modular_monolith"
    SERVICE_ORIENTED = "service_oriented"
    MICROSERVICES = "microservices"
    EVENT_DRIVEN = "event_driven"
    CQRS = "cqrs"
    PLUGIN = "plugin"
    UNCLASSIFIED = "unclassified"


@dataclass
class LayeringViolation:
    """A violation of expected layering rules."""
    source: str          # Module doing the importing
    target: str          # Module being imported (shouldn't be)
    expected_direction: str  # e.g., "controller → service", not "model → controller"
    severity: str        # "critical", "major", "minor"
    explanation: str


@dataclass
class CouplingHotspot:
    """A module with excessive coupling."""
    module: str
    fan_in: int          # How many modules depend on this one
    fan_out: int         # How many modules this one depends on
    instability: float   # fan_out / (fan_in + fan_out)
    is_stable: bool      # True if low instability (many dependents)
    explanation: str


@dataclass
class CohesionAssessment:
    """Assessment of a package's internal cohesion."""
    package: str
    module_count: int
    internal_deps: int   # Edges between modules in the same package
    external_deps: int   # Edges leaving the package
    cohesion_ratio: float  # internal / (internal + external)
    is_cohesive: bool
    explanation: str


@dataclass
class MissingAbstraction:
    """A place where an interface/protocol might be needed."""
    module: str
    consumers: List[str]  # Modules that would benefit from an abstraction
    reason: str           # Why an abstraction is needed
    suggested_pattern: str  # e.g., "Interface", "Factory", "Strategy"


@dataclass
class ArchitectureReport:
    """Complete architectural assessment of a codebase."""

    style: ArchitectureStyle = ArchitectureStyle.UNCLASSIFIED
    style_confidence: float = 0.0
    style_evidence: List[str] = field(default_factory=list)

    layering_violations: List[LayeringViolation] = field(default_factory=list)
    coupling_hotspots: List[CouplingHotspot] = field(default_factory=list)
    cohesion_assessments: List[CohesionAssessment] = field(default_factory=list)
    missing_abstractions: List[MissingAbstraction] = field(default_factory=list)

    # Narrative
    architecture_narrative: str = ""
    principle_violations: List[str] = field(default_factory=list)  # Which SOLID/design principles are violated
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "style": self.style.value,
            "style_confidence": self.style_confidence,
            "style_evidence": self.style_evidence,
            "layering_violations": [vars(v) for v in self.layering_violations],
            "coupling_hotspots": [vars(h) for h in self.coupling_hotspots],
            "cohesion_assessments": [vars(c) for c in self.cohesion_assessments],
            "missing_abstractions": [vars(m) for m in self.missing_abstractions],
            "architecture_narrative": self.architecture_narrative,
            "principle_violations": self.principle_violations,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "metadata": self.metadata,
        }


# ══════════════════════════════════════════════════════════════════════
# ArchitectureAnalyzer
# ══════════════════════════════════════════════════════════════════════

class ArchitectureAnalyzer:
    """
    Reasons about the architectural structure of a codebase.

    Uses the dependency graph, semantic roles, and domain concepts to
    infer architectural style, detect violations, and assess quality.
    """

    # Expected layering order (lower number = upper layer, higher = lower layer)
    LAYER_ORDER: Dict[str, int] = {
        "cli": 0,
        "view": 0,
        "controller": 1,
        "middleware": 1,
        "service": 2,
        "factory": 2,
        "repository": 3,
        "adapter": 3,
        "model": 4,
        "interface": 4,
        "config": 4,
        "utility": 5,  # Can be imported by any layer
    }

    def __init__(
        self,
        graph: DependencyGraph,
        semantic_graph: Optional[SemanticGraph] = None,
        knowledge_base: Optional[KnowledgeBase] = None,
    ) -> None:
        self.graph = graph
        self.semantic_graph = semantic_graph
        self.knowledge_base = knowledge_base

    # ------------------------------------------------------------------
    # Full analysis
    # ------------------------------------------------------------------

    def analyze(self) -> ArchitectureReport:
        """Run full architectural analysis and return a report."""
        report = ArchitectureReport()

        # 1. Classify architectural style
        report.style, report.style_confidence, report.style_evidence = self._classify_style()

        # 2. Detect layering violations
        report.layering_violations = self._detect_layering_violations()

        # 3. Find coupling hotspots
        report.coupling_hotspots = self._find_coupling_hotspots()

        # 4. Assess package cohesion
        report.cohesion_assessments = self._assess_cohesion()

        # 5. Identify missing abstractions
        report.missing_abstractions = self._identify_missing_abstractions()

        # 6. Synthesize narrative
        report.architecture_narrative = self._synthesize_narrative(report)
        report.strengths, report.weaknesses = self._assess_quality(report)
        report.principle_violations = self._detect_principle_violations(report)

        report.metadata = {
            "node_count": self.graph.node_count,
            "edge_count": self.graph.edge_count,
            "analyzer_version": "1.0",
        }

        return report

    # ------------------------------------------------------------------
    # Style classification
    # ------------------------------------------------------------------

    def _classify_style(self) -> Tuple[ArchitectureStyle, float, List[str]]:
        """
        Infer the architectural style from code structure.
        """
        evidence: List[str] = []
        scores: Dict[ArchitectureStyle, float] = {}

        roles = self._get_role_distribution()
        role_count = sum(roles.values())

        # Detect Layered architecture
        if roles.get("controller", 0) > 0 and roles.get("service", 0) > 0 and roles.get("repository", 0) > 0:
            scores[ArchitectureStyle.LAYERED] = 0.7
            evidence.append("Has controller, service, and repository roles — classic layered architecture")
        elif roles.get("service", 0) > 0 and roles.get("model", 0) > 0:
            scores[ArchitectureStyle.LAYERED] = 0.45
            evidence.append("Has service and model separation — suggestive of layering")

        # Detect Modular Monolith
        packages = self._get_packages()
        if len(packages) >= 4 and role_count <= 6:
            scores[ArchitectureStyle.MODULAR_MONOLITH] = 0.6
            evidence.append(f"Has {len(packages)} packages with {role_count} distinct roles — modular monolith pattern")

        # Detect Hexagonal (ports & adapters)
        adapter_count = roles.get("adapter", 0)
        interface_count = roles.get("interface", 0)
        if adapter_count >= 1 and interface_count >= 1:
            scores[ArchitectureStyle.HEXAGONAL] = 0.55
            evidence.append("Has adapter and interface roles — hexagonal/ports-and-adapters pattern")
        elif adapter_count >= 2:
            scores[ArchitectureStyle.HEXAGONAL] = 0.4
            evidence.append("Multiple adapter modules detected — possible hexagonal architecture")

        # Detect Event-Driven
        observer_patterns = 0
        if self.semantic_graph:
            all_patterns = self.semantic_graph.get_all_patterns()
            for pats in all_patterns.values():
                observer_patterns += sum(1 for p in pats if p.pattern == "observer")
        if observer_patterns >= 2:
            scores[ArchitectureStyle.EVENT_DRIVEN] = 0.6
            evidence.append(f"Found {observer_patterns} observer pattern implementations — event-driven design")

        # Edge direction analysis
        if self.graph.edge_count > 0:
            deps_upward, deps_downward, deps_cross = self._analyze_edge_directions()
            total = deps_upward + deps_downward + deps_cross
            if total > 0:
                if deps_downward / total > 0.6:
                    scores[ArchitectureStyle.LAYERED] = scores.get(ArchitectureStyle.LAYERED, 0) + 0.15
                    evidence.append("Dependencies flow predominantly downward (higher → lower layers)")

        if not scores:
            return ArchitectureStyle.UNCLASSIFIED, 0.3, ["Could not confidently classify architectural style"]

        best = max(scores, key=lambda k: scores[k])
        confidence = min(scores[best], 0.9)
        return best, confidence, evidence

    # ------------------------------------------------------------------
    # Layering violation detection
    # ------------------------------------------------------------------

    def _detect_layering_violations(self) -> List[LayeringViolation]:
        """
        Detect imports that violate expected layering.
        A violation occurs when an upper layer imports a lower layer
        (e.g., a model importing a service).
        """
        violations: List[LayeringViolation] = []

        if not self.semantic_graph:
            return violations

        for edge in self.graph.iter_edges():
            source_role = self._get_module_role(edge.source)
            target_role = self._get_module_role(edge.target)

            if source_role == "unknown" or target_role == "unknown":
                continue  # Can't assess without roles

            source_layer = self.LAYER_ORDER.get(source_role, 99)
            target_layer = self.LAYER_ORDER.get(target_role, 99)

            # utility can be imported by anyone
            if source_role == "utility" or target_role == "utility":
                continue

            # Upward reference: lower layer importing upper layer → violation
            if source_layer > target_layer:
                severity = "critical" if (source_layer - target_layer) >= 3 else "major"
                violations.append(LayeringViolation(
                    source=edge.source,
                    target=edge.target,
                    expected_direction=f"{source_role} ({source_layer}) should not depend on {target_role} ({target_layer})",
                    severity=severity if source_layer - target_layer >= 2 else "minor",
                    explanation=(
                        f"Module '{edge.source}' (role: {source_role}) imports '{edge.target}' "
                        f"(role: {target_role}). This reverses the expected dependency direction "
                        f"where upper layers should depend on lower layers, not vice versa."
                    ),
                ))

        return violations

    # ------------------------------------------------------------------
    # Coupling hotspot detection
    # ------------------------------------------------------------------

    def _find_coupling_hotspots(self, top_n: int = 10) -> List[CouplingHotspot]:
        """Find modules with excessive coupling."""
        hotspots: List[CouplingHotspot] = []
        modules_seen = 0

        for node in self.graph.iter_nodes():
            if modules_seen >= 50:
                break
            modules_seen += 1

            fan_in = len(self.graph.immediate_dependents(node.name))
            fan_out = len(self.graph.immediate_dependencies(node.name))
            total = fan_in + fan_out

            if total == 0:
                continue

            instability = fan_out / total if total > 0 else 0.0
            is_stable = instability < 0.3

            # Hotspot threshold: high total coupling
            if total >= 5:
                if is_stable:
                    explanation = (
                        f"'{node.name}' is a STABLE hotspot: {fan_in} modules depend on it "
                        f"(only {fan_out} outgoing). Changes here affect {fan_in} consumers. "
                        f"Consider this a core abstraction — treat with care."
                    )
                elif instability > 0.7:
                    explanation = (
                        f"'{node.name}' is an UNSTABLE hotspot: it depends on {fan_out} modules "
                        f"(only {fan_in} dependents). It is fragile — changes to any dependency "
                        f"may break this module. Consider reducing coupling."
                    )
                else:
                    explanation = (
                        f"'{node.name}' is a BALANCED hotspot with {total} total connections "
                        f"({fan_in} in, {fan_out} out). It is neither overly stable nor fragile."
                    )

                hotspots.append(CouplingHotspot(
                    module=node.name,
                    fan_in=fan_in,
                    fan_out=fan_out,
                    instability=round(instability, 3),
                    is_stable=is_stable,
                    explanation=explanation,
                ))

        hotspots.sort(key=lambda h: h.fan_in + h.fan_out, reverse=True)
        return hotspots[:top_n]

    # ------------------------------------------------------------------
    # Package cohesion
    # ------------------------------------------------------------------

    def _assess_cohesion(self) -> List[CohesionAssessment]:
        """Assess cohesion of each package."""
        packages = self._get_packages()
        assessments: List[CohesionAssessment] = []

        for pkg in sorted(packages):
            modules_in_pkg = set()
            for node in self.graph.iter_nodes():
                if node.package == pkg:
                    modules_in_pkg.add(node.name)

            if len(modules_in_pkg) < 2:
                continue  # Single-module package has trivially perfect cohesion

            internal_deps = 0
            external_deps = 0

            for edge in self.graph.iter_edges():
                src_in = edge.source in modules_in_pkg
                tgt_in = edge.target in modules_in_pkg
                if src_in and tgt_in:
                    internal_deps += 1
                elif src_in and not tgt_in:
                    external_deps += 1

            total = internal_deps + external_deps
            ratio = internal_deps / total if total > 0 else 0.0

            if ratio >= 0.6:
                explanation = (
                    f"Package '{pkg}' is HIGHLY COHESIVE ({ratio:.0%} internal). "
                    f"Modules within this package primarily depend on each other."
                )
            elif ratio >= 0.3:
                explanation = (
                    f"Package '{pkg}' is MODERATELY COHESIVE ({ratio:.0%} internal). "
                    f"Some cross-package dependencies exist."
                )
            else:
                explanation = (
                    f"Package '{pkg}' has LOW COHESION ({ratio:.0%} internal). "
                    f"Modules depend more on external packages than on each other — "
                    f"consider whether this package's boundaries are correct."
                )

            assessments.append(CohesionAssessment(
                package=pkg,
                module_count=len(modules_in_pkg),
                internal_deps=internal_deps,
                external_deps=external_deps,
                cohesion_ratio=round(ratio, 3),
                is_cohesive=ratio >= 0.5,
                explanation=explanation,
            ))

        return assessments

    # ------------------------------------------------------------------
    # Missing abstraction detection
    # ------------------------------------------------------------------

    def _identify_missing_abstractions(self) -> List[MissingAbstraction]:
        """Identify places where interfaces or abstractions are needed."""
        missing: List[MissingAbstraction] = []

        for node in self.graph.iter_nodes():
            dependents = self.graph.immediate_dependents(node.name)
            if len(dependents) >= 3 and len(node.classes) <= 2 and len(node.functions) >= 3:
                # This module is directly depended on by many consumers
                # without an interface layer — consider adding one
                missing.append(MissingAbstraction(
                    module=node.name,
                    consumers=dependents,
                    reason=(
                        f"'{node.name}' has {len(dependents)} direct dependents without an "
                        f"abstract interface. This creates tight coupling — any change to "
                        f"'{node.name}' forces all {len(dependents)} consumers to adapt."
                    ),
                    suggested_pattern="Interface or Abstract Base Class",
                ))

        # Also check for repetitive patterns
        implementation_modules = defaultdict(list)
        for node in self.graph.iter_nodes():
            # Group modules that look like implementations of the same concept
            name = node.name.split(".")[-1]
            if name in ("adapter", "client", "repository", "service"):
                implementation_modules[name].append(node.name)

        for suffix, modules in implementation_modules.items():
            if len(modules) >= 3:
                # These share a naming convention but likely no shared interface
                missing.append(MissingAbstraction(
                    module=modules[0],
                    consumers=modules,
                    reason=(
                        f"Found {len(modules)} modules ending in '{suffix}' without a shared "
                        f"interface. Consider defining a base class or protocol for consistency."
                    ),
                    suggested_pattern="Protocol or Abstract Base Class",
                ))

        return missing

    # ------------------------------------------------------------------
    # Quality assessment
    # ------------------------------------------------------------------

    def _assess_quality(self, report: ArchitectureReport) -> Tuple[List[str], List[str]]:
        """Identify architectural strengths and weaknesses."""
        strengths: List[str] = []
        weaknesses: List[str] = []

        # Strengths
        cycles = self.graph.find_cycles()
        if not cycles:
            strengths.append("No circular dependencies — the dependency graph is a DAG")
        else:
            weaknesses.append(f"Found {len(cycles)} circular dependency cycle(s)")

        high_cohesion = [c for c in report.cohesion_assessments if c.cohesion_ratio >= 0.6]
        low_cohesion = [c for c in report.cohesion_assessments if c.cohesion_ratio < 0.3]
        if high_cohesion:
            strengths.append(f"{len(high_cohesion)} package(s) are highly cohesive")
        if low_cohesion:
            weaknesses.append(f"{len(low_cohesion)} package(s) have low cohesion — review package boundaries")

        if not report.layering_violations:
            strengths.append("No layering violations detected — dependency direction follows expected patterns")
        else:
            critical_violations = [v for v in report.layering_violations if v.severity == "critical"]
            if critical_violations:
                weaknesses.append(f"{len(critical_violations)} critical layering violation(s) — lower layers importing upper layers")

        if not report.coupling_hotspots or all(h.instability > 0.3 and h.instability < 0.7 for h in report.coupling_hotspots):
            strengths.append("Coupling is balanced — no extreme hotspots detected")
        else:
            fragile = [h for h in report.coupling_hotspots if h.instability > 0.7]
            if fragile:
                weaknesses.append(f"{len(fragile)} module(s) are overly fragile (high instability)")

        if not report.missing_abstractions:
            strengths.append("Abstraction level appears adequate")
        else:
            weaknesses.append(f"{len(report.missing_abstractions)} potential missing abstraction(s) identified")

        return strengths, weaknesses

    def _detect_principle_violations(self, report: ArchitectureReport) -> List[str]:
        """Detect violations of SOLID and other design principles."""
        violations: List[str] = []

        # Single Responsibility: modules with too many roles or too many dependencies
        for node in self.graph.iter_nodes():
            if len(node.imports) > 15:
                violations.append(
                    f"SRP violation: '{node.name}' imports {len(node.imports)} modules — "
                    f"likely has too many responsibilities"
                )
                break  # One example is enough

        # Dependency Inversion: concrete-to-concrete dependencies without abstraction
        if report.missing_abstractions:
            violations.append(
                f"DIP concern: {len(report.missing_abstractions)} potential missing abstractions — "
                f"consider depending on interfaces, not concretions"
            )

        # Interface Segregation: if a module is imported by many but only for one function
        for hotspot in report.coupling_hotspots:
            if hotspot.fan_in >= 8:
                violations.append(
                    f"ISP concern: '{hotspot.module}' has {hotspot.fan_in} dependents — "
                    f"the interface may be too broad for all consumers"
                )
                break

        # Open/Closed: modules modified frequently (from git history if available)
        # (This requires change_tracker data — skip for now)

        return violations

    # ------------------------------------------------------------------
    # Narrative synthesis
    # ------------------------------------------------------------------

    def _synthesize_narrative(self, report: ArchitectureReport) -> str:
        """
        Produce a human-readable narrative explaining the architecture.
        This is the "WHY" — the reasoning engine's primary output.
        """
        parts = []

        # Opening
        parts.append(
            f"This codebase appears to follow a **{report.style.value.replace('_', ' ').title()}** "
            f"architectural style (confidence: {report.style_confidence:.0%})."
        )

        # Style evidence
        if report.style_evidence:
            parts.append("Evidence for this classification:")
            for ev in report.style_evidence:
                parts.append(f"  - {ev}")

        # Structure
        packages = self._get_packages()
        parts.append(
            f"\nThe system comprises **{len(packages)} package(s)** with "
            f"**{self.graph.node_count} modules** and **{self.graph.edge_count} dependencies**."
        )

        # Role distribution
        roles = self._get_role_distribution()
        if roles:
            role_str = ", ".join(f"{r}({c})" for r, c in sorted(roles.items(), key=lambda x: x[1], reverse=True))
            parts.append(f"Role distribution: {role_str}.")

        # Coupling narrative
        if report.coupling_hotspots:
            top = report.coupling_hotspots[0]
            parts.append(
                f"\nThe most coupled module is **'{top.module}'** "
                f"with {top.fan_in} dependents and {top.fan_out} dependencies. "
                f"{'It is a stable core abstraction.' if top.is_stable else 'It is fragile — changes to its dependencies may break it.'}"
            )

        # Layering narrative
        if report.layering_violations:
            critical = [v for v in report.layering_violations if v.severity == "critical"]
            major = [v for v in report.layering_violations if v.severity == "major"]
            if critical:
                parts.append(f"\n**⚠️  {len(critical)} critical layering violation(s)** detected:")
                for v in critical[:3]:
                    parts.append(f"  - {v.source} → {v.target}: {v.explanation[:120]}")
            if major:
                parts.append(f"**{len(major)} major violation(s)** — review recommended.")

        # Cohesion narrative
        cohesive = [c for c in report.cohesion_assessments if c.is_cohesive]
        if cohesive:
            parts.append(f"\n**{len(cohesive)} package(s)** show strong internal cohesion.")
        low_cohesion = [c for c in report.cohesion_assessments if not c.is_cohesive]
        if low_cohesion:
            parts.append(f"**{len(low_cohesion)} package(s)** have weak cohesion — consider restructuring.")

        # Overall
        total_issues = (
            len(report.layering_violations) +
            len(report.missing_abstractions) +
            len(report.principle_violations)
        )
        if total_issues == 0:
            parts.append("\n**Overall: The architecture is clean with no major concerns identified.**")
        elif total_issues <= 3:
            parts.append(f"\n**Overall: Minor architectural concerns ({total_issues} issue(s)) — manageable.**")
        else:
            parts.append(f"\n**Overall: {total_issues} architectural concern(s) identified — review recommended.**")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_role_distribution(self) -> Dict[str, int]:
        """Get count of each architectural role."""
        roles: Dict[str, int] = defaultdict(int)
        if self.semantic_graph:
            for role in self.semantic_graph.get_all_roles().values():
                roles[role.role] += 1
        return dict(roles)

    def _get_module_role(self, module_name: str) -> str:
        """Get the role of a module as a string."""
        if self.semantic_graph:
            role = self.semantic_graph.get_role(module_name)
            if role:
                return role.role
        return "unknown"

    def _get_packages(self) -> Set[str]:
        """Get all package names."""
        packages: Set[str] = set()
        for node in self.graph.iter_nodes():
            if node.package:
                packages.add(node.package)
        return packages

    def _analyze_edge_directions(self) -> Tuple[int, int, int]:
        """
        Count edges by direction relative to layering.
        Returns (upward, downward, cross_layer).
        """
        upward, downward, cross = 0, 0, 0
        for edge in self.graph.iter_edges():
            src_role = self._get_module_role(edge.source)
            tgt_role = self._get_module_role(edge.target)
            src_layer = self.LAYER_ORDER.get(src_role, 99)
            tgt_layer = self.LAYER_ORDER.get(tgt_role, 99)
            if src_layer < tgt_layer:
                downward += 1  # Upper → Lower (correct)
            elif src_layer > tgt_layer:
                upward += 1    # Lower → Upper (potential violation)
            else:
                cross += 1     # Same layer
        return upward, downward, cross
