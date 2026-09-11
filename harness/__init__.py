"""Evaluation and Execution Harness for sandboxed-opencode.

Provides an agent loop engine, context management, token budgeting,
model profile integration, and automated task evaluation.
"""

from harness.context import ContextManager
from harness.embeddings import LocalEmbeddingClient, SemanticCodeIndex
from harness.evaluator import EvaluationReport, TaskEvaluator
from harness.model_client import ModelClient
from harness.runner import AgentLoopRunner

__all__ = [
    "AgentLoopRunner",
    "ContextManager",
    "EvaluationReport",
    "LocalEmbeddingClient",
    "ModelClient",
    "SemanticCodeIndex",
    "TaskEvaluator",
]
