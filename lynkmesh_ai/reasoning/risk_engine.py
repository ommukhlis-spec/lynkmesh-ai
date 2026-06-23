"""
RiskEngine — multi-dimensional risk assessment with reasoning.

Computes risk from:
1. Dependency centrality (how many things depend on this?)
2. Change frequency (how often does this module change?)
3. Semantic coupling (how many similar modules exist?)
4. Architectural significance (role, patterns, domain criticality)
5. Cyclomatic complexity (structural indicators from LoC, class count)

Produces RiskAssessment with per-dimension scores and explanations.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from lynkmesh_ai.core.graph import DependencyGraph
from lynkmesh_ai.core.change_tracker import ChangeRecord
from lynkmesh_ai.semantic.graph import SemanticGraph
from lynkmesh_ai.knowledge.base import KnowledgeBase

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Output types
# ══════════════════════════════════════════════════════════════════════

@dataclass
class RiskDimension:
    """A single dimension of risk."""
    name: str               # e.g., "dependency_centrality", "change_frequency"
    score: float            # 0.0 to 1.0
    weight: float           # Contribution weight to overall risk
    explanation: str        # Human-readable explanation
    evidence: List[str] = field(default_factory=list)


@dataclass
class RiskAssessment:
    """Complete multi-dimensional risk assessment for a module."""
    module: str
    overall_score: float        # 0.0 to 1.0
    overall_level: str          # "critical", "high", "medium", "low", "none"
    dimensions: List[RiskDimension] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)       # Top contributing factors
    mitigating_factors: List[str] = field(default_factory=list) # Things that reduce risk
    explanation: str = ""       # Narrative explanation
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "overall_score": self.overall_score,
            "overall_level": self.overall_level,
            "dimensions": [vars(d) for d in self.dimensions],
            "risk_factors": self.risk_factors,
            "mitigating_factors": self.mitigating_factors,
            "explanation": self.explanation,
            "metadata": self.metadata,
        }


class RiskEngine:
    """
    Computes multi-dimensional risk scores with reasoning.

    Unlike the simple risk scoring in DependencyGraph (which only counts
    dependents), this engine considers architectural significance,
    semantic coupling, change patterns, and structural complexity.
    """

    # Dimension weights (must sum to 1.0)
    DEFAULT_WEIGHTS: Dict[str, float] = {
        "dependency_centrality": 0.25,
        "architectural_significance": 0.25,
        "structural_complexity": 0.20,
        "semantic_coupling": 0.15,
        "change_volatility": 0.10,
        "cycle_risk": 0.05,
    }

    def __init__(
        self,
        graph: DependencyGraph,
        semantic_graph: Optional[SemanticGraph] = None,
        knowledge_base: Optional[KnowledgeBase] = None,
        change_history: Optional[List[ChangeRecord]] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self.graph = graph
        self.semantic_graph = semantic_graph
        self.knowledge_base = knowledge_base
        self.change_history = change_history or []
        self.weights = weights or dict(self.DEFAULT_WEIGHTS)

        # Precompute for efficiency
        self._change_counts: Dict[str, int] = self._count_changes_per_module()

    # ------------------------------------------------------------------
    # Full analysis
    # ------------------------------------------------------------------

    def compute_risk(self, module_name: str) -> RiskAssessment:
        """
        Compute multi-dimensional risk for a single module.

        Returns a RiskAssessment with per-dimension scores and explanation.
        """
        if not self.graph.has_node(module_name):
            return RiskAssessment(
                module=module_name,
                overall_score=0.0,
                overall_level="none",
                explanation=f"Module '{module_name}' not found in graph.",
            )

        dimensions: List[RiskDimension] = []
        risk_factors: List[str] = []
        mitigating_factors: List[str] = []

        # 1. Dependency Centrality
        d = self._assess_dependency_centrality(module_name)
        dimensions.append(d)
        if d.score > 0.5:
            risk_factors.append(d.explanation[:120])
        elif d.score < 0.2:
            mitigating_factors.append(d.explanation[:120])

        # 2. Architectural Significance
        d = self._assess_architectural_significance(module_name)
        dimensions.append(d)
        if d.score > 0.5:
            risk_factors.append(d.explanation[:120])

        # 3. Structural Complexity
        d = self._assess_structural_complexity(module_name)
        dimensions.append(d)
        if d.score > 0.5:
            risk_factors.append(d.explanation[:120])

        # 4. Semantic Coupling
        d = self._assess_semantic_coupling(module_name)
        dimensions.append(d)
        if d.score > 0.5:
            risk_factors.append(d.explanation[:120])
        elif d.score < 0.2:
            mitigating_factors.append("Low semantic coupling — changes are locally contained")

        # 5. Change Volatility
        d = self._assess_change_volatility(module_name)
        dimensions.append(d)
        if d.score > 0.5:
            risk_factors.append(d.explanation[:120])
        elif d.score < 0.2:
            mitigating_factors.append("Low change frequency — module is stable")

        # 6. Cycle Risk
        d = self._assess_cycle_risk(module_name)
        dimensions.append(d)
        if d.score > 0.5:
            risk_factors.append(d.explanation[:120])

        # Compute weighted overall
        overall_score = sum(
            d.score * d.weight for d in dimensions
        )
        overall_score = round(min(overall_score, 1.0), 3)
        overall_level = self._score_to_level(overall_score)

        # Synthesize explanation
        explanation = self._synthesize_risk_explanation(
            module_name, overall_level, risk_factors, mitigating_factors
        )

        return RiskAssessment(
            module=module_name,
            overall_score=overall_score,
            overall_level=overall_level,
            dimensions=dimensions,
            risk_factors=risk_factors,
            mitigating_factors=mitigating_factors,
            explanation=explanation,
            metadata={
                "weights_used": self.weights,
                "change_history_count": len(self.change_history),
            },
        )

    def compute_systemic_risk(self) -> Dict[str, RiskAssessment]:
        """
        Compute risk for ALL modules and return a map.

        Use this for identifying risk hotspots across the system.
        """
        results: Dict[str, RiskAssessment] = {}
        for node in self.graph.iter_nodes():
            results[node.name] = self.compute_risk(node.name)
        return results

    def identify_risk_hotspots(self, threshold: float = 0.5) -> List[RiskAssessment]:
        """
        Identify modules with elevated overall risk.

        Args:
            threshold: Minimum overall_score to be considered a hotspot.

        Returns:
            List of RiskAssessment sorted by score descending.
        """
        all_risks = self.compute_systemic_risk()
        hotspots = [
            r for r in all_risks.values()
            if r.overall_score >= threshold
        ]
        hotspots.sort(key=lambda r: r.overall_score, reverse=True)
        return hotspots

    def compute_change_risk(
        self,
        changes: List[ChangeRecord],
    ) -> List[RiskAssessment]:
        """
        Compute risk specifically for changed modules.
        """
        results: List[RiskAssessment] = []
        for change in changes:
            module_name = change.module_name
            if not module_name:
                continue
            if self.graph.has_node(module_name):
                risk = self.compute_risk(module_name)
                risk.metadata["change_type"] = change.change_type
                risk.metadata["lines_added"] = change.lines_added
                risk.metadata["lines_removed"] = change.lines_removed
                results.append(risk)
        return results

    # ------------------------------------------------------------------
    # Risk dimensions
    # ------------------------------------------------------------------

    def _assess_dependency_centrality(self, module: str) -> RiskDimension:
        """Assess risk from dependency centrality (fan-in/fan-out)."""
        direct_deps = len(self.graph.immediate_dependencies(module))
        direct_dependents = len(self.graph.immediate_dependents(module))
        all_dependents = len(self.graph.downstream_dependents(module))

        # Score: normalized sum of fan-in + fan-out
        max_edges = max(self.graph.edge_count, 1)
        centrality = (direct_deps + direct_dependents) / max(1, self.graph.node_count * 0.5)
        score = min(centrality, 1.0)

        if all_dependents > 10:
            explanation = (
                f"'{module}' is a critical dependency hub: {direct_dependents} direct dependents, "
                f"{all_dependents} total transitive dependents. Changes affect a large portion of the system."
            )
        elif all_dependents > 3:
            explanation = (
                f"'{module}' has moderate centrality: {direct_dependents} direct, "
                f"{all_dependents} transitive dependents."
            )
        else:
            explanation = (
                f"'{module}' has low centrality: {direct_dependents} dependents. "
                f"Changes are relatively contained."
            )

        return RiskDimension(
            name="dependency_centrality",
            score=round(score, 3),
            weight=self.weights["dependency_centrality"],
            explanation=explanation,
            evidence=[
                f"Direct dependents: {direct_dependents}",
                f"Direct dependencies: {direct_deps}",
                f"Transitive dependents: {all_dependents}",
            ],
        )

    def _assess_architectural_significance(self, module: str) -> RiskDimension:
        """Assess risk from architectural role and domain importance."""
        score = 0.0
        evidence: List[str] = []

        role = self._get_module_role(module)
        if role in ("interface", "model"):
            score += 0.4
            evidence.append(f"Architectural role '{role}' is a core abstraction — changes have wide impact")
        elif role in ("service", "repository"):
            score += 0.3
            evidence.append(f"Architectural role '{role}' contains business logic")
        elif role in ("controller", "middleware"):
            score += 0.2
            evidence.append(f"Architectural role '{role}' handles request flow")

        # Pattern significance
        if self.semantic_graph:
            patterns = self.semantic_graph.get_patterns(module)
            for p in patterns:
                if p.pattern in ("singleton", "facade"):
                    score += 0.2
                    evidence.append(f"Implements {p.pattern} pattern — global state implications")
                elif p.pattern in ("repository", "factory"):
                    score += 0.15
                    evidence.append(f"Implements {p.pattern} pattern — architectural contract")

        # Domain criticality
        if self.knowledge_base:
            domains = self.knowledge_base.get_domain_concepts(module)
            if domains:
                score += 0.1 * min(len(domains), 3)
                evidence.append(f"Belongs to {len(domains)} domain concept(s): {', '.join(domains[:3])}")

        score = min(score, 1.0)

        if score >= 0.5:
            explanation = f"'{module}' is architecturally significant — changes have disproportionate impact."
        elif score >= 0.2:
            explanation = f"'{module}' has some architectural significance — review changes carefully."
        else:
            explanation = f"'{module}' has low architectural significance — changes are locally scoped."

        return RiskDimension(
            name="architectural_significance",
            score=round(score, 3),
            weight=self.weights["architectural_significance"],
            explanation=explanation,
            evidence=evidence,
        )

    def _assess_structural_complexity(self, module: str) -> RiskDimension:
        """Assess risk from code complexity indicators."""
        node = self.graph.get_node(module)
        if not node:
            return RiskDimension(
                name="structural_complexity",
                score=0.0,
                weight=self.weights["structural_complexity"],
                explanation="No structural data available.",
                evidence=[],
            )

        evidence: List[str] = []
        complexity_points = 0.0

        # Lines of code
        if node.lines_of_code > 500:
            complexity_points += 0.4
            evidence.append(f"Large module: {node.lines_of_code} LOC")
        elif node.lines_of_code > 200:
            complexity_points += 0.2
            evidence.append(f"Medium module: {node.lines_of_code} LOC")

        # Class count
        class_count = len(node.classes)
        if class_count > 10:
            complexity_points += 0.3
            evidence.append(f"Many classes: {class_count}")
        elif class_count > 5:
            complexity_points += 0.15
            evidence.append(f"Moderate class count: {class_count}")

        # Function count
        func_count = len(node.functions)
        if func_count > 20:
            complexity_points += 0.3
            evidence.append(f"Many functions: {func_count}")
        elif func_count > 10:
            complexity_points += 0.15
            evidence.append(f"Moderate function count: {func_count}")

        # Import count (proxy for responsibility breadth)
        import_count = len(node.imports)
        if import_count > 15:
            complexity_points += 0.2
            evidence.append(f"Many imports: {import_count} — possible SRP violation")

        score = min(complexity_points, 1.0)

        if score > 0.5:
            explanation = f"'{module}' is structurally complex ({node.lines_of_code} LOC, {class_count} classes, {func_count} functions)."
        elif score > 0.2:
            explanation = f"'{module}' has moderate structural complexity."
        else:
            explanation = f"'{module}' is structurally simple."

        return RiskDimension(
            name="structural_complexity",
            score=round(score, 3),
            weight=self.weights["structural_complexity"],
            explanation=explanation,
            evidence=evidence,
        )

    def _assess_semantic_coupling(self, module: str) -> RiskDimension:
        """Assess risk from semantic coupling (similar modules that may co-change)."""
        score = 0.0
        evidence: List[str] = []

        if self.semantic_graph:
            similar = self.semantic_graph.find_similar_modules(module, top_n=5)

            # Count high-similarity modules
            high_similar = [s for s in similar if s.score >= 0.5]
            if high_similar:
                score += 0.15 * min(len(high_similar), 5)
                evidence.append(
                    f"Highly similar to {len(high_similar)} module(s): "
                    f"{', '.join(self._similar_target(s, module) for s in high_similar[:3])}"
                )

            # Semantic edges indicate architectural coupling
            sem_edges = self.semantic_graph.get_semantic_edges(module=module)
            if sem_edges:
                score += 0.1 * min(len(sem_edges), 3)
                evidence.append(f"{len(sem_edges)} semantic edge(s) increase coupling surface")

            score = min(score, 1.0)

        if score > 0.5:
            explanation = (
                f"'{module}' has high semantic coupling — changes here may necessitate "
                f"changes in structurally similar modules."
            )
        elif score > 0.2:
            explanation = f"'{module}' has moderate semantic coupling."
        else:
            explanation = f"'{module}' has low semantic coupling."

        return RiskDimension(
            name="semantic_coupling",
            score=round(score, 3),
            weight=self.weights["semantic_coupling"],
            explanation=explanation,
            evidence=evidence,
        )

    def _assess_change_volatility(self, module: str) -> RiskDimension:
        """Assess risk from historical change frequency."""
        change_count = self._change_counts.get(module, 0)

        evidence: List[str] = []
        if change_count >= 5:
            score = 0.8
            explanation = (
                f"'{module}' has changed {change_count} times — it is a high-churn module. "
                f"Frequent changes increase the probability of introducing defects."
            )
            evidence.append(f"Changed {change_count} times in recent history")
        elif change_count >= 2:
            score = 0.4
            explanation = f"'{module}' has changed {change_count} times — moderate churn."
            evidence.append(f"Changed {change_count} times")
        elif change_count == 1:
            score = 0.2
            explanation = "Module has changed once recently — stable otherwise."
        else:
            score = 0.0
            explanation = "No recent changes — the module is stable."

        return RiskDimension(
            name="change_volatility",
            score=round(score, 3),
            weight=self.weights["change_volatility"],
            explanation=explanation,
            evidence=evidence,
        )

    def _assess_cycle_risk(self, module: str) -> RiskDimension:
        """Assess risk from involvement in dependency cycles."""
        cycles = self.graph.find_cycles()
        module_cycles = [c for c in cycles if module in c]

        if not module_cycles:
            return RiskDimension(
                name="cycle_risk",
                score=0.0,
                weight=self.weights["cycle_risk"],
                explanation="Module is not involved in any dependency cycle.",
                evidence=[],
            )

        cycle_count = len(module_cycles)
        max_cycle_len = max(len(c) for c in module_cycles) if module_cycles else 0

        if cycle_count >= 2:
            score = 0.9
        elif max_cycle_len >= 4:
            score = 0.7
        else:
            score = 0.5

        explanation = (
            f"'{module}' is part of {cycle_count} cycle(s) "
            f"(max length: {max_cycle_len}). "
            f"Cyclic modules are harder to test, reason about, and change safely."
        )

        return RiskDimension(
            name="cycle_risk",
            score=round(score, 3),
            weight=self.weights["cycle_risk"],
            explanation=explanation,
            evidence=[
                f"Involved in {cycle_count} dependency cycle(s)",
                f"Largest cycle length: {max_cycle_len}",
            ],
        )

    # ------------------------------------------------------------------
    # Explanation synthesis
    # ------------------------------------------------------------------

    def _synthesize_risk_explanation(
        self,
        module: str,
        level: str,
        risk_factors: List[str],
        mitigating: List[str],
    ) -> str:
        """Synthesize a natural-language risk explanation."""
        parts = []

        parts.append(f"**Risk Assessment for '{module}': {level.upper()}**")

        if risk_factors:
            parts.append(f"\nKey risk factors:")
            for f in risk_factors[:3]:
                parts.append(f"  - {f}")

        if mitigating:
            parts.append(f"\nMitigating factors:")
            for m in mitigating[:3]:
                parts.append(f"  - {m}")

        if level == "critical":
            parts.append(
                f"\nThis module requires **exceptional care**. "
                f"Changes should be reviewed by at least two senior engineers, "
                f"include comprehensive tests, and be deployed with a rollback plan."
            )
        elif level == "high":
            parts.append(
                f"\nChanges to this module should include **thorough testing** "
                f"and review of all dependents."
            )
        elif level == "medium":
            parts.append(
                f"\nStandard change practices apply. "
                f"Review dependents for compatibility."
            )
        else:
            parts.append(
                f"\nThis is a low-risk module. Standard development practices apply."
            )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_module_role(self, module: str) -> str:
        """Get the role of a module."""
        if self.semantic_graph:
            role = self.semantic_graph.get_role(module)
            if role:
                return role.role
        return "unknown"

    def _count_changes_per_module(self) -> Dict[str, int]:
        """Count changes per module from change history."""
        counts: Dict[str, int] = defaultdict(int)
        for change in self.change_history:
            if change.module_name:
                counts[change.module_name] += 1
        return dict(counts)

    @staticmethod
    def _similar_target(sim, module: str) -> str:
        """Extract the 'other' module from a similarity score."""
        return sim.module_a if sim.module_a != module else sim.module_b

    @staticmethod
    def _score_to_level(score: float) -> str:
        """Convert a numeric score to a risk level."""
        if score >= 0.7:
            return "critical"
        elif score >= 0.5:
            return "high"
        elif score >= 0.3:
            return "medium"
        elif score >= 0.1:
            return "low"
        return "none"
