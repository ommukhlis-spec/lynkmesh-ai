# LynkMesh AI Roadmap

## v0.4.0 — Agent Loop

**Goal:** Close the analyze-decide-execute-verify-learn loop.

- [ ] `agents/loop_engine.py` — AgentLoop orchestrator
- [ ] `agents/router.py` — TaskRouter: classify, route, prioritize tasks
- [ ] `agents/memory.py` — AgentMemory: store outcomes, refine confidence, detect recurring patterns
- [ ] `agents/executor.py` — ClaudeCodeExecutor: invoke Claude Code via inbox bridge
- [ ] `agents/verifier.py` — OutcomeVerifier: structural verification of change outcomes
- [ ] CLI: `lynkmesh-ai agent run`, `agent watch`, `agent verify`, `agent status`
- [ ] `--dry-run` flag for safe preview of agent actions

**Design doc:** `docs/AGENT_LOOP_ARCHITECTURE.md`

---

## v0.5.0 — Multi-Language + Live Monitoring

**Goal:** Expand beyond Python and add real-time analysis.

- [ ] `core/parser_js.py` — JavaScript/TypeScript AST parser
- [ ] `core/parser_rs.py` — Rust source parser (basic)
- [ ] Language-agnostic graph edges (cross-language dependencies)
- [ ] `monitor/` subpackage — file watcher for live graph updates
- [ ] `lynkmesh-ai watch --dir .` — continuous monitoring mode
- [ ] Incremental graph updates (only re-parse changed files)
- [ ] CI integration examples (GitHub Actions workflow that comments on PRs)

---

## v1.0.0 — Stable API + Ecosystem

**Goal:** Production stability and community ecosystem.

- [ ] Stable public API for all core types (DependencyGraph, ContextPackage, SemanticGraph)
- [ ] Comprehensive test suite (`tests/` with pytest, >80% coverage target)
- [ ] Plugin architecture for custom analyzers
- [ ] Configuration file support (`.lynkmesh.toml`)
- [ ] Published to PyPI (`pip install lynkmesh-ai`)
- [ ] Documentation site (GitHub Pages or Read the Docs)
- [ ] Community extension registry
- [ ] Performance benchmarks for large codebases (>10,000 modules)

---

## Principles

- **Zero dependencies** — this is non-negotiable. The stdlib-only design is a core differentiator.
- **Backward compatibility** — all serialization formats must remain loadable across versions.
- **Composable flags** — `--semantic` and `--reason` remain opt-in; the base pipeline stays fast.
- **No embedded LLM** — LynkMesh AI orchestrates external agents; it does not embed them.
