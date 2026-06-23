"""
DecisionEngine — produces architecture decisions, recommendations, and ADRs.

Consumes ArchitectureReport + ImpactReport + KnowledgeBase to:
- Recommend concrete actions (refactoring, abstraction, testing)
- Generate Architecture Decision Records (ADRs)
- Identify technical debt items with priority
- Evaluate trade-offs between alternative approaches
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from lynkmesh_ai.core.graph import DependencyGraph
from lynkmesh_ai.semantic.graph import SemanticGraph
from lynkmesh_ai.knowledge.base import KnowledgeBase
from lynkmesh_ai.knowledge.fact import KnowledgeFact
from lynkmesh_ai.reasoning.architecture_analyzer import ArchitectureReport
from lynkmesh_ai.reasoning.impact_analyzer import ImpactReport

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Output types
# ══════════════════════════════════════════════════════════════════════

class ActionType(str, Enum):
    REFACTOR = "refactor"
    ADD_ABSTRACTION = "add_abstraction"
    ADD_TESTS = "add_tests"
    EXTRACT_MODULE = "extract_module"
    BREAK_CYCLE = "break_cycle"
    INTRODUCE_INTERFACE = "introduce_interface"
    CONSOLIDATE = "consolidate"
    DOCUMENT = "document"
    REMOVE = "remove"


class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


@dataclass
class ActionRecommendation:
    """A concrete, actionable recommendation."""
    action_type: ActionType
    target_module: str
    title: str
    rationale: str
    priority: str  # "critical", "high", "medium", "low"
    effort_estimate: str  # "small", "medium", "large"
    expected_impact: str
    related_modules: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "target_module": self.target_module,
            "title": self.title,
            "rationale": self.rationale,
            "priority": self.priority,
            "effort_estimate": self.effort_estimate,
            "expected_impact": self.expected_impact,
            "related_modules": self.related_modules,
            "alternatives": self.alternatives,
        }


@dataclass
class ArchitectureDecision:
    """An Architecture Decision Record (ADR)."""
    decision_id: str
    title: str
    status: DecisionStatus = DecisionStatus.PROPOSED
    context: str = ""           # What is the issue we're addressing?
    decision: str = ""          # What is the decision?
    rationale: str = ""         # Why did we make this decision?
    consequences: str = ""      # What are the consequences?
    alternatives: List[str] = field(default_factory=list)
    related_modules: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "title": self.title,
            "status": self.status.value,
            "context": self.context,
            "decision": self.decision,
            "rationale": self.rationale,
            "consequences": self.consequences,
            "alternatives": self.alternatives,
            "related_modules": self.related_modules,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """Render as a standard ADR markdown document."""
        return f"""# ADR: {self.title}

**Status:** {self.status.value}
**Date:** {self.created_at[:10]}
**Modules:** {', '.join(f'`{m}`' for m in self.related_modules) if self.related_modules else 'N/A'}

## Context

{self.context}

## Decision

{self.decision}

## Rationale

{self.rationale}

## Consequences

{self.consequences}

## Alternatives Considered

{chr(10).join(f'- {a}' for a in self.alternatives) if self.alternatives else '- None recorded'}
"""


@dataclass
class TechnicalDebtItem:
    """A technical debt item with priority and remediation plan."""
    module: str
    description: str
    category: str       # "architectural", "code_quality", "testing", "documentation"
    priority: str       # "critical", "high", "medium", "low"
    effort: str         # "small", "medium", "large"
    remediation_steps: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "effort": self.effort,
            "remediation_steps": self.remediation_steps,
            "created_at": self.created_at,
        }


@dataclass
class DecisionReport:
    """Complete decision support output."""
    recommendations: List[ActionRecommendation] = field(default_factory=list)
    adrs: List[ArchitectureDecision] = field(default_factory=list)
    technical_debt: List[TechnicalDebtItem] = field(default_factory=list)
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendations": [r.to_dict() for r in self.recommendations],
            "adrs": [a.to_dict() for a in self.adrs],
            "technical_debt": [t.to_dict() for t in self.technical_debt],
            "summary": self.summary,
            "metadata": self.metadata,
        }


# ══════════════════════════════════════════════════════════════════════
# DecisionEngine
# ══════════════════════════════════════════════════════════════════════

class DecisionEngine:
    """
    Produces architecture decisions, recommendations, and technical debt analysis.

    Takes architectural analysis and impact assessment as input, and produces
    concrete, actionable output: what should be done, why, and how.
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
        self._decision_counter = 0

    # ------------------------------------------------------------------
    # Full analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        architecture_report: Optional[ArchitectureReport] = None,
        impact_report: Optional[ImpactReport] = None,
    ) -> DecisionReport:
        """
        Produce a complete decision support report.

        Args:
            architecture_report: From ArchitectureAnalyzer.
            impact_report: From ImpactAnalyzer.

        Returns:
            DecisionReport with recommendations, ADRs, and technical debt.
        """
        report = DecisionReport()

        # 1. Generate recommendations from architectural analysis
        report.recommendations = self.recommend_actions(architecture_report, impact_report)

        # 2. Generate ADRs for significant architectural decisions
        report.adrs = self._generate_adrs(architecture_report, impact_report)

        # 3. Identify technical debt
        report.technical_debt = self.identify_technical_debt(architecture_report)

        # 4. Synthesize summary
        report.summary = self._synthesize_summary(report)
        report.metadata = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "recommendation_count": len(report.recommendations),
            "adr_count": len(report.adrs),
            "debt_count": len(report.technical_debt),
        }

        return report

    # ------------------------------------------------------------------
    # Action recommendations
    # ------------------------------------------------------------------

    def recommend_actions(
        self,
        architecture_report: Optional[ArchitectureReport] = None,
        impact_report: Optional[ImpactReport] = None,
    ) -> List[ActionRecommendation]:
        """
        Recommend concrete actions based on architectural analysis.
        """
        recommendations: List[ActionRecommendation] = []

        if architecture_report:
            # From layering violations
            for v in architecture_report.layering_violations:
                if v.severity in ("critical", "major"):
                    recommendations.append(ActionRecommendation(
                        action_type=ActionType.REFACTOR,
                        target_module=v.source,
                        title=f"Fix layering violation: {v.source} → {v.target}",
                        rationale=v.explanation,
                        priority="critical" if v.severity == "critical" else "high",
                        effort_estimate="medium",
                        expected_impact="Restore proper dependency direction; reduce architectural erosion",
                    ))

            # From coupling hotspots
            for h in architecture_report.coupling_hotspots[:5]:
                if h.instability > 0.7:
                    recommendations.append(ActionRecommendation(
                        action_type=ActionType.INTRODUCE_INTERFACE,
                        target_module=h.module,
                        title=f"Introduce abstraction for '{h.module}'",
                        rationale=(
                            f"'{h.module}' is unstable (instability={h.instability:.2f}) — "
                            f"it depends on many modules. An interface would protect consumers "
                            f"from changes in dependencies."
                        ),
                        priority="high" if h.fan_out > 8 else "medium",
                        effort_estimate="medium",
                        expected_impact=f"Protect {h.fan_in} dependent(s) from ripple effects",
                    ))

            # From missing abstractions
            for m in architecture_report.missing_abstractions[:3]:
                recommendations.append(ActionRecommendation(
                    action_type=ActionType.INTRODUCE_INTERFACE,
                    target_module=m.module,
                    title=f"Add {m.suggested_pattern} for '{m.module}'",
                    rationale=m.reason,
                    priority="high" if len(m.consumers) > 5 else "medium",
                    effort_estimate="medium",
                    expected_impact=f"Decouple {len(m.consumers)} consumer(s) from implementation details",
                ))

            # From low cohesion
            for c in architecture_report.cohesion_assessments:
                if not c.is_cohesive and c.module_count >= 3:
                    recommendations.append(ActionRecommendation(
                        action_type=ActionType.CONSOLIDATE,
                        target_module=c.package,
                        title=f"Review package cohesion for '{c.package}'",
                        rationale=(
                            f"Package '{c.package}' has low cohesion ({c.cohesion_ratio:.0%} internal deps). "
                            f"Modules depend more on external packages than each other."
                        ),
                        priority="medium",
                        effort_estimate="large",
                        expected_impact="Clearer package boundaries; easier maintenance",
                    ))

        # From cycles
        cycles = self.graph.find_cycles()
        for cycle in cycles[:2]:
            cycle_str = " → ".join(cycle)
            recommendations.append(ActionRecommendation(
                action_type=ActionType.BREAK_CYCLE,
                target_module=cycle[0],
                title=f"Break dependency cycle: {cycle_str}",
                rationale=f"Circular dependency detected: {cycle_str}. Cycles prevent modular reasoning and testing.",
                priority="high",
                effort_estimate="medium",
                expected_impact="Restore DAG property; enable independent testing and deployment",
            ))

        # From impact report
        if impact_report:
            for change in impact_report.changes:
                if change.risk_level in ("critical", "high") and change.blast_radius > 5:
                    recommendations.append(ActionRecommendation(
                        action_type=ActionType.ADD_TESTS,
                        target_module=change.module,
                        title=f"Add integration tests for '{change.module}'",
                        rationale=(
                            f"Changing '{change.module}' has blast radius {change.blast_radius}. "
                            f"Integration tests are essential to catch regressions."
                        ),
                        priority="high",
                        effort_estimate="small",
                        expected_impact="Catch regressions before they reach production",
                    ))

        # Deduplicate by target + action_type
        seen = set()
        unique = []
        for r in recommendations:
            key = (r.target_module, r.action_type.value)
            if key not in seen:
                seen.add(key)
                unique.append(r)

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        unique.sort(key=lambda r: priority_order.get(r.priority, 99))

        return unique

    # ------------------------------------------------------------------
    # ADR generation
    # ------------------------------------------------------------------

    def _generate_adrs(
        self,
        architecture_report: Optional[ArchitectureReport] = None,
        impact_report: Optional[ImpactReport] = None,
    ) -> List[ArchitectureDecision]:
        """Generate Architecture Decision Records for significant findings."""
        adrs: List[ArchitectureDecision] = []

        if architecture_report:
            # ADR for architectural style
            if architecture_report.style_confidence >= 0.5:
                adrs.append(ArchitectureDecision(
                    decision_id=f"ADR-{self._next_id():04d}",
                    title=f"Architectural Style: {architecture_report.style.value.replace('_', ' ').title()}",
                    context=(
                        f"Based on analysis of {self.graph.node_count} modules across "
                        f"{len(set(n.package for n in self.graph.iter_nodes() if n.package))} packages, "
                        f"the system exhibits characteristics of a "
                        f"{architecture_report.style.value.replace('_', ' ').title()} architecture."
                    ),
                    decision=f"Recognize the {architecture_report.style.value.replace('_', ' ').title()} style as the primary architectural pattern.",
                    rationale="\n".join(architecture_report.style_evidence),
                    consequences=(
                        "Future changes should respect this architectural style. "
                        "Deviations should be documented as conscious decisions, not accidents."
                    ),
                    related_modules=sorted(architecture_report.coupling_hotspots[0].module if architecture_report.coupling_hotspots else "" or ""),
                ))

            # ADR for each significant layering violation
            for v in architecture_report.layering_violations:
                if v.severity == "critical":
                    adrs.append(ArchitectureDecision(
                        decision_id=f"ADR-{self._next_id():04d}",
                        title=f"Address Layering Violation: {v.source}",
                        context=v.explanation,
                        decision=(
                            f"Either refactor '{v.source}' to remove the reverse dependency on "
                            f"'{v.target}', or explicitly document why this exception is necessary."
                        ),
                        rationale=(
                            f"Layering violations erode architectural integrity over time. "
                            f"Each exception makes the next one easier. "
                            f"Expected direction: {v.expected_direction}."
                        ),
                        consequences=(
                            "If refactored: improved architectural clarity at cost of migration effort. "
                            "If documented: preserved velocity at cost of architectural debt."
                        ),
                        alternatives=[
                            "Refactor to introduce an interface or intermediary",
                            "Document as an explicit architectural exception",
                            "Accept and monitor (not recommended)",
                        ],
                        related_modules=[v.source, v.target],
                    ))

        # ADR from impact: if a change has critical system-wide impact
        if impact_report:
            if impact_report.system_risk_level in ("critical", "high"):
                affected = set()
                for c in impact_report.changes:
                    affected.update(p.path[-1] for p in c.impact_paths)
                adrs.append(ArchitectureDecision(
                    decision_id=f"ADR-{self._next_id():04d}",
                    title="System-Wide Change: Incremental Rollout Required",
                    context=(
                        f"A {impact_report.system_risk_level}-risk change affecting "
                        f"{len(affected)} modules is proposed."
                    ),
                    decision="Adopt an incremental rollout strategy with feature flags.",
                    rationale=(
                        "High blast-radius changes should be decomposed into smaller, "
                        "independently deployable increments. Each increment should be "
                        "validated before proceeding to the next."
                    ),
                    consequences=(
                        "Increased deployment complexity in the short term; "
                        "reduced blast radius and faster recovery in the long term."
                    ),
                    alternatives=[
                        "Big-bang deployment with extended testing window",
                        "Canary deployment with gradual traffic shifting",
                        "Parallel running of old and new implementations",
                    ],
                    related_modules=sorted(affected)[:10],
                ))

        return adrs

    # ------------------------------------------------------------------
    # Technical debt identification
    # ------------------------------------------------------------------

    def identify_technical_debt(
        self,
        architecture_report: Optional[ArchitectureReport] = None,
    ) -> List[TechnicalDebtItem]:
        """Identify technical debt items from architectural analysis."""
        debt: List[TechnicalDebtItem] = []

        # Cycles are always debt
        for cycle in self.graph.find_cycles():
            debt.append(TechnicalDebtItem(
                module=cycle[0],
                description=f"Circular dependency: {' → '.join(cycle)}",
                category="architectural",
                priority="high",
                effort="medium",
                remediation_steps=[
                    f"Identify the weakest link in the cycle: {' → '.join(cycle)}",
                    "Extract shared interface to break the cycle",
                    "Use dependency inversion to reverse one edge",
                ],
            ))

        if architecture_report:
            # Layering violations
            for v in architecture_report.layering_violations:
                debt.append(TechnicalDebtItem(
                    module=v.source,
                    description=f"Layering violation: {v.source} → {v.target} ({v.severity})",
                    category="architectural",
                    priority="high" if v.severity == "critical" else "medium",
                    effort="medium",
                    remediation_steps=[
                        f"Audit why '{v.source}' depends on '{v.target}'",
                        "Introduce an abstraction layer between them",
                        "Or move shared code to a lower layer",
                    ],
                ))

            # Low cohesion packages
            for c in architecture_report.cohesion_assessments:
                if c.cohesion_ratio < 0.3:
                    debt.append(TechnicalDebtItem(
                        module=c.package,
                        description=(
                            f"Package '{c.package}' has low cohesion ({c.cohesion_ratio:.0%}). "
                            f"{c.external_deps} external deps vs {c.internal_deps} internal."
                        ),
                        category="architectural",
                        priority="medium",
                        effort="large",
                        remediation_steps=[
                            f"Review the purpose of package '{c.package}'",
                            "Move unrelated modules to more appropriate packages",
                            "Extract shared concerns into a new package",
                        ],
                    ))

            # Missing abstractions
            for m in architecture_report.missing_abstractions:
                debt.append(TechnicalDebtItem(
                    module=m.module,
                    description=f"Missing abstraction: {len(m.consumers)} consumers directly depend on '{m.module}'",
                    category="code_quality",
                    priority="medium",
                    effort="small",
                    remediation_steps=[
                        f"Create {m.suggested_pattern} for '{m.module}'",
                        f"Migrate {len(m.consumers)} consumers to depend on the abstraction",
                        "Update tests to use the abstraction",
                    ],
                ))

        # Deduplicate
        seen = set()
        unique = []
        for d in debt:
            key = (d.module, d.description)
            if key not in seen:
                seen.add(key)
                unique.append(d)

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        unique.sort(key=lambda d: priority_order.get(d.priority, 99))

        return unique

    # ------------------------------------------------------------------
    # Knowledge base integration: store decisions as facts
    # ------------------------------------------------------------------

    def store_decisions(self, report: DecisionReport, kb: KnowledgeBase) -> int:
        """
        Store architecture decisions as KnowledgeFacts in the KnowledgeBase.

        Returns the number of facts added.
        """
        count = 0

        # Store ADRs as architecture_decision facts
        for adr in report.adrs:
            fact = KnowledgeFact(
                fact_id=adr.decision_id.lower().replace(" ", "_"),
                fact_type="architecture_decision",
                subject=",".join(adr.related_modules) if adr.related_modules else "system",
                predicate="has_decision",
                object_value=adr.title,
                confidence=0.9,
                evidence=[
                    f"Context: {adr.context[:200]}",
                    f"Decision: {adr.decision[:200]}",
                    f"Rationale: {adr.rationale[:200]}",
                ],
                source="DecisionEngine",
            )
            kb.add_fact(fact)
            count += 1

        # Store key recommendations as design_constraint facts
        for rec in report.recommendations:
            if rec.priority in ("critical", "high"):
                fact = KnowledgeFact(
                    fact_id=f"constraint_{rec.target_module}_{rec.action_type.value}",
                    fact_type="design_constraint",
                    subject=rec.target_module,
                    predicate="has_constraint",
                    object_value=rec.title,
                    confidence=0.8,
                    evidence=[rec.rationale],
                    source="DecisionEngine",
                )
                kb.add_fact(fact)
                count += 1

        # Store identified technical debt as learned_pattern facts
        for debt_item in report.technical_debt:
            if debt_item.priority in ("critical", "high"):
                fact = KnowledgeFact(
                    fact_id=f"debt_{debt_item.module}_{debt_item.category}",
                    fact_type="learned_pattern",
                    subject=debt_item.module,
                    predicate="has_technical_debt",
                    object_value=debt_item.description[:200],
                    confidence=0.85,
                    evidence=debt_item.remediation_steps,
                    source="DecisionEngine",
                )
                kb.add_fact(fact)
                count += 1

        return count

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _synthesize_summary(self, report: DecisionReport) -> str:
        """Synthesize the decision report into a concise summary."""
        parts = []

        critical_recs = [r for r in report.recommendations if r.priority == "critical"]
        high_recs = [r for r in report.recommendations if r.priority == "high"]

        if critical_recs:
            parts.append(
                f"**{len(critical_recs)} critical action(s)** require immediate attention:"
            )
            for r in critical_recs:
                parts.append(f"  - {r.title}")
            parts.append("")

        if high_recs:
            parts.append(
                f"**{len(high_recs)} high-priority action(s)** recommended:"
            )
            for r in high_recs[:3]:
                parts.append(f"  - {r.title}")

        if report.adrs:
            parts.append(f"\n**{len(report.adrs)} Architecture Decision Record(s)** generated.")

        if report.technical_debt:
            critical_debt = [d for d in report.technical_debt if d.priority == "critical"]
            high_debt = [d for d in report.technical_debt if d.priority == "high"]
            total_critical = len(critical_debt) + len(high_debt)
            if total_critical > 0:
                parts.append(
                    f"**{total_critical} high-priority technical debt item(s)** identified."
                )

        return "\n".join(parts) if parts else "No significant actions or decisions required."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._decision_counter += 1
        return self._decision_counter
