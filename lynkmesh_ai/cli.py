"""
CLI entry point for LynkMesh AI.

Commands:
    lynkmesh-ai scan [--dir PATH]       Scan codebase and build dependency graph
    lynkmesh-ai run --module NAME       Run full pipeline: graph → context → task
    lynkmesh-ai status                  Show system status (inbox, graph, state)
    lynkmesh-ai graph [--summary|--deps|--cycles|--impact]
    lynkmesh-ai inbox [--list|--pop|--clean]
    lynkmesh-ai changes [--base REF] [--target REF]

Usage:
    lynkmesh-ai run --module auth
    lynkmesh-ai scan --dir ./src
    lynkmesh-ai status
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

from lynkmesh_ai import (
    DependencyGraph,
    ModuleParser,
    GraphResolver,
    ChangeTracker,
    ContextBuilder,
    ContextPackage,
    ClaudeTaskGenerator,
    InboxManager,
    StateStore,
)
from lynkmesh_ai.semantic import (
    SemanticGraph,
    SemanticAnalyzer,
    PatternDetector,
    RoleClassifier,
)
from lynkmesh_ai.knowledge import (
    KnowledgeBase,
    KnowledgeExtractor,
)

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def _safe_print(*args, **kwargs) -> None:
    """Print that handles Windows console encoding gracefully."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # Fall back to ASCII-safe rendering
        safe_args = []
        for a in args:
            if isinstance(a, str):
                safe_args.append(a.encode("ascii", errors="replace").decode("ascii"))
            else:
                safe_args.append(a)
        print(*safe_args, **kwargs)


# ──────────────────────────────────────────────────────────────────────
# Command: scan
# ──────────────────────────────────────────────────────────────────────


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan a directory, build the dependency graph, and persist it."""
    target_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    _safe_print(f"\n[*] Scanning: {target_dir}")

    if not target_dir.exists():
        _safe_print(f"[!] Directory not found: {target_dir}")
        return 1

    t0 = time.perf_counter()

    # Parse -> Resolve -> Save
    parser = ModuleParser(target_dir=target_dir)
    resolver = GraphResolver(parser=parser)
    graph = resolver.build(target_dir)

    elapsed = (time.perf_counter() - t0) * 1000

    # Persist graph
    output_path = Path(args.output) if args.output else target_dir / ".ai" / "graph.json"
    graph.save(output_path)

    # Record in state
    state = StateStore(target_dir / ".ai" / "state.json")
    state.record_analysis(
        directory=str(target_dir),
        node_count=graph.node_count,
        edge_count=graph.edge_count,
        duration_ms=elapsed,
    )
    state.record_graph_build(
        graph_path=str(output_path),
        node_count=graph.node_count,
        edge_count=graph.edge_count,
    )

    _safe_print(graph.summary())
    _safe_print(f"\n[OK] Graph saved to: {output_path}")
    _safe_print(f"[*] Completed in {elapsed:.0f}ms")
    return 0


# ──────────────────────────────────────────────────────────────────────
# Command: run
# ──────────────────────────────────────────────────────────────────────


def cmd_run(args: argparse.Namespace) -> int:
    """
    Run the full LynkMesh AI pipeline:

    1. Load or build the dependency graph
    2. Build a ContextPackage for the target module
    3. Generate a Claude Code task file in .ai/inbox/
    4. Print the output path
    """
    target_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    module_name = args.module
    task_id = args.task_id or None

    print(f"\n🚀 LynkMesh AI — Running pipeline for: {module_name}")
    print(f"   Target directory: {target_dir}")

    # ── Step 1: Load or build graph ──
    graph_path = target_dir / ".ai" / "graph.json"
    if graph_path.exists() and not args.rebuild:
        print(f"\n📊 Loading cached graph from {graph_path}")
        graph = DependencyGraph.load(graph_path)
        print(f"   {graph.node_count} nodes, {graph.edge_count} edges loaded")
    else:
        print(f"\n🔍 Building fresh dependency graph...")
        t0 = time.perf_counter()
        parser = ModuleParser(target_dir=target_dir)
        resolver = GraphResolver(parser=parser)
        graph = resolver.build(target_dir)
        elapsed = (time.perf_counter() - t0) * 1000
        graph.save(graph_path)
        print(f"   Graph built in {elapsed:.0f}ms: {graph.node_count} nodes, {graph.edge_count} edges")

    # Verify module exists
    if not graph.has_node(module_name):
        print(f"\n⚠️  Module '{module_name}' not found in graph.")
        print(f"   Available modules ({graph.node_count}):")
        for node in sorted(graph.iter_nodes(), key=lambda n: n.name):
            print(f"     - {node.name}")
        print(f"\n   Tip: Run 'lynkmesh-ai scan' first to build the graph.")
        return 1

    # ── Step 2: Detect changes ──
    change_tracker = ChangeTracker(target_dir)
    changes = None
    if change_tracker.has_git:
        if args.base_ref or args.target_ref:
            base = args.base_ref or "HEAD~1"
            target = args.target_ref or "HEAD"
            changes = change_tracker.detect_changes(base, target)
            if changes:
                print(f"\n📝 Detected {len(changes)} changes between {base} and {target}")
    else:
        print(f"\n⚠️  No git repository detected — change tracking disabled")

    # ── Step 2.5: Semantic analysis (if --semantic) ──
    sgraph = None
    kb = None
    if getattr(args, "semantic", False):
        print(f"\n🧠 Running semantic analysis...")
        analyzer = SemanticAnalyzer(graph)
        sgraph = analyzer.analyze()
        print(f"   {sgraph.summary().split(chr(10))[0]}")

        extractor = KnowledgeExtractor(sgraph)
        kb = extractor.build_knowledge_base()
        print(f"   KnowledgeBase: {kb.fact_count} facts")

        # Save for future use
        sem_path = target_dir / ".ai" / "semantic_graph.json"
        kb_path = target_dir / ".ai" / "knowledge_base.json"
        sgraph.save(sem_path)
        kb.save(kb_path)
        print(f"   Saved: {sem_path.name}, {kb_path.name}")

    # ── Step 3: Build context ──
    # ── Step 2.6: Architecture reasoning (if --reason) ──
    reasoning_report = None
    if getattr(args, "reason", False):
        print(f"\n🧠 Running architecture reasoning...")
        from lynkmesh_ai.reasoning import (
            ArchitectureAnalyzer, ImpactAnalyzer, DecisionEngine, RiskEngine,
        )
        # Build semantic data if not already built
        if not sgraph:
            analyzer = SemanticAnalyzer(graph)
            sgraph = analyzer.analyze()
            extractor = KnowledgeExtractor(sgraph)
            kb = extractor.build_knowledge_base()

        # Risk assessment
        risk_engine = RiskEngine(graph, sgraph, kb)
        risk = risk_engine.compute_risk(module_name)
        print(f"   Risk: {risk.overall_level.upper()} (score: {risk.overall_score:.2f})")

        # Architecture analysis
        arch_analyzer = ArchitectureAnalyzer(graph, sgraph, kb)
        arch_report = arch_analyzer.analyze()
        print(f"   Architecture: {arch_report.style.value.replace('_', ' ').title()} (confidence: {arch_report.style_confidence:.0%})")

        # Impact analysis (single module)
        impact_analyzer = ImpactAnalyzer(graph, sgraph, kb)
        impact = impact_analyzer.analyze_single_change(module_name)
        print(f"   Blast radius: {impact.blast_radius} modules")

        # Decision engine
        decision_engine = DecisionEngine(graph, sgraph, kb)
        decision_report = decision_engine.analyze(arch_report)
        print(f"   Recommendations: {len(decision_report.recommendations)}")

        # Store in knowledge base and persist
        if kb:
            stored = decision_engine.store_decisions(decision_report, kb)
            kb_path = target_dir / ".ai" / "knowledge_base.json"
            kb.save(kb_path)
            print(f"   Decision facts stored: {stored}")

        # Build combined reasoning report for context
        _impact_dict = impact.to_dict() if hasattr(impact, 'to_dict') else vars(impact)
        _decision_dict = decision_report.to_dict()

        class _ReasoningReport:
            def to_dict(self) -> dict:
                return {
                    'risk_assessment': risk.to_dict(),
                    'impact': _impact_dict,
                    'recommendations': _decision_dict.get('recommendations', []),
                    'architecture_narrative': arch_report.architecture_narrative,
                }

        reasoning_report = _ReasoningReport()

    print(f"\n📦 Building context package for '{module_name}'...")
    builder = ContextBuilder(graph, change_tracker, target_dir,
                             semantic_graph=sgraph, knowledge_base=kb,
                             reasoning_report=reasoning_report)

    if changes and any(module_name in c.module_name for c in changes):
        # Module has changes — build change-aware context
        pkg = builder.build_for_changes()
    else:
        pkg = builder.build_for_module(
            module_name,
            include_dependencies=not args.no_deps,
            include_dependents=not args.no_dependents,
            depth=args.depth,
        )

    print(f"   {pkg.file_count} files, {pkg.dependency_count} dependencies")
    print(f"   Risk: {pkg.risk_score.upper()}")

    # ── Step 4: Generate task file ──
    print(f"\n📝 Generating Claude Code task file...")
    task_gen = ClaudeTaskGenerator(inbox_dir=target_dir / ".ai" / "inbox")
    task_path = task_gen.generate_and_save(
        pkg,
        task_id=task_id,
        instructions=args.instructions or None,
    )

    # ── Step 5: Write context JSON alongside ──
    ctx_path = target_dir / ".ai" / f"context_{module_name.replace('.', '_')}.json"
    pkg.save(ctx_path)

    print(f"\n✅ Task file generated:")
    print(f"   📄  {task_path}")
    print(f"   📄  {ctx_path}")

    # ── Summary ──
    print(f"\n{'─' * 50}")
    print(f"Module:      {module_name}")
    print(f"Risk:        {pkg.risk_score.upper()}")
    print(f"Files:       {pkg.file_count}")
    print(f"Dependencies:{pkg.dependency_count}")
    print(f"Changes:     {len(pkg.recent_changes)}")
    print(f"{'─' * 50}")

    # Inbox status
    inbox = InboxManager(target_dir / ".ai")
    print(f"\n📥 Inbox: {inbox.queue_size()} pending, {inbox.executing_count()} executing, {inbox.done_count()} done")

    return 0


# ──────────────────────────────────────────────────────────────────────
# Command: status
# ──────────────────────────────────────────────────────────────────────


def cmd_status(args: argparse.Namespace) -> int:
    """Display system status: graph health, inbox state, recent runs."""
    target_dir = Path(args.dir).resolve() if args.dir else Path.cwd()

    # Inbox status
    inbox = InboxManager(target_dir / ".ai")
    print(inbox.status_report())

    # Graph status
    graph_path = target_dir / ".ai" / "graph.json"
    if graph_path.exists():
        graph = DependencyGraph.load(graph_path)
        print(graph.summary())
        print()
    else:
        print("📊 No cached graph found. Run 'lynkmesh-ai scan' first.\n")

    # State info
    state = StateStore(target_dir / ".ai" / "state.json")
    last = state.last_analysis()
    if last:
        print(f"📋 Last analysis: {last.get('timestamp', 'N/A')}")
        print(f"   Nodes: {last.get('node_count', '?')} | Edges: {last.get('edge_count', '?')}")
        print(f"   Duration: {last.get('duration_ms', 0):.0f}ms")
        print(f"   Total runs: {state.total_runs()}")
    else:
        print("📋 No analysis history.")

    return 0


# ──────────────────────────────────────────────────────────────────────
# Command: graph
# ──────────────────────────────────────────────────────────────────────


def cmd_graph(args: argparse.Namespace) -> int:
    """Inspect the dependency graph."""
    target_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    graph_path = target_dir / ".ai" / "graph.json"

    if not graph_path.exists():
        print(f"❌ No graph found at {graph_path}")
        print(f"   Run 'lynkmesh-ai scan' first.")
        return 1

    graph = DependencyGraph.load(graph_path)

    if args.summary:
        print(graph.summary())

    elif args.module:
        node = graph.get_node(args.module)
        if not node:
            print(f"❌ Module '{args.module}' not found.")
            return 1

        print(f"\n=== Module: {node.name} ===")
        print(f"  Path:      {node.file_path}")
        print(f"  Package:   {node.package}")
        print(f"  LoC:       {node.lines_of_code}")
        print(f"  Classes:   {', '.join(node.classes) if node.classes else '(none)'}")
        print(f"  Functions: {', '.join(node.functions) if node.functions else '(none)'}")

        deps = graph.immediate_dependencies(node.name)
        print(f"\n  Dependencies ({len(deps)}):")
        for d in sorted(deps):
            print(f"    → {d}")

        dependents = graph.immediate_dependents(node.name)
        print(f"\n  Dependents ({len(dependents)}):")
        for d in sorted(dependents):
            print(f"    ← {d}")

        print(f"\n  Transitively depends on: {len(graph.upstream_dependencies(node.name))} modules")
        print(f"  Transitively depended on by: {len(graph.downstream_dependents(node.name))} modules")

    elif args.cycles:
        cycles = graph.find_cycles()
        if cycles:
            print(f"🔄 {len(cycles)} cycle(s) detected:")
            for i, cycle in enumerate(cycles, 1):
                print(f"  {i}. {' → '.join(cycle)}")
        else:
            print("✅ No cycles detected in the dependency graph.")

    elif args.impact:
        modules = [m.strip() for m in args.impact.split(",")]
        analysis = graph.impact_analysis(modules)
        print(f"\n=== Impact Analysis ===")
        print(f"  Modules: {', '.join(modules)}")
        for mod, affected in analysis.get("affected_dependents", {}).items():
            print(f"\n  {mod}:")
            print(f"    Risk: {analysis['risk_scores'].get(mod, '?')}")
            print(f"    Downstream affected ({len(affected)}):")
            for a in sorted(affected):
                print(f"      - {a}")

    elif args.top:
        try:
            n = int(args.top)
        except ValueError:
            n = 10
        top = resolver_module(graph).find_most_depended_upon(n)
        print(f"\n=== Top {n} Most Depended-Upon Modules ===")
        for name, count in top:
            print(f"  {count:4d}  {name}")

    elif args.orphans:
        orphans = resolver_module(graph).find_orphans()
        if orphans:
            print(f"\n🕸️  {len(orphans)} orphan module(s) (no imports, no dependents):")
            for o in orphans:
                print(f"  - {o.name} ({o.file_path})")
        else:
            print("✅ No orphan modules found.")

    else:
        print(graph.summary())
        print(f"\nUse --module <name> for module details")
        print(f"    --cycles to detect cycles")
        print(f"    --impact <mod1,mod2> for impact analysis")
        print(f"    --top <N> for most depended-upon modules")
        print(f"    --orphans to find orphan modules")

    return 0


def resolver_module(graph: DependencyGraph) -> GraphResolver:
    """Helper to create a resolver from a loaded graph for utility methods."""
    resolver = GraphResolver()
    resolver.graph = graph
    return resolver


# ──────────────────────────────────────────────────────────────────────
# Command: inbox
# ──────────────────────────────────────────────────────────────────────


def cmd_inbox(args: argparse.Namespace) -> int:
    """Manage the AI inbox."""
    target_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    inbox = InboxManager(target_dir / ".ai")

    if args.list:
        all_tasks = inbox.list_all_tasks()
        for state, tasks in all_tasks.items():
            print(f"\n📂 {state.upper()} ({len(tasks)}):")
            for t in tasks:
                meta = inbox.get_task_metadata(t)
                module = meta.get("module", "?")
                risk = meta.get("risk_score", "?")
                print(f"  - {t.name}  [{module}]  risk={risk}")

    elif args.pop:
        task = inbox.pop_next_task()
        if task:
            print(f"▶️  Popped to executing: {task.name}")
        else:
            print("📭 Inbox is empty.")

    elif args.clean:
        count = 0
        stale = inbox.find_stale_tasks(max_age_hours=args.stale_hours)
        if stale:
            requeued = inbox.requeue_stale_tasks(args.stale_hours)
            print(f"🔄 Requeued {len(requeued)} stale task(s) back to inbox.")
        # Clean done tasks older than N days (default 30)
        import time as time_mod
        cutoff = time_mod.time() - (args.clean_days * 86400)
        for task in inbox.list_tasks("done"):
            try:
                if task.stat().st_mtime < cutoff:
                    inbox.delete_task(task)
                    count += 1
            except OSError:
                pass
        print(f"🧹 Cleaned {count} old done task(s).")

    else:
        print(inbox.status_report())

    return 0


# ──────────────────────────────────────────────────────────────────────
# Command: changes
# ──────────────────────────────────────────────────────────────────────


def cmd_changes(args: argparse.Namespace) -> int:
    """Detect and display code changes."""
    target_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    tracker = ChangeTracker(target_dir)

    if not tracker.has_git:
        print("❌ No git repository detected.")
        print("   Change tracking requires a git repository with commits.")
        return 1

    base = args.base or "HEAD~1"
    target = args.target or "HEAD"

    print(f"\n📝 Changes: {base} → {target}")
    changes = tracker.detect_changes(base, target)

    if not changes:
        print("   No changes detected.")
        return 0

    for ch in changes:
        icon = {"added": "➕", "modified": "📝", "deleted": "🗑️ ", "renamed": "🔄"}.get(ch.change_type, "❓")
        print(f"  {icon} [{ch.change_type}] {ch.file_path}")
        if ch.lines_added or ch.lines_removed:
            print(f"       +{ch.lines_added}/-{ch.lines_removed} lines")

    # Also show recent commits
    commits = tracker.get_recent_commits(5)
    if commits:
        print(f"\n📋 Recent commits:")
        for c in commits:
            print(f"  {c['hash'][:8]} {c['message'][:80]}")

    return 0


# ──────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for lynkmesh-ai CLI."""
    parser = argparse.ArgumentParser(
        prog="lynkmesh-ai",
        description="LynkMesh AI — Code intelligence and AI task orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  lynkmesh-ai scan --dir ./src
  lynkmesh-ai run --module auth.service
  lynkmesh-ai run --module auth --task-id fix-auth-bug
  lynkmesh-ai status
  lynkmesh-ai graph --module auth.service
  lynkmesh-ai graph --cycles
  lynkmesh-ai graph --impact auth.service,payment
  lynkmesh-ai changes --base main --target feature/auth
  lynkmesh-ai inbox --list
        """.strip(),
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── scan ──
    scan_parser = subparsers.add_parser("scan", help="Scan codebase and build dependency graph")
    scan_parser.add_argument("--dir", type=str, help="Target directory to scan (default: CWD)")
    scan_parser.add_argument("--output", type=str, help="Output path for graph JSON (default: .ai/graph.json)")
    scan_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # ── run ──
    run_parser = subparsers.add_parser("run", help="Run the full pipeline for a module")
    run_parser.add_argument("--module", "-m", type=str, required=True, help="Target module name (e.g., auth.service)")
    run_parser.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    run_parser.add_argument("--task-id", type=str, help="Custom task ID")
    run_parser.add_argument("--rebuild", action="store_true", help="Force graph rebuild")
    run_parser.add_argument("--no-deps", action="store_true", help="Exclude dependencies from context")
    run_parser.add_argument("--no-dependents", action="store_true", help="Exclude dependents from context")
    run_parser.add_argument("--depth", type=int, default=1, help="Dependency traversal depth (default: 1)")
    run_parser.add_argument("--base-ref", type=str, help="Base git ref for change detection")
    run_parser.add_argument("--target-ref", type=str, help="Target git ref for change detection")
    run_parser.add_argument("--instructions", type=str, help="Custom instructions for the task")
    run_parser.add_argument("--semantic", action="store_true", help="Include semantic analysis in context")
    run_parser.add_argument("--reason", action="store_true", help="Include architecture reasoning in context")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # ── status ──
    status_parser = subparsers.add_parser("status", help="Show system status")
    status_parser.add_argument("--dir", type=str, help="Target directory (default: CWD)")

    # ── graph ──
    graph_parser = subparsers.add_parser("graph", help="Inspect the dependency graph")
    graph_parser.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    graph_parser.add_argument("--summary", "-s", action="store_true", help="Show graph summary")
    graph_parser.add_argument("--module", "-m", type=str, help="Show details for a specific module")
    graph_parser.add_argument("--cycles", action="store_true", help="Detect dependency cycles")
    graph_parser.add_argument("--impact", type=str, help="Run impact analysis for comma-separated modules")
    graph_parser.add_argument("--top", type=str, help="Show top N most depended-on modules")
    graph_parser.add_argument("--orphans", action="store_true", help="Find orphan modules")

    # ── inbox ──
    inbox_parser = subparsers.add_parser("inbox", help="Manage the .ai/ inbox")
    inbox_parser.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    inbox_parser.add_argument("--list", "-l", action="store_true", help="List all tasks")
    inbox_parser.add_argument("--pop", action="store_true", help="Pop next task to executing")
    inbox_parser.add_argument("--clean", action="store_true", help="Clean old/stale tasks")
    inbox_parser.add_argument("--stale-hours", type=int, default=24, help="Max age before task is stale (hours)")
    inbox_parser.add_argument("--clean-days", type=int, default=30, help="Max age of done tasks (days)")

    # ── semantic ──
    semantic_parser = subparsers.add_parser("semantic", help="Semantic code analysis")
    semantic_sub = semantic_parser.add_subparsers(dest="semantic_command", help="Semantic commands")
    # semantic analyze
    sem_analyze = semantic_sub.add_parser("analyze", help="Run full semantic analysis")
    sem_analyze.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    sem_analyze.add_argument("--save", action="store_true", help="Persist semantic graph to .ai/")
    # semantic patterns
    sem_patterns = semantic_sub.add_parser("patterns", help="Detect design patterns")
    sem_patterns.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    sem_patterns.add_argument("--module", "-m", type=str, default=None, help="Filter by module")
    sem_patterns.add_argument("--all", action="store_true", help="Show all detected patterns")
    # semantic role
    sem_role = semantic_sub.add_parser("role", help="Classify architectural role")
    sem_role.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    sem_role.add_argument("--module", "-m", type=str, required=True, help="Module to classify")
    # semantic similar
    sem_similar = semantic_sub.add_parser("similar", help="Find similar modules")
    sem_similar.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    sem_similar.add_argument("--module", "-m", type=str, required=True, help="Reference module")
    sem_similar.add_argument("--top", type=int, default=5, help="Number of results (default: 5)")
    # semantic domains
    sem_domains = semantic_sub.add_parser("domains", help="List domain concepts")
    sem_domains.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    sem_domains.add_argument("--module", "-m", type=str, default=None, help="Filter by module")

    # ── knowledge ──
    knowledge_parser = subparsers.add_parser("knowledge", help="Knowledge base operations")
    knowledge_sub = knowledge_parser.add_subparsers(dest="knowledge_command", help="Knowledge commands")
    # knowledge build
    kb_build = knowledge_sub.add_parser("build", help="Build knowledge base from analysis")
    kb_build.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    # knowledge query
    kb_query = knowledge_sub.add_parser("query", help="Query knowledge base facts")
    kb_query.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    kb_query.add_argument("--type", "-t", type=str, help="Filter by fact type")
    kb_query.add_argument("--module", "-m", type=str, help="Filter by module")
    kb_query.add_argument("--predicate", "-p", type=str, help="Filter by predicate")
    kb_query.add_argument("--search", type=str, help="Full-text search across facts")
    # knowledge summary
    kb_summary = knowledge_sub.add_parser("summary", help="Knowledge base summary")
    kb_summary.add_argument("--dir", type=str, help="Target directory (default: CWD)")

    # ── reasoning ──
    reasoning_parser = subparsers.add_parser("reasoning", help="Architecture reasoning and decision support")
    reasoning_sub = reasoning_parser.add_subparsers(dest="reasoning_command", help="Reasoning commands")
    # reasoning analyze
    reason_analyze = reasoning_sub.add_parser("analyze", help="Run full architecture reasoning")
    reason_analyze.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    reason_analyze.add_argument("--save", action="store_true", help="Store decisions in knowledge base")
    # reasoning risk
    reason_risk = reasoning_sub.add_parser("risk", help="Assess risk for a module")
    reason_risk.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    reason_risk.add_argument("--module", "-m", type=str, required=True, help="Module to assess")
    # reasoning impact
    reason_impact = reasoning_sub.add_parser("impact", help="Analyze impact of changes")
    reason_impact.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    reason_impact.add_argument("--module", "-m", type=str, required=True, help="Module to analyze impact for")
    # reasoning decide
    reason_decide = reasoning_sub.add_parser("decide", help="Generate architecture decisions and recommendations")
    reason_decide.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    reason_decide.add_argument("--save", action="store_true", help="Store decisions in knowledge base")

    # ── changes ──
    changes_parser = subparsers.add_parser("changes", help="Detect and display code changes")
    changes_parser.add_argument("--dir", type=str, help="Target directory (default: CWD)")
    changes_parser.add_argument("--base", type=str, help="Base git ref (default: HEAD~1)")
    changes_parser.add_argument("--target", type=str, help="Target git ref (default: HEAD)")

    return parser


# ──────────────────────────────────────────────────────────────────────
# Helper: load or build semantic analysis
# ──────────────────────────────────────────────────────────────────────


def _load_or_build_semantic(target_dir: Path) -> tuple:
    """Load cached or build fresh SemanticGraph and KnowledgeBase.

    Returns (SemanticGraph, KnowledgeBase) or (None, None) on failure.
    """
    graph_path = target_dir / ".ai" / "graph.json"
    sem_path = target_dir / ".ai" / "semantic_graph.json"
    kb_path = target_dir / ".ai" / "knowledge_base.json"

    if not graph_path.exists():
        _safe_print("[!] No dependency graph found. Run 'lynkmesh-ai scan' first.")
        return None, None

    graph = DependencyGraph.load(graph_path)

    # Try loading cached semantic data
    if sem_path.exists() and kb_path.exists():
        _safe_print("[*] Loading cached semantic analysis...")
        sgraph = SemanticGraph.load(sem_path)
        kb = KnowledgeBase.load(kb_path)
        return sgraph, kb

    # Build fresh
    _safe_print("[*] Running semantic analysis (this may take a moment)...")
    analyzer = SemanticAnalyzer(graph)
    sgraph = analyzer.analyze()
    extractor = KnowledgeExtractor(sgraph)
    kb = extractor.build_knowledge_base()

    sem_path.parent.mkdir(parents=True, exist_ok=True)
    sgraph.save(sem_path)
    kb.save(kb_path)
    _safe_print(f"[OK] Semantic analysis saved to {sem_path.name}, {kb_path.name}")

    return sgraph, kb


# ──────────────────────────────────────────────────────────────────────
# Command: semantic
# ──────────────────────────────────────────────────────────────────────


def cmd_semantic(args: argparse.Namespace) -> int:
    """Semantic code analysis subcommands."""
    target_dir = Path(args.dir).resolve() if args.dir else Path.cwd()

    if args.semantic_command == "analyze":
        return _semantic_analyze(target_dir, args)
    elif args.semantic_command == "patterns":
        return _semantic_patterns(target_dir, args)
    elif args.semantic_command == "role":
        return _semantic_role(target_dir, args)
    elif args.semantic_command == "similar":
        return _semantic_similar(target_dir, args)
    elif args.semantic_command == "domains":
        return _semantic_domains(target_dir, args)
    else:
        _safe_print("Usage: lynkmesh-ai semantic {analyze,patterns,role,similar,domains}")
        return 1


def _semantic_analyze(target_dir: Path, args: argparse.Namespace) -> int:
    """Run full semantic analysis and optionally save."""
    sgraph, kb = _load_or_build_semantic(target_dir)
    if not sgraph:
        return 1
    _safe_print(sgraph.summary())
    _safe_print(kb.summary())
    return 0


def _semantic_patterns(target_dir: Path, args: argparse.Namespace) -> int:
    """List design patterns."""
    sgraph, _ = _load_or_build_semantic(target_dir)
    if not sgraph:
        return 1

    if args.module:
        patterns = sgraph.get_patterns(args.module)
        if patterns:
            _safe_print(f"\n=== Patterns in {args.module} ===")
            for p in patterns:
                _safe_print(f"  [{p.pattern}] class={p.class_name} confidence={p.confidence:.0%}")
                for e in p.evidence:
                    _safe_print(f"    - {e}")
        else:
            _safe_print(f"No patterns detected in {args.module}")
    elif args.all:
        all_pats = sgraph.get_all_patterns()
        if all_pats:
            _safe_print(f"\n=== All Design Patterns ({sum(len(v) for v in all_pats.values())} total) ===")
            for mod, pats in sorted(all_pats.items()):
                for p in pats:
                    _safe_print(f"  {mod}: [{p.pattern}] class={p.class_name} (conf={p.confidence:.0%})")
        else:
            _safe_print("No patterns detected in any module.")
    else:
        # Summary by pattern type
        types = sgraph.list_all_pattern_types()
        if types:
            _safe_print("\n=== Pattern Types Detected ===")
            for t in sorted(types):
                matches = sgraph.get_patterns_by_type(t)
                _safe_print(f"  {t}: {sum(len(v) for v in matches.values())} occurrence(s)")
            _safe_print("\nUse --all to see details or --module <name> for a specific module.")
        else:
            _safe_print("No patterns detected.")
    return 0


def _semantic_role(target_dir: Path, args: argparse.Namespace) -> int:
    """Classify architectural role for a module."""
    sgraph, _ = _load_or_build_semantic(target_dir)
    if not sgraph:
        return 1

    role = sgraph.get_role(args.module)
    if not role:
        _safe_print(f"No role classification for '{args.module}'. Run semantic analyze first.")
        return 1

    _safe_print(f"\n=== Architectural Role: {args.module} ===")
    _safe_print(f"  Role:       {role.role}")
    _safe_print(f"  Confidence: {role.confidence:.0%}")
    if role.evidence:
        _safe_print(f"  Evidence:")
        for e in role.evidence:
            _safe_print(f"    - {e}")

    # Also show distribution
    roles = sgraph.get_all_roles()
    from collections import Counter
    dist = Counter(r.role for r in roles.values())
    _safe_print(f"\n  Role distribution across codebase:")
    for r, c in dist.most_common():
        _safe_print(f"    {r}: {c}")
    return 0


def _semantic_similar(target_dir: Path, args: argparse.Namespace) -> int:
    """Find modules similar to a given module."""
    sgraph, _ = _load_or_build_semantic(target_dir)
    if not sgraph:
        return 1

    similar = sgraph.find_similar_modules(args.module, top_n=args.top)
    if similar:
        _safe_print(f"\n=== Modules Similar to '{args.module}' ===")
        for s in similar:
            target = s.module_a if s.module_a != args.module else s.module_b
            _safe_print(f"  {target:40s} score={s.score:.3f}  ({s.basis})")
    else:
        _safe_print(f"No similar modules found for '{args.module}'.")
    return 0


def _semantic_domains(target_dir: Path, args: argparse.Namespace) -> int:
    """List domain concepts."""
    sgraph, _ = _load_or_build_semantic(target_dir)
    if not sgraph:
        return 1

    if args.module:
        concepts = sgraph.get_domain_concepts(args.module)
        if concepts:
            _safe_print(f"\n=== Domain Concepts: {args.module} ===")
            for c in concepts:
                _safe_print(f"  {c.concept} [{c.category}] (source: {c.source})")
        else:
            _safe_print(f"No domain concepts found for '{args.module}'.")
    else:
        domains = sgraph.get_unique_domains()
        if domains:
            _safe_print(f"\n=== All Domain Concepts ({len(domains)}) ===")
            cat_map = sgraph.get_domain_category_map()
            for cat, concepts in sorted(cat_map.items()):
                _safe_print(f"  [{cat}]: {', '.join(concepts)}")
        else:
            _safe_print("No domain concepts extracted.")
    return 0


# ──────────────────────────────────────────────────────────────────────
# Command: knowledge
# ──────────────────────────────────────────────────────────────────────


def cmd_knowledge(args: argparse.Namespace) -> int:
    """Knowledge base operations."""
    target_dir = Path(args.dir).resolve() if args.dir else Path.cwd()

    if args.knowledge_command == "build":
        return _knowledge_build(target_dir, args)
    elif args.knowledge_command == "query":
        return _knowledge_query(target_dir, args)
    elif args.knowledge_command == "summary":
        return _knowledge_summary(target_dir, args)
    else:
        _safe_print("Usage: lynkmesh-ai knowledge {build,query,summary}")
        return 1


def _knowledge_build(target_dir: Path, args: argparse.Namespace) -> int:
    """Build knowledge base from semantic analysis."""
    _, kb = _load_or_build_semantic(target_dir)
    if not kb:
        return 1
    _safe_print(kb.summary())
    return 0


def _knowledge_query(target_dir: Path, args: argparse.Namespace) -> int:
    """Query knowledge base facts."""
    _, kb = _load_or_build_semantic(target_dir)
    if not kb:
        return 1

    if args.search:
        results = kb.search(args.search)
    else:
        results = kb.query(
            fact_type=args.type,
            subject=args.module,
            predicate=args.predicate,
        )

    if results:
        _safe_print(f"\n=== Knowledge Query Results ({len(results)} facts) ===")
        for f in results:
            _safe_print(f"  {f.subject:30s} --[{f.predicate}]--> {f.object_value} "
                        f"(conf={f.confidence:.0%}, type={f.fact_type})")
    else:
        _safe_print("No facts matched your query.")
    return 0


def _knowledge_summary(target_dir: Path, args: argparse.Namespace) -> int:
    """Show knowledge base summary."""
    _, kb = _load_or_build_semantic(target_dir)
    if not kb:
        return 1
    _safe_print(kb.summary())
    return 0


# ──────────────────────────────────────────────────────────────────────
# Command: reasoning
# ──────────────────────────────────────────────────────────────────────


def cmd_reasoning(args: argparse.Namespace) -> int:
    """Architecture reasoning subcommands."""
    target_dir = Path(args.dir).resolve() if args.dir else Path.cwd()

    if args.reasoning_command == "analyze":
        return _reasoning_analyze(target_dir, args)
    elif args.reasoning_command == "risk":
        return _reasoning_risk(target_dir, args)
    elif args.reasoning_command == "impact":
        return _reasoning_impact(target_dir, args)
    elif args.reasoning_command == "decide":
        return _reasoning_decide(target_dir, args)
    else:
        _safe_print("Usage: lynkmesh-ai reasoning {analyze,risk,impact,decide}")
        return 1


def _reasoning_analyze(target_dir: Path, args: argparse.Namespace) -> int:
    """Run full architecture reasoning."""
    graph_path = target_dir / ".ai" / "graph.json"
    if not graph_path.exists():
        _safe_print("[!] No graph found. Run 'lynkmesh-ai scan' first.")
        return 1

    graph = DependencyGraph.load(graph_path)

    # Load semantic data
    sgraph, kb = _load_or_build_semantic(target_dir)
    if not sgraph:
        _safe_print("[!] Semantic analysis required. Running now...")
        from lynkmesh_ai.semantic import SemanticAnalyzer
        from lynkmesh_ai.knowledge import KnowledgeExtractor
        analyzer = SemanticAnalyzer(graph)
        sgraph = analyzer.analyze()
        extractor = KnowledgeExtractor(sgraph)
        kb = extractor.build_knowledge_base()

    # Run architecture analysis
    from lynkmesh_ai.reasoning import ArchitectureAnalyzer
    arch_analyzer = ArchitectureAnalyzer(graph, sgraph, kb)
    report = arch_analyzer.analyze()

    _safe_print("")
    _safe_print(report.architecture_narrative)
    _safe_print("")

    if report.layering_violations:
        _safe_print(f"Layering Violations: {len(report.layering_violations)}")
        for v in report.layering_violations[:5]:
            _safe_print(f"  [{v.severity}] {v.source} -> {v.target}")

    if report.coupling_hotspots:
        _safe_print(f"\nCoupling Hotspots:")
        for h in report.coupling_hotspots[:5]:
            stable = "STABLE" if h.is_stable else "UNSTABLE"
            _safe_print(f"  {h.module}: fan-in={h.fan_in}, fan-out={h.fan_out}, instability={h.instability:.2f} [{stable}]")

    if report.missing_abstractions:
        _safe_print(f"\nMissing Abstractions: {len(report.missing_abstractions)}")
        for m in report.missing_abstractions[:3]:
            _safe_print(f"  {m.module}: {m.reason[:80]}...")

    if report.principle_violations:
        _safe_print(f"\nPrinciple Violations:")
        for v in report.principle_violations:
            _safe_print(f"  - {v}")

    _safe_print(f"\nStrengths:")
    for s in report.strengths:
        _safe_print(f"  + {s}")
    _safe_print(f"\nWeaknesses:")
    for w in report.weaknesses:
        _safe_print(f"  - {w}")

    return 0


def _reasoning_risk(target_dir: Path, args: argparse.Namespace) -> int:
    """Assess risk for a specific module."""
    graph_path = target_dir / ".ai" / "graph.json"
    if not graph_path.exists():
        _safe_print("[!] No graph found. Run 'lynkmesh-ai scan' first.")
        return 1

    graph = DependencyGraph.load(graph_path)
    sgraph, kb = _load_or_build_semantic(target_dir)

    from lynkmesh_ai.reasoning import RiskEngine
    engine = RiskEngine(graph, sgraph, kb)
    risk = engine.compute_risk(args.module)

    _safe_print(f"\n=== Risk Assessment: {args.module} ===")
    _safe_print(f"Overall: {risk.overall_level.upper()} (score: {risk.overall_score:.2f})")
    _safe_print("")
    _safe_print("Dimensions:")
    for d in risk.dimensions:
        bar = "▓" * int(d.score * 20) + "░" * (20 - int(d.score * 20))
        _safe_print(f"  {d.name:30s} [{bar}] {d.score:.2f}")

    _safe_print(f"\n{risk.explanation}")

    return 0


def _reasoning_impact(target_dir: Path, args: argparse.Namespace) -> int:
    """Analyze impact for a specific module."""
    graph_path = target_dir / ".ai" / "graph.json"
    if not graph_path.exists():
        _safe_print("[!] No graph found. Run 'lynkmesh-ai scan' first.")
        return 1

    graph = DependencyGraph.load(graph_path)
    sgraph, kb = _load_or_build_semantic(target_dir)

    from lynkmesh_ai.reasoning import ImpactAnalyzer
    analyzer = ImpactAnalyzer(graph, sgraph, kb)
    impact = analyzer.analyze_single_change(args.module)

    _safe_print(f"\n=== Impact Analysis: {args.module} ===")
    _safe_print(f"Risk Level: {impact.risk_level.upper()}")
    _safe_print(f"Blast Radius: {impact.blast_radius} module(s)")
    _safe_print(f"Affected Roles: {', '.join(impact.affected_roles) if impact.affected_roles else 'none'}")
    _safe_print(f"\n{impact.explanation}")

    if impact.impact_paths:
        _safe_print(f"\nImpact Paths:")
        for p in impact.impact_paths[:5]:
            _safe_print(f"  [{p.risk_level}] {' -> '.join(p.path)} ({p.propagation_type})")

    if impact.principle_impacts:
        _safe_print(f"\nPrinciple Impact:")
        for p in impact.principle_impacts:
            _safe_print(f"  - {p}")

    return 0


def _reasoning_decide(target_dir: Path, args: argparse.Namespace) -> int:
    """Generate architecture decisions and recommendations."""
    graph_path = target_dir / ".ai" / "graph.json"
    if not graph_path.exists():
        _safe_print("[!] No graph found. Run 'lynkmesh-ai scan' first.")
        return 1

    graph = DependencyGraph.load(graph_path)
    sgraph, kb = _load_or_build_semantic(target_dir)

    from lynkmesh_ai.reasoning import ArchitectureAnalyzer, DecisionEngine
    arch_analyzer = ArchitectureAnalyzer(graph, sgraph, kb)
    arch_report = arch_analyzer.analyze()

    decision_engine = DecisionEngine(graph, sgraph, kb)
    report = decision_engine.analyze(arch_report)

    _safe_print(report.summary)
    _safe_print("")

    if report.recommendations:
        _safe_print(f"=== Recommendations ({len(report.recommendations)}) ===")
        for r in report.recommendations[:10]:
            _safe_print(f"  [{r.priority.upper()}] {r.title}")
            _safe_print(f"    Action: {r.action_type.value}")
            _safe_print(f"    Effort: {r.effort_estimate}")
            _safe_print(f"    {r.rationale[:120]}...")
            _safe_print("")

    if report.adrs:
        _safe_print(f"=== Architecture Decision Records ({len(report.adrs)}) ===")
        for adr in report.adrs:
            _safe_print(f"  {adr.decision_id}: {adr.title}")
            _safe_print(f"    Status: {adr.status.value}")

    if report.technical_debt:
        _safe_print(f"\n=== Technical Debt ({len(report.technical_debt)}) ===")
        for d in report.technical_debt[:5]:
            _safe_print(f"  [{d.priority}] {d.module}: {d.description[:100]}")

    # Store in knowledge base
    if args.save and kb:
        stored = decision_engine.store_decisions(report, kb)
        kb_path = target_dir / ".ai" / "knowledge_base.json"
        kb.save(kb_path)
        _safe_print(f"\n[OK] {stored} decision facts stored in knowledge base")

    return 0


def main(argv: Optional[list] = None) -> int:
    """Main CLI entry point. Returns exit code."""
    # Force UTF-8 encoding on Windows consoles
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(verbose=getattr(args, "verbose", False))

    if args.command == "scan":
        return cmd_scan(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "graph":
        return cmd_graph(args)
    elif args.command == "inbox":
        return cmd_inbox(args)
    elif args.command == "changes":
        return cmd_changes(args)
    elif args.command == "semantic":
        return cmd_semantic(args)
    elif args.command == "knowledge":
        return cmd_knowledge(args)
    elif args.command == "reasoning":
        return cmd_reasoning(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
