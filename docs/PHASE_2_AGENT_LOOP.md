# Phase 2 — Agent Loop Engine Design

## Target Architecture

```
                    ┌─────────────────────────┐
                    │   AgentOrchestrator      │
                    │                          │
                    │  run_cycle()             │
                    │  analyze → decide →      │
                    │  dispatch → review →     │
                    │  learn                   │
                    └──────────┬───────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
            ▼                  ▼                  ▼
   ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐
   │   Executor     │ │   Reviewer   │ │   ResultStore    │
   │                │ │              │ │                  │
   │ dispatch()     │ │ review()     │ │ store_result()   │
   │ monitor()      │ │ approve()    │ │ query_history()  │
   │ retry()        │ │ reject()     │ │ get_metrics()    │
   │                │ │ escalate()   │ │                  │
   └───────┬────────┘ └──────┬───────┘ └────────┬─────────┘
           │                 │                   │
           ▼                 ▼                   ▼
   ┌────────────────────────────────────────────────────┐
   │                 ProviderRegistry                    │
   │  claude-code | anthropic | openai | ollama | ...   │
   └────────────────────────────────────────────────────┘
```

## Module: `agents/orchestrator.py`

### AgentOrchestrator

```python
class AgentOrchestrator:
    """
    Central loop engine. Orchestrates the full analyze-decide-execute-review-learn cycle.

    Dependencies:
        - DependencyGraph (what to analyze)
        - SemanticAnalyzer (pattern/role/domain detection)
        - ArchitectureAnalyzer (architecture reasoning)
        - DecisionEngine (action recommendations)
        - ProviderRegistry (who can execute)
        - Executor (dispatch + monitor)
        - Reviewer (approval/rejection)
        - ResultStore (persistence + learning)

    Usage:
        orchestrator = AgentOrchestrator(graph, registry)
        result = orchestrator.run_cycle(module="auth.service")
        # Or in continuous mode:
        orchestrator.watch(interval_seconds=300)
    """

    def __init__(
        self,
        graph: DependencyGraph,
        registry: ProviderRegistry,
        semantic_graph: Optional[SemanticGraph] = None,
        knowledge_base: Optional[KnowledgeBase] = None,
        config: Optional[AgentConfig] = None,
    ): ...

    # ------------------------------------------------------------------
    # Cycle methods
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        module: Optional[str] = None,
        changes: Optional[List[ChangeRecord]] = None,
        auto_approve: bool = False,      # Skip review for low-risk changes
        dry_run: bool = False,           # Analyze + decide only, no execution
    ) -> CycleResult:
        """
        Run one complete agent cycle.

        Phases:
        1. ANALYZE — Run semantic + reasoning analysis on target
        2. DECIDE  — Generate prioritized action plan via DecisionEngine
        3. DISPATCH — Route actions to providers via Executor
        4. REVIEW  — Human or automated review of execution results
        5. LEARN   — Store outcomes, update confidence, refine knowledge
        """
        ...

    def watch(
        self,
        interval_seconds: int = 300,
        auto_approve_threshold: str = "low",  # Auto-approve at or below this risk
    ) -> None:
        """
        Continuous watch mode. Polls for changes, runs cycles automatically.
        Stops on SIGINT or when a cycle returns critical failure.
        """
        ...

    # Phase methods (public for manual orchestration)
    def analyze_phase(self, module: str) -> AnalysisContext: ...
    def decide_phase(self, context: AnalysisContext) -> ActionPlan: ...
    def dispatch_phase(self, plan: ActionPlan) -> DispatchResult: ...
    def review_phase(self, result: DispatchResult) -> ReviewOutcome: ...
    def learn_phase(self, outcome: ReviewOutcome) -> LearningRecord: ...
```

### AgentConfig

```python
@dataclass
class AgentConfig:
    """Configuration for the AgentOrchestrator."""
    auto_approve_risk_levels: Set[str] = field(default_factory=lambda: {"none", "low"})
    max_retries: int = 3
    retry_delay_seconds: int = 60
    review_timeout_hours: int = 24
    continuous_poll_interval: int = 300
    max_concurrent_tasks: int = 1
    result_ttl_days: int = 90
    dry_run: bool = False
```

---

## Module: `agents/executor.py`

### Executor

```python
class Executor:
    """
    Dispatches tasks to registered providers and monitors execution.

    Wraps ProviderRegistry, TaskRouter, and InboxManager to provide
    a unified execution interface.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        router: TaskRouter,
        inbox: InboxManager,
    ): ...

    def dispatch(self, action: ActionRecommendation) -> str:
        """
        Convert an ActionRecommendation into a BridgeTask and submit it
        to the appropriate provider. Returns the task ID.
        """
        ...

    def dispatch_batch(self, actions: List[ActionRecommendation]) -> List[str]:
        """Dispatch multiple actions, respecting dependency order."""
        ...

    def monitor(self, task_id: str, timeout_seconds: int = 3600) -> TaskResult:
        """
        Block until the task completes or times out.
        Polls provider.get_status() at 5-second intervals.
        """
        ...

    def retry(self, task_id: str) -> str:
        """
        Retry a failed task. Creates a new task with the same spec,
        incremented retry count, and exponential backoff.
        """
        ...

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or executing task."""
        ...
```

---

## Module: `agents/reviewer.py`

### Reviewer

```python
class Reviewer:
    """
    Human-in-the-loop review and approval system.

    Every action above a configurable risk threshold must be reviewed
    before execution. Reviewers can approve, reject, or request changes.
    """

    def __init__(
        self,
        result_store: ResultStore,
        auto_approve_risk_levels: Optional[Set[str]] = None,
    ): ...

    def review(self, action: ActionRecommendation, result: TaskResult) -> ReviewOutcome:
        """
        Review an executed action.

        Auto-approves if the risk level is below the threshold and the
        task succeeded. Otherwise, queues for human review.

        Returns a ReviewOutcome (APPROVED, REJECTED, NEEDS_CHANGES, ESCALATED).
        """
        ...

    def approve(self, review_id: str, note: str = "") -> None: ...
    def reject(self, review_id: str, reason: str) -> None: ...
    def request_changes(self, review_id: str, feedback: str) -> None: ...
    def escalate(self, review_id: str, reason: str) -> None: ...

    def pending_reviews(self) -> List[ReviewItem]:
        """List all reviews awaiting human decision."""
        ...

    def review_queue_size(self) -> int: ...
```

### ReviewItem, ReviewOutcome

```python
class ReviewOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    ESCALATED = "escalated"
    AUTO_APPROVED = "auto_approved"

@dataclass
class ReviewItem:
    review_id: str
    action: Dict[str, Any]       # ActionRecommendation serialized
    result: Dict[str, Any]       # TaskResult serialized
    risk_level: str
    status: ReviewOutcome
    reviewer: str = ""           # Who reviewed it (empty = pending)
    feedback: str = ""
    created_at: str
    resolved_at: Optional[str] = None
```

---

## Module: `agents/result_store.py`

### ResultStore

```python
class ResultStore:
    """
    Persistent store for execution results, review outcomes, and learning data.

    Backed by .ai/results/ directory with JSON files.
    Integrates with KnowledgeBase for learned facts.
    """

    def __init__(
        self,
        root_dir: Optional[Path] = None,
        knowledge_base: Optional[KnowledgeBase] = None,
    ): ...

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def store_result(self, task_id: str, result: TaskResult) -> None: ...
    def store_review(self, review: ReviewItem) -> None: ...
    def store_cycle_result(self, result: CycleResult) -> None: ...

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_result(self, task_id: str) -> Optional[TaskResult]: ...
    def get_results_for_module(self, module: str) -> List[TaskResult]: ...
    def get_recent_results(self, count: int = 20) -> List[TaskResult]: ...

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def success_rate(self, module: Optional[str] = None) -> float:
        """Ratio of successful to total tasks."""
        ...

    def mean_time_to_completion(self, module: Optional[str] = None) -> float:
        """Average execution duration in milliseconds."""
        ...

    def most_frequent_failures(self, count: int = 5) -> List[Tuple[str, int]]:
        """Most common error patterns."""
        ...

    # ------------------------------------------------------------------
    # Learning integration
    # ------------------------------------------------------------------

    def feed_knowledge_base(self) -> int:
        """
        Convert execution outcomes into KnowledgeFacts.

        Successful patterns → increased confidence on related facts.
        Failed patterns → decreased confidence, learned_pattern with failure mode.
        Returns the number of facts added/updated.
        """
        ...

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data) -> "ResultStore": ...
    def save(self, path: Path) -> None: ...
    @classmethod
    def load(cls, path: Path) -> "ResultStore": ...
```

---

## Workflow State Machine

```
                    ┌─────────┐
                    │  IDLE   │
                    └────┬────┘
                         │ trigger: module change / manual / schedule
                         ▼
                    ┌─────────┐
                    │ ANALYZE │ ◀────────── SemanticAnalyzer + Reasoning
                    └────┬────┘
                         │ AnalysisContext produced
                         ▼
                    ┌─────────┐
                    │ DECIDE  │ ◀────────── DecisionEngine
                    └────┬────┘
                         │ ActionPlan produced (prioritized list)
                         ▼
                    ┌─────────┐
                    │ DISPATCH│ ◀────────── Executor → Provider
                    └────┬────┘
                         │
                    ┌────┴────┐
                    │         │
                    ▼         ▼
              ┌─────────┐  ┌──────────┐
              │ SUCCESS │  │  FAILED  │
              └────┬────┘  └────┬─────┘
                   │            │
                   ▼            ▼
              ┌─────────┐  ┌──────────┐
              │ REVIEW  │  │  RETRY   │──▶ DISPATCH (if retries remain)
              └────┬────┘  └──────────┘
                   │            │ (no retries left)
        ┌──────────┼──────┐     ▼
        ▼          ▼      ▼  ┌──────────┐
   ┌────────┐ ┌──────┐ ┌──┐ │  LEARN   │
   │APPROVE │ │REJECT│ │ESC│ │ (failure │
   └───┬────┘ └──┬───┘ └─┬┘ │  recorded)│
       │         │       │  └──────────┘
       ▼         ▼       ▼
   ┌─────────────────────────┐
   │        LEARN            │
   │  update confidence      │
   │  store outcome          │
   │  refine knowledge       │
   └────────────┬────────────┘
                │
                ▼
           ┌─────────┐
           │  IDLE   │  (cycle complete)
           └─────────┘
```

### State Transitions

| From | To | Trigger |
|------|----|---------|
| IDLE | ANALYZE | `run_cycle(module)` or `watch()` poll |
| ANALYZE | DECIDE | AnalysisContext ready |
| DECIDE | DISPATCH | ActionPlan non-empty |
| DECIDE | IDLE | ActionPlan empty (nothing to do) |
| DISPATCH | SUCCESS | Task completed with success=True |
| DISPATCH | FAILED | Task completed with success=False |
| SUCCESS | REVIEW | Auto-review (or queue for human) |
| FAILED | RETRY | Retry count < max_retries |
| FAILED | LEARN | Retries exhausted |
| REVIEW | APPROVE → LEARN | Human or auto approved |
| REVIEW | REJECT → LEARN | Human rejected |
| REVIEW | ESCALATE → LEARN | Escalated for manual intervention |
| RETRY | DISPATCH | Wait retry_delay_seconds, then re-dispatch |
| LEARN | IDLE | Knowledge updated, cycle complete |

---

## Approval / Review Loop Design

```
┌─────────────────────────────────────────────────────────────────┐
│                      REVIEW DECISION TREE                       │
│                                                                 │
│  Task completed                                                 │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────┐                                                    │
│  │ Success? │─── No ──▶ Risk level?                             │
│  └────┬────┘                                                    │
│       │ Yes                                          ┌──────────┤
│       ▼                                              ▼          ▼
│  Risk level?                                  low/medium    high/critical
│       │                                           │          │
│  ┌────┴────┐                                      ▼          ▼
│  ▼         ▼                                  AUTO-RETRY   NEEDS REVIEW
│ none/low  medium/high/critical                    │          │
│  │         │                                      │    ┌─────┴─────┐
│  ▼         ▼                                      │    ▼           ▼
│ AUTO-    QUEUE                                     │  APPROVE    REJECT
│ APPROVE  FOR REVIEW                                │    │           │
│  │         │                                       │    │           │
│  ▼         ▼                                       │    ▼           ▼
│ LEARN    Human                                     │  LEARN       LEARN
│          decides                                    │  (positive)  (negative
│          │                                          │   feedback)   feedback)
│     ┌────┴────┐                                     │
│     ▼         ▼                                     │
│  APPROVE    REJECT                                  │
│  (maybe     (maybe                                  │
│   with       with                                   │
│   changes)   reason)                                │
│     │         │                                     │
└─────┴─────────┴─────────────────────────────────────┘
```

### Approval Rules

| Risk Level | Success | Failure |
|-----------|---------|---------|
| `none` | Auto-approve | Auto-retry (1x) |
| `low` | Auto-approve | Queue for review |
| `medium` | Queue for review | Queue for review |
| `high` | Queue for review | Requires review (cannot auto-retry) |
| `critical` | Requires review | Escalate immediately |

---

## Implementation Plan

### Step 1: `agents/result_store.py`
**Depends on:** KnowledgeBase, state.py (pattern reference)
- ResultStore dataclass + JSON persistence
- CRUD for results, reviews, cycle outcomes
- Metrics computation (success rate, MTTC, failure patterns)
- KnowledgeBase feed integration
- **Estimated:** ~250 lines

### Step 2: `agents/reviewer.py`
**Depends on:** ResultStore
- Reviewer class with review queue
- ReviewItem, ReviewOutcome types
- Auto-approval logic based on risk thresholds
- Pending review query
- **Estimated:** ~200 lines

### Step 3: `agents/executor.py`
**Depends on:** ProviderRegistry, TaskRouter, InboxManager, DecisionEngine (for action type)
- Executor class with dispatch/monitor/retry/cancel
- ActionRecommendation → BridgeTask conversion
- Exponential backoff retry logic
- Execution timeout handling
- **Estimated:** ~250 lines

### Step 4: `agents/orchestrator.py`
**Depends on:** All above + SemanticAnalyzer, ArchitectureAnalyzer, DecisionEngine
- AgentOrchestrator with full cycle
- AgentConfig dataclass
- Phase methods (analyze, decide, dispatch, review, learn)
- watch() continuous mode
- dry_run support
- **Estimated:** ~350 lines

### Step 5: CLI + Integration
**Depends on:** All above
- `lynkmesh-ai agent run --module <name> [--dry-run] [--auto-approve]`
- `lynkmesh-ai agent watch [--interval 300]`
- `lynkmesh-ai agent review [--list | --approve | --reject]`
- `lynkmesh-ai agent status`
- Wire into existing `--semantic --reason` pipeline
- **Estimated:** ~200 lines CLI + ~100 lines integration

### Step 6: Tests + Documentation
- Smoke tests for each new module
- Full cycle integration test
- Update README, CHANGELOG, ROADMAP
- **Estimated:** ~300 lines tests + docs

---

## Risk Considerations

| Risk | Mitigation |
|------|-----------|
| Autonomous execution safety | `--dry-run` preview, auto-approve only for low-risk, human review required for high+critical |
| Feedback loop instability | EMA-based confidence adjustment, not binary. ResultStore tracks per-module success rates |
| State explosion in ResultStore | LRU eviction for results older than `result_ttl_days` (default 90) |
| Watch mode resource usage | Polling interval configurable; uses file mtime checks, not busy-wait |
| Provider unavailability | Executor retries with exponential backoff; failed providers logged to KnowledgeBase |
