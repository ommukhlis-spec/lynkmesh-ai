# LynkMesh AI

**AI orchestration layer — from dependency graphs to architecture reasoning.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](requirements.txt)
[![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)](CHANGELOG.md)
[![CI](https://github.com/ommukhlis-spec/lynkmesh-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/ommukhlis-spec/lynkmesh-ai/actions/workflows/ci.yml)

> ⚠️ **Safety Note:** LynkMesh AI is an **experimental AI orchestration framework** designed for development environments. It analyzes code, generates task files, and can invoke external AI agents. **It does NOT execute arbitrary code by default.** All autonomous actions require explicit CLI flags (`--semantic`, `--reason`). Generated task files in `.ai/inbox/` are plain Markdown — they are only executed if you explicitly feed them to an AI agent. Review all generated task files before execution. This tool is not intended for production deployment without additional guardrails.

---

## Architecture

```
                           LynkMesh AI v0.3.0
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    REASONING LAYER (v0.3)                         │  │
│  │                                                                   │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────┐ │  │
│  │  │ Architecture │  │   Impact     │  │  Decision    │  │ Risk  │ │  │
│  │  │  Analyzer    │  │  Analyzer    │  │   Engine     │  │Engine │ │  │
│  │  │              │  │              │  │              │  │       │ │  │
│  │  │ • Style      │  │ • Why risky? │  │ • ADRs       │  │ • 6D   │ │  │
│  │  │ • Layering   │  │ • Blast      │  │ • Actions    │  │  risk  │ │  │
│  │  │ • Coupling   │  │   radius     │  │ • Debt       │  │  score │ │  │
│  │  │ • Cohesion   │  │ • Paths      │  │ • Trade-offs │  │ • Hot- │ │  │
│  │  │ • Missing    │  │ • Principles │  │              │  │  spots │ │  │
│  │  │   Abstract.  │  │              │  │              │  │       │ │  │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──┬────┘ │  │
│  │         └─────────────────┴─────────────────┴──────────────┘      │  │
│  └────────────────────────────┬─────────────────────────────────────┘  │
│                               │ consumes                               │
│  ┌────────────────────────────▼─────────────────────────────────────┐  │
│  │                    SEMANTIC LAYER (v0.2)                          │  │
│  │                                                                   │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────┐ │  │
│  │  │   Pattern    │  │    Role      │  │   Domain     │  │Similar│ │  │
│  │  │  Detector    │  │  Classifier  │  │  Analyzer    │  │ ity   │ │  │
│  │  │              │  │              │  │              │  │       │ │  │
│  │  │ • 10 design  │  │ • 13 roles   │  │ • 50+ domain │  │ • Jac-│ │  │
│  │  │   patterns   │  │ • Naming     │  │   keywords   │  │  card │ │  │
│  │  │ • Heuristic  │  │ • Structure  │  │ • 4 categ.   │  │ • Co- │ │  │
│  │  │ • Evidence   │  │ • Graph pos. │  │ • Docstring  │  │  coup│ │  │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──┬────┘ │  │
│  │         └─────────────────┴─────────────────┴──────────────┘      │  │
│  └────────────────────────────┬─────────────────────────────────────┘  │
│                               │ consumes                               │
│  ┌────────────────────────────▼─────────────────────────────────────┐  │
│  │                      CORE LAYER (v0.1)                            │  │
│  │                                                                   │  │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────────┐  ┌──────────────┐ │  │
│  │  │  Parser  │  │ Resolver  │  │   Change     │  │  Dependency  │ │  │
│  │  │  (AST)   │─▶│ (Graph)   │  │   Tracker    │  │   Graph      │ │  │
│  │  │          │  │           │  │  (git diff)  │  │              │ │  │
│  │  │• imports │  │• imports  │  │              │  │ • topsort    │ │  │
│  │  │• calls   │  │• calls    │  │ • HEAD~1..   │  │ • cycles    │ │  │
│  │  │• classes │  │• reverse  │  │ • unstaged   │  │ • impact    │ │  │
│  │  │• bases   │  │• orphans  │  │ • map to     │  │ • JSON      │ │  │
│  │  │• methods │  │• entries  │  │   graph      │  │   persist   │ │  │
│  │  └──────────┘  └───────────┘  └──────────────┘  └──────────────┘ │  │
│  └────────────────────────────┬─────────────────────────────────────┘  │
│                               │                                       │
│  ┌────────────────────────────▼─────────────────────────────────────┐  │
│  │                     BRIDGES + STORAGE                             │  │
│  │                                                                   │  │
│  │  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐   │  │
│  │  │ Context Builder  │  │ Claude Task  │  │  Inbox Manager   │   │  │
│  │  │                  │  │  Generator   │  │                  │   │  │
│  │  │ • assemble ctx   │  │ • Markdown   │  │ • inbox/         │   │  │
│  │  │ • enrich semant. │  │   templates  │  │ • executing/     │   │  │
│  │  │ • enrich reason. │  │ • YAML FM    │  │ • done/          │   │  │
│  │  └──────────────────┘  └──────────────┘  └──────────────────┘   │  │
│  │                                                                   │  │
│  │  ┌──────────────────┐  ┌──────────────┐                          │  │
│  │  │  State Store     │  │ Knowledge    │                          │  │
│  │  │                  │  │   Base       │                          │  │
│  │  │ • run history    │  │ • 6 fact     │                          │  │
│  │  │ • config         │  │   types      │                          │  │
│  │  │ • graph cache    │  │ • search     │                          │  │
│  │  │                  │  │ • inference  │                          │  │
│  │  └──────────────────┘  └──────────────┘                          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  Pipeline: scan → parse → resolve → analyze → reason → context → task  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Layer Architecture

| Layer | Version | Modules | Responsibility | Answers |
|-------|---------|---------|----------------|---------|
| **Core** | v0.1 | `graph.py`, `parser.py`, `resolver.py`, `change_tracker.py` | Parse code, build dependency graph, track changes | WHAT depends on WHAT? |
| **Semantic** | v0.2 | 6 modules in `semantic/` | Design patterns, architectural roles, domain concepts, structural similarity | WHAT PATTERNS? WHAT ROLE? WHAT DOMAIN? |
| **Knowledge** | v0.2 | 3 modules in `knowledge/` | Structured fact storage, query, inference, Decision Memory | WHAT DO WE KNOW? |
| **Reasoning** | v0.3 | 4 modules in `reasoning/` | Architecture assessment, impact analysis, ADRs, multi-dimensional risk | WHY is it this way? WHAT SHOULD WE DO? |
| **Context** | v0.1–0.3 | `schema.py`, `builder.py`, `formatter.py` | Assemble AI context packages with progressive enrichment | What does the AI need to know? |
| **Bridges** | v0.1–0.3 | `claude_task.py`, `inbox.py` | Generate Claude Code task files, manage task lifecycle | How does this reach the execution engine? |
| **Storage** | v0.1 | `state.py` | Operational state, run history, configuration | What's our operational state? |

## Quick Start

```bash
# Install (zero dependencies — stdlib only)
pip install -e .

# Scan a codebase
lynkmesh-ai scan --dir ./src

# Run the full intelligence pipeline
lynkmesh-ai run --module auth.service --semantic --reason

# Inspect the architecture
lynkmesh-ai reasoning analyze --dir ./src
lynkmesh-ai reasoning risk --module auth.service --dir ./src
lynkmesh-ai semantic role --module auth.service --dir ./src
```

## Key Capabilities

### Dependency Graph (v0.1)
- Directed graph with import/call edges
- Topological sort, cycle detection, impact analysis
- Upstream/downstream traversal with configurable depth
- JSON persistence and caching

### Semantic Intelligence (v0.2)
- **10 design patterns detected**: Singleton, Factory, Repository, Observer, Strategy, Facade, Adapter, Command, Decorator, Template Method
- **13 architectural roles classified**: Controller, Service, Repository, Model, Config, Utility, Interface, Middleware, Adapter, Factory, View, CLI, Unknown
- **50+ domain concepts** across 4 categories: core_domain, supporting, infrastructure, generic
- **4 similarity dimensions**: Shared dependency Jaccard, naming overlap, co-coupling, structural equivalence
- **KnowledgeBase**: Schema-less fact store with typed queries, full-text search, and semantic risk inference

### Architecture Reasoning (v0.3)
- **8 architectural styles recognized**: Layered, Hexagonal, Modular Monolith, Service-Oriented, Microservices, Event-Driven, CQRS, Plugin
- **Multi-dimensional risk**: 6 weighted dimensions with configurable weights
- **Impact analysis**: WHY is this change risky? Blast radius, impact paths (direct, transitive, semantic, architectural), principle impacts
- **Architecture Decision Records (ADRs)**: Full context/rationale/consequences/alternatives in standard format
- **Action recommendations**: 9 action types with priority, effort estimate, and expected impact
- **Technical debt identification**: Architectural, code quality, testing, and documentation debt with remediation steps

### Decision Memory
- **6 KnowledgeFact types**: pattern, role, domain, relationship, architecture_decision, design_constraint, learned_pattern
- Facts are subject-predicate-object with confidence scores, evidence chains, and provenance
- Decision Memory persists across analysis runs via KnowledgeBase serialization

## CLI Reference

| Command | Description |
|---------|-------------|
| `lynkmesh-ai scan` | Scan codebase and build dependency graph |
| `lynkmesh-ai run --module <name> [--semantic] [--reason]` | Full pipeline with progressive enrichment |
| `lynkmesh-ai status` | System status (inbox, graph, history) |
| `lynkmesh-ai graph [--summary\|--module\|--cycles\|--impact\|--top\|--orphans]` | Inspect dependency graph |
| `lynkmesh-ai semantic analyze` | Run full semantic analysis |
| `lynkmesh-ai semantic patterns [--all\|--module]` | Detect design patterns |
| `lynkmesh-ai semantic role --module <name>` | Classify architectural role |
| `lynkmesh-ai semantic similar --module <name>` | Find structurally similar modules |
| `lynkmesh-ai semantic domains` | List domain concepts |
| `lynkmesh-ai knowledge summary` | Knowledge base overview |
| `lynkmesh-ai knowledge query [--type\|--module\|--search]` | Query knowledge facts |
| `lynkmesh-ai reasoning analyze` | Full architecture assessment |
| `lynkmesh-ai reasoning risk --module <name>` | Multi-dimensional risk score |
| `lynkmesh-ai reasoning impact --module <name>` | Change impact with WHY explanation |
| `lynkmesh-ai reasoning decide [--save]` | Generate ADRs and recommendations |
| `lynkmesh-ai inbox [--list\|--pop\|--clean]` | Manage AI task inbox |
| `lynkmesh-ai changes [--base\|--target]` | Detect code changes via git diff |

## Context Package Schema

```json
{
  "module": "auth.service",
  "files": [...],
  "dependencies": [...],
  "recent_changes": [...],
  "risk_score": "medium",
  "semantic_edges": [{"source": "auth.service", "target": "models.user", "relation_type": "inherits"}],
  "design_patterns": [{"pattern": "facade", "module": "utils.validators", "confidence": 0.71}],
  "domain_concepts": [{"concept": "auth", "module": "auth.service"}],
  "architectural_role": "service",
  "reasoning": {
    "architecture_narrative": "This codebase appears to follow a Layered style...",
    "risk": {"overall_level": "high", "overall_score": 0.52, "dimensions": [...]},
    "recommendations": [{"title": "Introduce abstraction for...", "priority": "high"}]
  },
  "metadata": {"generated_at": "...", "schema_version": "1.0"}
}
```

## The `.ai/` Directory

```
.ai/
├── inbox/                # Task files awaiting Claude Code execution
├── executing/            # Tasks currently being processed
├── done/                 # Completed task archive
├── graph.json            # Cached dependency graph
├── semantic_graph.json   # Cached semantic analysis
├── knowledge_base.json   # Persistent knowledge base + Decision Memory
├── state.json            # Operational state and run history
└── context_*.json        # Context package snapshots
```

## Design Principles

### Zero Dependencies
The entire system — all 32 modules across 3 layers — runs on the Python 3.11+ standard library:
`ast`, `subprocess`, `json`, `pathlib`, `dataclasses`, `argparse`, `logging`, `collections`, `re`, `enum`, `hashlib`, `secrets`, `time`, `uuid`, `textwrap`, `shutil`, `tempfile`.

### Clean Layered Architecture
```
reasoning/ ──depends on──▶ semantic/ + knowledge/ ──depends on──▶ core/
                                                                     ▶ bridges/ + context/
                                                                     ▶ storage/
```
No circular dependencies. Each layer adds capability without modifying lower layers. All enrichment is opt-in — the core pipeline runs identically without upper layers.

### Progressive Enrichment
```
lynkmesh-ai run --module auth.service                    # v0.1 baseline
lynkmesh-ai run --module auth.service --semantic          # + semantic context
lynkmesh-ai run --module auth.service --reason            # + reasoning context
lynkmesh-ai run --module auth.service --semantic --reason # full intelligence
```

### Production Readiness
- Logging throughout with configurable verbosity
- Graceful degradation (falls back when data unavailable)
- State persistence with caching (analysis history, graph cache)
- Error handling on every I/O boundary
- Deterministic task file output with strict templates
- Backward-compatible serialization (all new fields have defaults)

---

## Project Stats

| Metric | Value |
|--------|-------|
| Source Files | 32 |
| Total Lines | 9,766 |
| Total Size | 374 KB |
| Layers | 5 (core, semantic, knowledge, reasoning, bridges) |
| CLI Subcommands | 9 |
| Top-Level Exports | 20 |
| Design Patterns Detected | 10 |
| Architectural Roles | 13 |
| Risk Dimensions | 6 |
| Knowledge Fact Types | 6 |
| External Dependencies | 0 |

---

## Security

- **No remote code execution by default.** All analysis happens locally using the Python standard library. No external services are called.
- **No credentials required.** LynkMesh AI does not use API keys, tokens, or authentication of any kind.
- **Generated artifacts are Markdown.** Task files in `.ai/inbox/` are plain text. They cannot execute themselves — they must be explicitly consumed by an external agent.
- **Explicit opt-in for all enrichment.** The `--semantic` and `--reason` flags are required for any analysis beyond basic dependency graphing.
- **Zero runtime dependencies.** The entire codebase uses only the Python standard library, eliminating supply-chain risks.

For security issues, please open a [private vulnerability report](https://github.com/ommukhlis-spec/lynkmesh-ai/security/advisories/new) rather than a public issue.

---

## License

MIT © LynkMesh AI Team
