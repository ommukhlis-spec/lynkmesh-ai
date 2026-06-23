"""
ImpactAnalyzer — reasons about the impact of code changes.

Goes beyond simple dependency traversal to explain:
- WHY a change is risky (architectural significance)
- WHAT could break (concrete impact paths)
- HOW risk propagates through the system
- WHICH architectural principles are affected
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from lynkmesh_ai.core.graph import DependencyGraph
from lynkmesh_ai.core.change_tracker import ChangeRecord
from lynkmesh_ai.semantic.graph import SemanticGraph
from lynkmesh_ai.semantic.roles import ArchitecturalRole
from lynkmesh_ai.knowledge.base import KnowledgeBase

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Output types
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ImpactPath:
    """A single path of impact propagation."""
    path: List[str]           # [changed_module, ..., affected_module]
    propagation_type: str     # "direct_dependency", "semantic_coupling", "co_change", "architectural"
    risk_level: str           # "critical", "high", "medium", "low"
    explanation: str


@dataclass
class ChangeImpact:
    """Impact assessment for a single changed module."""
    module: str
    change_type: str  # "modified", "added", "deleted"
    risk_level: str
    blast_radius: int  # Number of directly + transitively affected modules
    affected_roles: List[str]  # Roles of affected modules
    impact_paths: List[ImpactPath] = field(default_factory=list)
    principle_impacts: List[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class ImpactReport:
    """Complete impact assessment of a set of changes."""

    changes: List[ChangeImpact] = field(default_factory=list)
    system_risk_level: str = "low"
    critical_paths: List[ImpactPath] = field(default_factory=list)
    recommended_mitigations: List[str] = field(default_factory=list)
    explanation_narrative: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "changes": [vars(c) for c in self.changes],
            "system_risk_level": self.system_risk_level,
            "critical_paths": [vars(p) for p in self.critical_paths],
            "recommended_mitigations": self.recommended_mitigations,
            "explanation_narrative": self.explanation_narrative,
        }


# ══════════════════════════════════════════════════════════════════════
# ImpactAnalyzer
# ══════════════════════════════════════════════════════════════════════

class ImpactAnalyzer:
    """
    Analyzes the impact of code changes with architectural reasoning.

    Unlike the basic ChangeTracker which only maps files to nodes,
    this explains WHY changes matter and HOW impact cascades.
    """

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

    def analyze_changes(
        self,
        changes: List[ChangeRecord],
    ) -> ImpactReport:
        """
        Analyze the impact of a set of changes.

        Args:
            changes: List of ChangeRecord from ChangeTracker.

        Returns:
            ImpactReport with per-change impact and system-level assessment.
        """
        report = ImpactReport()

        for change in changes:
            module_name = change.module_name
            if not module_name:
                module_name = self._file_to_module(change.file_path)

            if not self.graph.has_node(module_name):
                continue

            impact = self.analyze_single_change(module_name, change)
            report.changes.append(impact)

            # Collect critical paths
            for path in impact.impact_paths:
                if path.risk_level in ("critical", "high"):
                    report.critical_paths.append(path)

        # System-level assessment
        report.system_risk_level = self._assess_system_risk(report)
        report.recommended_mitigations = self._recommend_mitigations(report)
        report.explanation_narrative = self._synthesize_narrative(report)

        return report

    def analyze_single_change(
        self,
        module_name: str,
        change: Optional[ChangeRecord] = None,
    ) -> ChangeImpact:
        """
        Analyze the impact of changing a single module.

        Returns a ChangeImpact with detailed reasoning.
        """
        # Compute blast radius
        direct_dependents = self.graph.immediate_dependents(module_name)
        all_dependents = self.graph.downstream_dependents(module_name)
        blast_radius = len(all_dependents)

        # Determine change type
        change_type = change.change_type if change else "modified"

        # Assess risk level with semantic reasoning
        risk_level = self._assess_change_risk(module_name, blast_radius)

        # Build impact paths
        impact_paths = self._build_impact_paths(module_name, direct_dependents, all_dependents)

        # Determine affected roles
        affected_roles = self._get_affected_roles(all_dependents)

        # Assess which principles are impacted
        principle_impacts = self._assess_principle_impact(module_name, blast_radius, affected_roles)

        # Synthesize explanation
        explanation = self._explain_why(module_name, risk_level, blast_radius, affected_roles)

        return ChangeImpact(
            module=module_name,
            change_type=change_type,
            risk_level=risk_level,
            blast_radius=blast_radius,
            affected_roles=affected_roles,
            impact_paths=impact_paths,
            principle_impacts=principle_impacts,
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Impact path tracing
    # ------------------------------------------------------------------

    def _build_impact_paths(
        self,
        module_name: str,
        direct_dependents: List[str],
        all_dependents: Set[str],
    ) -> List[ImpactPath]:
        """Build detailed impact propagation paths."""
        paths: List[ImpactPath] = []

        # Direct impact
        for dep in direct_dependents[:5]:  # Cap at 5 for readability
            path_risk = self._path_risk(module_name, dep)
            paths.append(ImpactPath(
                path=[module_name, dep],
                propagation_type="direct_dependency",
                risk_level=path_risk,
                explanation=(
                    f"'{dep}' directly imports '{module_name}'. "
                    f"Any breaking change to '{module_name}' will immediately affect '{dep}'."
                ),
            ))

        # Transitive impact (sample up to 3 deep paths)
        for dep in list(all_dependents - set(direct_dependents))[:3]:
            deep_path = self._find_shortest_path(module_name, dep)
            if deep_path and len(deep_path) >= 3:
                paths.append(ImpactPath(
                    path=deep_path,
                    propagation_type="transitive_dependency",
                    risk_level="medium",
                    explanation=(
                        f"Change propagates through {len(deep_path) - 1} hops: "
                        f"{' → '.join(deep_path)}. "
                        f"'{dep}' is indirectly affected."
                    ),
                ))

        # Semantic coupling impact
        if self.semantic_graph:
            similar = self.semantic_graph.find_similar_modules(module_name, top_n=2)
            for sim in similar:
                other = sim.module_a if sim.module_a != module_name else sim.module_b
                if other not in all_dependents:
                    paths.append(ImpactPath(
                        path=[module_name, other],
                        propagation_type="semantic_coupling",
                        risk_level="low",
                        explanation=(
                            f"'{other}' is structurally similar to '{module_name}' "
                            f"(score: {sim.score:.2f}, basis: {sim.basis}). "
                            f"Changes here may indicate needed changes there."
                        ),
                    ))

        # Architectural impact
        source_role = self._get_module_role(module_name)
        if source_role in ("service", "model", "interface"):
            # These roles are architectural pillars
            for dep in direct_dependents[:2]:
                dep_role = self._get_module_role(dep)
                if dep_role and dep_role != "utility":
                    paths.append(ImpactPath(
                        path=[module_name, dep],
                        propagation_type="architectural",
                        risk_level="high" if source_role == "interface" else "medium",
                        explanation=(
                            f"Architectural significance: '{module_name}' is a {source_role}. "
                            f"Changes to a {source_role} propagate architectural constraints "
                            f"to dependents like '{dep}' ({dep_role})."
                        ),
                    ))

        return paths

    # ------------------------------------------------------------------
    # Risk assessment
    # ------------------------------------------------------------------

    def _assess_change_risk(self, module_name: str, blast_radius: int) -> str:
        """Assess change risk with semantic reasoning."""
        points = 0

        # Blast radius
        if blast_radius > 10:
            points += 4
        elif blast_radius > 5:
            points += 3
        elif blast_radius > 2:
            points += 2
        elif blast_radius > 0:
            points += 1

        # Architectural role significance
        role = self._get_module_role(module_name)
        if role in ("interface", "model"):
            points += 3  # Core abstractions — high impact
        elif role in ("service", "repository"):
            points += 2
        elif role in ("controller", "middleware"):
            points += 1

        # Semantic significance: is this a pattern implementation?
        if self.semantic_graph:
            patterns = self.semantic_graph.get_patterns(module_name)
            if patterns:
                points += len(patterns)

        # Cycle involvement
        cycles = self.graph.find_cycles()
        for cycle in cycles:
            if module_name in cycle:
                points += 2  # Cyclic modules are dangerous to change
                break

        # Domain criticality
        if self.knowledge_base:
            domains = self.knowledge_base.get_domain_concepts(module_name)
            if domains:
                # Check if belongs to core_domain
                for d in domains:
                    # Look up the fact to check category
                    facts = self.knowledge_base.query(subject=module_name, predicate="belongs_to_domain")
                    for f in facts:
                        if f.confidence > 0.7:
                            points += 1
                            break

        if points >= 6:
            return "critical"
        elif points >= 4:
            return "high"
        elif points >= 2:
            return "medium"
        elif points >= 1:
            return "low"
        return "none"

    def _path_risk(self, source: str, target: str) -> str:
        """Assess risk along a specific dependency path."""
        # Semantic edges (inheritance, implementation) are higher risk
        if self.semantic_graph:
            sem_edges = self.semantic_graph.get_semantic_edges(module=source)
            for e in sem_edges:
                if e.target == target and e.relation_type in ("inherits", "implements"):
                    return "high"

        # Check if target is a critical role
        target_role = self._get_module_role(target)
        if target_role in ("controller", "service"):
            return "medium"

        return "low"

    # ------------------------------------------------------------------
    # Principle impact
    # ------------------------------------------------------------------

    def _assess_principle_impact(
        self,
        module_name: str,
        blast_radius: int,
        affected_roles: List[str],
    ) -> List[str]:
        """Assess which design principles are affected by this change."""
        impacts: List[str] = []

        if blast_radius > 5:
            impacts.append(
                "Single Responsibility Principle: This module is depended on by many — "
                "it may have too many responsibilities. Consider splitting."
            )

        if "interface" in self._get_module_role(module_name):
            impacts.append(
                "Interface Segregation Principle: Changing an interface affects all "
                "implementors. Ensure the change is backward-compatible."
            )

        if blast_radius > 0 and not self.semantic_graph:
            pass  # Can't assess further without semantic data

        if self.semantic_graph:
            patterns = self.semantic_graph.get_patterns(module_name)
            for p in patterns:
                if p.pattern == "facade":
                    impacts.append(
                        "Facade Pattern: This module simplifies a complex subsystem. "
                        "Changes may expose internal complexity to consumers."
                    )
                elif p.pattern == "singleton":
                    impacts.append(
                        "Singleton Pattern: Global state changes can have "
                        "unpredictable side effects across the entire system."
                    )

        return impacts

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _explain_why(
        self,
        module_name: str,
        risk_level: str,
        blast_radius: int,
        affected_roles: List[str],
    ) -> str:
        """Produce a natural-language explanation of WHY this change matters."""
        role = self._get_module_role(module_name)

        parts = [f"Changing '{module_name}' is a **{risk_level.upper()}** risk change."]

        if role and role != "unknown":
            parts.append(f"This module serves as a **{role}** in the architecture.")

        if blast_radius == 0:
            parts.append(
                "No modules depend on it, so the change is locally contained. "
                "However, verify that tests exist for this module's behavior."
            )
        elif blast_radius <= 3:
            parts.append(
                f"It directly or transitively affects **{blast_radius} module(s)**. "
                f"Review these dependents to ensure compatibility."
            )
        else:
            parts.append(
                f"It has a **blast radius of {blast_radius} module(s)** — "
                f"changes can cascade broadly. "
                f"Create a comprehensive test plan before proceeding."
            )

        if affected_roles:
            unique_roles = list(set(affected_roles))
            parts.append(f"Affected architectural roles: {', '.join(unique_roles)}.")

        # Add semantic insight if available
        if self.semantic_graph:
            patterns = self.semantic_graph.get_patterns(module_name)
            if patterns:
                pattern_names = [p.pattern for p in patterns]
                parts.append(
                    f"This module implements the {', '.join(pattern_names)} pattern(s) — "
                    f"preserving the pattern contract is important."
                )

        return " ".join(parts)

    def _synthesize_narrative(self, report: ImpactReport) -> str:
        """Synthesize the overall impact narrative."""
        parts = []

        if not report.changes:
            return "No changes to analyze."

        total_affected = sum(c.blast_radius for c in report.changes)
        critical_changes = [c for c in report.changes if c.risk_level == "critical"]
        high_changes = [c for c in report.changes if c.risk_level == "high"]

        parts.append(
            f"**{len(report.changes)} change(s)** analyzed. "
            f"Combined blast radius: **{total_affected} modules** potentially affected. "
            f"System risk level: **{report.system_risk_level.upper()}**."
        )

        if critical_changes:
            parts.append(
                f"\n**⚠️  {len(critical_changes)} critical-risk change(s):**"
            )
            for c in critical_changes:
                parts.append(f"  - `{c.module}`: {c.explanation[:150]}...")

        if high_changes:
            parts.append(
                f"\n**{len(high_changes)} high-risk change(s)** — review recommended."
            )

        if report.recommended_mitigations:
            parts.append("\n**Recommended Mitigations:**")
            for i, m in enumerate(report.recommended_mitigations, 1):
                parts.append(f"  {i}. {m}")

        return "\n".join(parts)

    def _assess_system_risk(self, report: ImpactReport) -> str:
        """Assess overall system risk level from all changes."""
        risk_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "none": 0}
        max_risk = 0
        for c in report.changes:
            max_risk = max(max_risk, risk_order.get(c.risk_level, 0))

        if len(report.changes) >= 5 and max_risk >= 2:
            return "critical"
        elif max_risk >= 3:
            return "high"
        elif max_risk >= 2:
            return "medium"
        elif max_risk >= 1:
            return "low"
        return "none"

    def _recommend_mitigations(self, report: ImpactReport) -> List[str]:
        """Recommend mitigation strategies."""
        mitigations: List[str] = []

        total_affected = sum(c.blast_radius for c in report.changes)
        if total_affected > 20:
            mitigations.append(
                "Stagger the deployment: break this change into smaller, independently "
                "releasable increments to reduce the blast radius."
            )

        # Check for critical paths
        if report.critical_paths:
            mitigations.append(
                f"Address {len(report.critical_paths)} critical impact path(s) first — "
                f"these represent the highest propagation risk."
            )

        # Check for semantic coupling
        has_semantic = any(
            p.propagation_type == "semantic_coupling"
            for c in report.changes for p in c.impact_paths
        )
        if has_semantic:
            mitigations.append(
                "Semantic coupling detected — modules that are structurally similar may "
                "also need updates. Run `lynkmesh-ai semantic similar` to identify them."
            )

        # Test coverage recommendation
        affected_modules = set()
        for c in report.changes:
            affected_modules.update(
                p.path[-1] for p in c.impact_paths
            )
        if affected_modules:
            mitigations.append(
                f"Run tests for {len(affected_modules)} affected module(s) before merging."
            )

        # Default
        if not mitigations:
            mitigations.append("Standard code review is sufficient for this change scope.")

        return mitigations

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_module_role(self, module_name: str) -> str:
        """Get the role of a module."""
        if self.semantic_graph:
            role = self.semantic_graph.get_role(module_name)
            if role:
                return role.role
        return "unknown"

    def _get_affected_roles(self, modules: Set[str]) -> List[str]:
        """Get unique roles of affected modules."""
        roles: Set[str] = set()
        for mod in modules:
            role = self._get_module_role(mod)
            if role != "unknown":
                roles.add(role)
        return sorted(roles)

    def _find_shortest_path(self, source: str, target: str, max_depth: int = 5) -> Optional[List[str]]:
        """BFS to find shortest path from source to target in the dependency graph."""
        if source == target:
            return [source]

        from collections import deque
        queue = deque([[source]])
        visited = {source}

        while queue:
            path = queue.popleft()
            current = path[-1]

            if len(path) > max_depth:
                continue

            for neighbor in self.graph.immediate_dependents(current):
                if neighbor == target:
                    return path + [target]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])

        return None

    def _file_to_module(self, file_path: str) -> str:
        """Convert file path to module name."""
        import re
        return re.sub(r'[\\/]', '.', file_path).replace('.py', '')
