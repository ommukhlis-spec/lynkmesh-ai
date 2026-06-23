"""
LynkMesh AI — AI orchestration layer connecting code graph intelligence
with Claude Code task execution.

Core flow: scan → analyze → graph → context → task → execute
Semantic flow: graph → patterns → roles → domains → similarity → knowledge
"""

__version__ = "0.3.0"
__author__ = "LynkMesh AI"

from lynkmesh_ai.core.graph import DependencyGraph
from lynkmesh_ai.core.parser import ModuleParser
from lynkmesh_ai.core.resolver import GraphResolver
from lynkmesh_ai.core.change_tracker import ChangeTracker
from lynkmesh_ai.context.builder import ContextBuilder
from lynkmesh_ai.context.schema import ContextPackage
from lynkmesh_ai.bridges.claude_task import ClaudeTaskGenerator
from lynkmesh_ai.bridges.inbox import InboxManager
from lynkmesh_ai.storage.state import StateStore

# Semantic layer
from lynkmesh_ai.semantic.graph import SemanticGraph
from lynkmesh_ai.semantic.patterns import PatternDetector
from lynkmesh_ai.semantic.roles import RoleClassifier, ArchitecturalRole
from lynkmesh_ai.semantic.analyzer import SemanticAnalyzer

# Knowledge layer
from lynkmesh_ai.knowledge.base import KnowledgeBase
from lynkmesh_ai.knowledge.extractor import KnowledgeExtractor

# Bridge layer (agent bus)
from lynkmesh_ai.bridges.task_router import TaskRouter, BridgeTask
from lynkmesh_ai.bridges.claude_bridge import ClaudeBridge
from lynkmesh_ai.bridges.chatgpt_bridge import ChatGPTBridge

# Reasoning layer
from lynkmesh_ai.reasoning.architecture_analyzer import ArchitectureAnalyzer
from lynkmesh_ai.reasoning.impact_analyzer import ImpactAnalyzer
from lynkmesh_ai.reasoning.decision_engine import DecisionEngine
from lynkmesh_ai.reasoning.risk_engine import RiskEngine

__all__ = [
    # Core
    "DependencyGraph",
    "ModuleParser",
    "GraphResolver",
    "ChangeTracker",
    # Context
    "ContextBuilder",
    "ContextPackage",
    # Bridges
    "ClaudeTaskGenerator",
    "InboxManager",
    # Storage
    "StateStore",
    # Semantic
    "SemanticGraph",
    "PatternDetector",
    "RoleClassifier",
    "ArchitecturalRole",
    "SemanticAnalyzer",
    # Knowledge
    "KnowledgeBase",
    "KnowledgeExtractor",
    # Bridge (agent bus)
    "TaskRouter",
    "BridgeTask",
    "ClaudeBridge",
    "ChatGPTBridge",
    # Reasoning
    "ArchitectureAnalyzer",
    "ImpactAnalyzer",
    "DecisionEngine",
    "RiskEngine",
]
