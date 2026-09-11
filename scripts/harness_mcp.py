#!/usr/bin/env python3
"""Standard Stdio MCP Server providing Harness & Agent tools to OpenCode in make run.

Zero external dependencies (Python standard library only).
Implements Model Context Protocol (JSON-RPC 2.0) over stdin/stdout.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.embeddings import LocalEmbeddingClient, SemanticCodeIndex
from harness.evaluator import TaskEvaluator
from harness.session import SessionManager
from harness.telemetry import TelemetryTracker

PROJECT_DIR = Path(os.environ.get("PROJECTS_ROOT_PATH", "/home/agent/projects"))
if not PROJECT_DIR.exists():
    PROJECT_DIR = REPO_ROOT

session_mgr = SessionManager(project_dir=PROJECT_DIR)
telemetry = TelemetryTracker(project_dir=PROJECT_DIR)
evaluator = TaskEvaluator(project_dir=PROJECT_DIR)

TOOLS_METADATA = [
    {
        "name": "semantic_search",
        "description": (
            "Search the project codebase offline using semantic vector embeddings. "
            "Finds conceptually related functions, classes, and logic even without exact keyword matches."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query describing the logic, behavior, or feature.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of code chunks to return (default: 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "compact_context",
        "description": (
            "Compact conversational context and record an architectural checkpoint to disk. "
            "Call this when sessions get long or before starting a major sub-phase to preserve critical state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Optional architectural summary of completed work, decisions, and current state.",
                },
            },
        },
    },
    {
        "name": "evaluate_codebase",
        "description": (
            "Run automated verification gates (Ruff formatting check, Ruff linter, and Pytest test suite). "
            "Provides immediate structured feedback on syntax, style, typing, and test outcomes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_tests": {
                    "type": "boolean",
                    "description": "Whether to execute the full pytest test suite (default: true).",
                    "default": True,
                },
            },
        },
    },
    {
        "name": "track_milestone",
        "description": "Record or update progress on a project milestone or subtask in the observability dashboard.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Milestone title or phase name.",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "blocked"],
                    "description": "Current status of the milestone.",
                },
                "details": {
                    "type": "string",
                    "description": "Optional details or notes about progress.",
                    "default": "",
                },
            },
            "required": ["title", "status"],
        },
    },
    {
        "name": "get_telemetry",
        "description": "Fetch real-time agent metrics: token velocity (t/s), reasoning ratio, context headroom, and step latencies.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def handle_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    """Execute tool and return string result."""
    if name == "semantic_search":
        query = arguments.get("query", "")
        top_k = int(arguments.get("top_k", 5))

        base_url = os.environ.get("LLM_BASE_URL", "http://host.docker.internal:1234/v1")
        embed_model = os.environ.get("EMBEDDING_MODEL_NAME", "text-embedding-nomic-embed-text-v1.5")
        client = LocalEmbeddingClient(base_url=base_url, model=embed_model)
        index = SemanticCodeIndex(
            project_dir=PROJECT_DIR,
            embedding_client=client,
            db_path=PROJECT_DIR / ".cache" / "semantic_index.db",
        )

        try:
            results = index.query(query, top_k=top_k)
            if not results:
                # Try auto-indexing if empty
                index.index_project()
                results = index.query(query, top_k=top_k)
        except Exception as e:
            return f"Semantic search failed: {e}. Ensure local embedding model is loaded."

        if not results:
            return f"No semantic matches found for '{query}'."

        lines = [f"Found {len(results)} semantic matches for '{query}':"]
        for idx, r in enumerate(results, 1):
            lines.append(f"\n{idx}. {r['file_path']}:{r['start_line']}-{r['end_line']} (Score: {r['score']:.4f})")
            snippet = "\n".join(f"   {l}" for l in r["chunk_text"].split("\n")[:8])
            lines.append(snippet)
        return "\n".join(lines)

    elif name == "compact_context":
        summary = arguments.get("summary", "Manual context compaction checkpoint triggered.")
        checkpoint_dir = PROJECT_DIR / "logs" / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        ts = int(os.environ.get("STEP_TIMESTAMP", 0)) or int(PROJECT_DIR.stat().st_mtime)
        cp_file = checkpoint_dir / f"checkpoint_{ts}.md"
        with open(cp_file, "w", encoding="utf-8") as f:
            f.write(f"# Context Checkpoint\n\n{summary}\n")

        session_mgr.record_milestone("Context Compaction", "completed", f"Checkpoint recorded to {cp_file.name}")
        telemetry.record_milestone("Context Compaction", "completed", f"Checkpoint recorded to {cp_file.name}")
        return f"Context compaction successful. Architectural snapshot preserved in {cp_file}."

    elif name == "evaluate_codebase":
        run_tests = arguments.get("run_tests", True)
        res = evaluator.run_full_evaluation()
        telemetry.record_milestone(
            "Evaluation Gate",
            "completed" if res.all_passed else "blocked",
            f"Pass: {res.all_passed}, Tests: {res.tests_passed}, Lints: {res.lint_passed}",
        )
        return res.to_summary()

    elif name == "track_milestone":
        title = arguments.get("title", "Task Milestone")
        status = arguments.get("status", "in_progress")
        details = arguments.get("details", "")
        session_mgr.record_milestone(title, status, details)
        telemetry.record_milestone(title, status, details)
        return f"Milestone '{title}' updated to '{status}'."

    elif name == "get_telemetry":
        summary = telemetry.get_summary()
        return json.dumps(summary, indent=2)

    return f"Unknown tool: {name}"


def send_response(response: Dict[str, Any]) -> None:
    """Send JSON-RPC response to stdout."""
    payload = json.dumps(response)
    sys.stdout.write(payload + "\n")
    sys.stdout.flush()


def main() -> None:
    """Stdio JSON-RPC loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as err:
            send_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {err}"},
            })
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        # Handle notifications
        if req_id is None:
            continue

        if method == "initialize":
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "sandboxed-harness-mcp",
                        "version": "1.0.0",
                    },
                },
            })

        elif method == "tools/list":
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS_METADATA},
            })

        elif method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                result_text = handle_tool_call(name, arguments)
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                        "isError": False,
                    },
                })
            except Exception as err:
                tb = traceback.format_exc()
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {err}\n{tb}"}],
                        "isError": True,
                    },
                })

        else:
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })


if __name__ == "__main__":
    main()
