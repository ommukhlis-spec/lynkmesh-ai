# Changelog

All notable changes to LynkMesh AI.

## [0.3.0] — 2026-06-23

### Added — Reasoning Layer

- **ArchitectureAnalyzer** (`lynkmesh_ai/reasoning/architecture_analyzer.py`): Detects architectural style from 8 recognized styles (Layered, Hexagonal, Modular Monolith, Service-Oriented, Microservices, Event-Driven, CQRS, Plugin), identifies layering violations with severity classification, finds coupling hotspots with instability metrics, assesses package cohesion, identifies missing abstractions, detects SOLID principle violations, and synthesizes a human-readable architecture narrative.
- **ImpactAnalyzer** (`lynkmesh_ai/reasoning/impact_analyzer.py`): Explains WHY changes matter — computes blast radius, traces impact paths (direct, transitive, semantic, architectural), assesses principle impacts, and synthesizes natural-language impact narratives with recommended mitigations.
- **DecisionEngine** (`lynkmesh_ai/reasoning/decision_engine.py`): Produces concrete ActionRecommendations across 9 action types (Refactor, Add Abstraction, Add Tests, Extract Module, Break Cycle, Introduce Interface, Consolidate, Document, Remove), generates Architecture Decision Records (ADRs) with full context/rationale/consequences/alternatives in standard ADR format, identifies TechnicalDebt items with priority and remediation steps, and stores decisions as KnowledgeFacts for persistent Decision Memory.
- **RiskEngine** (`lynkmesh_ai/reasoning/risk_engine.py`): Multi-dimensional risk assessment across 6 weighted dimensions — Dependency Centrality (0.25), Architectural Significance (0.25), Structural Complexity (0.20), Semantic Coupling (0.15), Change Volatility (0.10), Cycle Risk (0.05) — with configurable weights, systemic risk computation, and risk hotspot identification.

### Added — Decision Memory (KnowledgeBase Extension)

- Three new KnowledgeFact types: `architecture_decision`, `design_constraint`, `learned_pattern`
- `KnowledgeBase.record_decision()` — Record architecture decisions with context/rationale
- `KnowledgeBase.record_constraint()` — Record design constraints for modules
- `KnowledgeBase.record_learned_pattern()` — Record patterns learned from architectural analysis
- `KnowledgeBase.get_decisions()`, `get_design_constraints()`, `get_learned_patterns()` — Typed queries
- `KnowledgeBase.get_decision_memory_summary()` — Decision memory overview

### Added — CLI

- `lynkmesh-ai reasoning analyze` — Full architecture reasoning report
- `lynkmesh-ai reasoning risk --module <name>` — Multi-dimensional risk assessment with visual bars
- `lynkmesh-ai reasoning impact --module <name>` — Change impact with WHY explanation
- `lynkmesh-ai reasoning decide [--save]` — Generate ADRs and recommendations
- `lynkmesh-ai run --reason` — Include architecture reasoning in task files
- `lynkmesh-ai run --semantic --reason` — Full intelligence pipeline (all flags compose)

### Changed — ContextPackage

- New field: `reasoning: Dict[str, Any]` — stores risk assessment, impact analysis, architecture narrative, and recommended actions (defaults to `{}` for backward compatibility)

### Changed — ClaudeTaskGenerator

- New template section: `## Architecture Reasoning` with subsections for Architecture Assessment, Risk Assessment, and Recommended Actions

---

## [0.2.0] — 2026-06-23

### Added — Semantic Layer

- **SemanticGraph** (`lynkmesh_ai/semantic/graph.py`): Wrapper around DependencyGraph with semantic edges, pattern matches, role classifications, domain concepts, and similarity scores. Full JSON serialization following the DependencyGraph pattern.
- **PatternDetector** (`lynkmesh_ai/semantic/patterns.py`): Detects 10 design patterns — Singleton, Factory, Repository, Observer, Strategy, Facade, Adapter, Command, Decorator, Template Method — using AST/heuristic rules with confidence scores and evidence.
- **RoleClassifier** (`lynkmesh_ai/semantic/roles.py`): Classifies modules into 13 architectural roles — Controller, Service, Repository, Model, Config, Utility, Interface, Middleware, Adapter, Factory, View, CLI, Unknown — using naming, structural, and graph-position heuristics.
- **DomainAnalyzer** (`lynkmesh_ai/semantic/domains.py`): Extracts domain concepts from module names, class names, docstrings, and package structure. 50+ domain keywords across 4 categories: core_domain, supporting, infrastructure, generic.
- **SimilarityAnalyzer** (`lynkmesh_ai/semantic/similarity.py`): Computes pairwise structural similarity using 4 dimensions — Jaccard similarity of imports, naming token overlap, co-coupling, and structural equivalence.
- **SemanticAnalyzer** (`lynkmesh_ai/semantic/analyzer.py`): Orchestrator that runs all analyzers and produces a fully populated SemanticGraph with inheritance/implements semantic edges.

### Added — Knowledge Layer

- **KnowledgeFact** (`lynkmesh_ai/knowledge/fact.py`): Canonical subject-predicate-object fact with confidence, evidence, and provenance. Hashable for deduplication.
- **KnowledgeBase** (`lynkmesh_ai/knowledge/base.py`): Schema-less fact store with typed queries (`query`, `search`, `get_facts_for_module`), convenience methods (`get_role`, `get_patterns`, `get_domain_concepts`, `get_modules_for_domain`), and semantic risk computation. Full JSON persistence.
- **KnowledgeExtractor** (`lynkmesh_ai/knowledge/extractor.py`): Bridges SemanticGraph → KnowledgeBase, converting each analysis dimension into KnowledgeFact instances.

### Added — CLI

- `lynkmesh-ai semantic analyze` — Full semantic analysis
- `lynkmesh-ai semantic patterns --all` / `--module <name>` — Design pattern detection
- `lynkmesh-ai semantic role --module <name>` — Architectural role classification
- `lynkmesh-ai semantic similar --module <name>` — Find structurally similar modules
- `lynkmesh-ai semantic domains` — List domain concepts
- `lynkmesh-ai knowledge summary` / `build` / `query` — Knowledge base operations
- `lynkmesh-ai run --semantic` — Include semantic analysis in context

### Changed — Core Parser

- `ModuleInfo` now captures `class_bases` (class inheritance hierarchies) and `class_methods` (per-class method tracking)
- `_ModuleVisitor` tracks current class context during AST traversal
- New helper: `_base_class_name()` for extracting base class names from AST nodes

### Changed — ContextPackage

- New fields: `semantic_edges`, `design_patterns`, `domain_concepts`, `architectural_role` (all with defaults for backward compatibility)
- New dataclass: `SemanticEdge` for semantic relationship edges

### Changed — ContextBuilder

- Accepts optional `semantic_graph` and `knowledge_base` parameters
- New `_enrich_with_semantics()` method that populates ContextPackage with semantic data when available

### Changed — ClaudeTaskGenerator

- New template sections: `## Architectural Role`, `## Design Patterns`, `## Domain Concepts`

---

## [0.1.0] — 2026-06-22

### Initial Release

- **DependencyGraph**: In-memory directed graph with JSON persistence, topological sort (Kahn's algorithm), DFS cycle detection, impact analysis, upstream/downstream dependency traversal with configurable depth, risk scoring.
- **ModuleParser**: AST-based Python source parser extracting imports, from-imports, function calls, class/function definitions, async functions, decorators, top-level names, docstrings, and entry-point detection.
- **GraphResolver**: Builds fully connected DependencyGraph from parsed ModuleInfo — creates nodes, resolves import/call edges, computes reverse relationships, detects orphans and entry points.
- **ChangeTracker**: Git diff integration via subprocess — detects changes between refs, unstaged/staged changes, maps changes to graph nodes, falls back gracefully when git is unavailable.
- **ContextBuilder**: Assembles ContextPackage objects from graph and change data — build_for_module, build_for_changes, build_full_context, build_for_modules.
- **ContextPackage**: Canonical JSON schema for AI context — files, dependencies, recent_changes, risk_score, metadata. Serializable with to_dict/from_dict/save/load.
- **ContextFormatter**: Renders ContextPackage as Markdown, JSON, or CLI text summaries.
- **ClaudeTaskGenerator**: Converts ContextPackage into structured Markdown task files with YAML frontmatter for Claude Code consumption.
- **InboxManager**: Manages `.ai/inbox/` → `.ai/executing/` → `.ai/done/` lifecycle with stale task detection and requeue.
- **StateStore**: Persistent key-value store for analysis history, graph cache metadata, and configuration.
- **CLI**: 6 subcommands — `scan`, `run`, `status`, `graph`, `inbox`, `changes` — with comprehensive flags.
- **Examples**: 5-package sample project (auth, payment, notifications, models, utils) demonstrating multi-level dependency chains.

---

## Version History

| Version | Date | Layers | Modules | Lines | Key Addition |
|---------|------|--------|---------|-------|--------------|
| 0.1.0 | 2026-06-22 | Core + Context + Bridges | 12 | ~3,700 | Dependency graph + task generation |
| 0.2.0 | 2026-06-23 | + Semantic + Knowledge | 24 | ~7,000 | Design patterns, roles, domains, similarity |
| 0.3.0 | 2026-06-23 | + Reasoning | 32 | ~9,800 | Architecture reasoning, impact analysis, ADRs |
