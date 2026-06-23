# Agent-Loop Architecture — v0.4.0 Planning

## Current State (v0.3.0)

LynkMesh AI now has three intelligence layers:
- **Core (v0.1)**: Dependency graph, change tracking
- **Semantic + Knowledge (v0.2)**: Design patterns, roles, domains, facts
- **Reasoning (v0.3)**: Architecture assessment, impact analysis, risk, ADRs

The system understands WHAT the code is, WHAT PATTERNS it uses, WHY it's designed that way, and WHAT SHOULD be done. But it cannot yet ACT on that knowledge.

## Agent-Loop Architecture (v0.4.0)

### Core Concept

The agent loop closes the circle: **Analyze → Reason → Decide → Execute → Verify → Learn**

```
┌──────────────────────────────────────────────────────────────┐
│                    AGENT LAYER (v0.4)                         │
│                                                               │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │  Agent   │   │  Agent   │   │  Agent   │   │  Agent   │ │
│  │  Loop    │──▶│  Router  │──▶│  Memory  │──▶│  Verify  │ │
│  │  Engine  │   │          │   │          │   │          │ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘ │
│       │              │               │               │       │
│       ▼              ▼               ▼               ▼       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              EXECUTION BRIDGES                        │   │
│  │                                                       │   │
│  │  • ClaudeCodeExecutor  — invoke claude CLI            │   │
│  │  • TaskOrchestrator    — manage multi-step tasks      │   │
│  │  • FeedbackCollector   — capture execution results    │   │
│  │  • LearningLoop        — update knowledge from outcomes│   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### New Subpackage: `lynkmesh_ai/agents/`

#### `agents/__init__.py`
Re-exports all agent classes.

#### `agents/loop_engine.py` — AgentLoop
```
AgentLoop(graph, semantic_graph, knowledge_base, reasoning_engine)
  ├── run_cycle() → CycleResult
  │   Orchestrates one complete analyze→decide→execute→verify→learn cycle
  ├── analyze_phase() → AnalysisContext
  │   Runs semantic + reasoning analysis on current state
  ├── decide_phase() → ActionPlan
  │   Uses DecisionEngine to produce prioritized action list
  ├── execute_phase() → ExecutionResult
  │   Dispatches tasks to executor bridges
  ├── verify_phase() → VerificationResult
  │   Validates that executed changes had intended effect
  └── learn_phase() → LearningRecord
      Updates KnowledgeBase with outcomes, refines confidence scores
```

#### `agents/router.py` — TaskRouter
```
TaskRouter(knowledge_base)
  ├── route_task(context_package) → ExecutionTarget
  │   Decides WHICH agent/executor should handle a task
  ├── classify_task(context) → TaskType
  │   Categorizes: REFACTOR, FIX, FEATURE, INVESTIGATE, DOCUMENT
  ├── estimate_effort(task) → EffortEstimate
  │   Uses code metrics + historical data
  └── prioritize_tasks(tasks) → List[PrioritizedTask]
      Multi-factor priority: risk, impact, effort, dependency order
```

#### `agents/memory.py` — AgentMemory
```
AgentMemory(knowledge_base, state_store)
  ├── remember(cycle_result) → None
  │   Store execution outcome for future reference
  ├── recall(module_or_pattern) → List[PastDecision]
  │   Retrieve relevant past decisions and outcomes
  ├── refine_confidence(fact_type, predicate) → None
  │   Adjust confidence scores based on execution feedback
  ├── detect_recurring_patterns() → List[RecurringPattern]
  │   Find patterns in past decisions (e.g., "3x singleton → repository refactor")
  └── suggest_next_action() → Optional[ActionRecommendation]
      Proactive suggestion based on historical patterns
```

#### `agents/executor.py` — ClaudeCodeExecutor
```
ClaudeCodeExecutor(inbox_manager, claude_task_generator)
  ├── execute(task_file) → ExecutionResult
  │   Invoke Claude Code with the task file, monitor progress
  ├── execute_batch(tasks) → List[ExecutionResult]
  │   Execute multiple tasks respecting dependency order
  ├── monitor_execution(task_id) → ExecutionStatus
  │   Track task through inbox → executing → done lifecycle
  ├── capture_output(task_id) → str
  │   Collect Claude Code output and any generated artifacts
  └── handle_failure(task_id, error) → RecoveryAction
      Decide: retry, escalate, or mark as blocked
```

#### `agents/verifier.py` — OutcomeVerifier
```
OutcomeVerifier(graph, change_tracker)
  ├── verify_change(module, before_snapshot, after_snapshot) → VerificationResult
  │   Did the change actually resolve the identified issue?
  ├── verify_impact_reduction(module) → bool
  │   Did blast radius decrease after refactoring?
  ├── verify_cycle_removal(cycle) → bool
  │   Was the dependency cycle actually broken?
  ├── verify_test_coverage(module) → CoverageDelta
  │   Did test coverage improve?
  └── verify_architecture_alignment() → AlignmentScore
      Is the codebase closer to the declared architectural style?
```

### Changes to Existing Modules

#### `context/schema.py` — New fields
- `ContextPackage.agent_actions: List[Dict]` — Actions the agent has taken or will take
- `ContextPackage.execution_history: List[Dict]` — Past execution results for this module

#### `bridges/claude_task.py` — New template sections
- Agent instructions section with prioritized action list
- Verification checklist generated from OutcomeVerifier
- Learning context from AgentMemory recall

#### `knowledge/base.py` — New fact types
- `execution_outcome` — What happened when we executed this action?
- `refinement_rule` — Learned rule from past outcomes
- `agent_decision` — Why did the agent choose this action?

#### `cli.py` — New commands
```
lynkmesh-ai agent run          # Run one full agent cycle
lynkmesh-ai agent watch        # Continuous agent loop (watch mode)
lynkmesh-ai agent execute      # Execute a specific task from the inbox
lynkmesh-ai agent verify       # Verify a completed task
lynkmesh-ai agent learn        # Run learning phase on past executions
lynkmesh-ai agent status       # Agent loop status and history
```

### Architecture Decisions for v0.4.0

1. **Agent does NOT replace the CLI** — the CLI becomes an agent control surface. `lynkmesh-ai run` remains the manual mode; `lynkmesh-ai agent run` is the autonomous mode.

2. **Execution is bridged, not embedded** — the AgentLoop invokes Claude Code as an external process via the executor bridge. It does not embed an LLM. This keeps LynkMesh AI zero-dependency and decoupled from any specific AI model.

3. **Learning is feedback-driven** — AgentMemory learns from execution outcomes, not from training data. If a refactoring recommendation led to test failures, the confidence for similar recommendations decreases. If it succeeded, confidence increases.

4. **Verification is structural** — OutcomeVerifier uses the existing graph analysis tools to verify changes. It does not run tests directly (that's Claude Code's job), but it can check structural properties: did the dependency count decrease? Was the cycle broken? Did cohesion improve?

5. **Task files remain the interface** — the bridge between LynkMesh AI and Claude Code remains the `.ai/inbox/task_*.md` file. The agent layer enhances the quality and specificity of these files, and monitors their lifecycle.

### Implementation Sequence

| Step | Module | Depends On |
|------|--------|-----------|
| 1 | `agents/memory.py` | KnowledgeBase, StateStore |
| 2 | `agents/router.py` | SemanticGraph, KnowledgeBase |
| 3 | `agents/executor.py` | InboxManager, ClaudeTaskGenerator |
| 4 | `agents/verifier.py` | DependencyGraph, ChangeTracker |
| 5 | `agents/loop_engine.py` | All above |
| 6 | Schema + builder extensions | ContextPackage |
| 7 | Task template extensions | ClaudeTaskGenerator |
| 8 | CLI agent commands | All above |

### Risk Considerations

- **Autonomous execution safety**: The agent should NEVER execute without explicit opt-in. A `--dry-run` flag should preview actions before execution.
- **Feedback loop stability**: Bad learning from noisy outcomes. Confidence adjustments should use exponential moving average, not binary success/failure.
- **State explosion**: AgentMemory grows unboundedly. Implement LRU eviction for old execution records.
- **Idempotency**: The same agent cycle run twice should produce idempotent results. Task deduplication is essential.
