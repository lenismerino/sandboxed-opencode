"""Standard Tool Registry and Sandboxed Executor for Agent Loops."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class ToolRegistry:
    """Registry of sandbox tools exposed to agent loops and model profiles."""

    def __init__(self, project_dir: str = ".") -> None:
        self.project_dir = Path(project_dir).resolve()
        self._tools: Dict[str, Tuple[Dict[str, Any], Callable[..., str]]] = {}
        self._register_default_tools()

    def _resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path ensuring it stays within project boundaries."""
        target = (self.project_dir / relative_path).resolve()
        try:
            target.relative_to(self.project_dir)
        except ValueError as err:
            raise PermissionError(f"Access denied: path '{relative_path}' is outside project root.") from err
        return target

    def register(self, name: str, schema: Dict[str, Any], handler: Callable[..., str]) -> None:
        """Register a new tool."""
        self._tools[name] = (schema, handler)

    def get_openai_tool_specs(self) -> List[Dict[str, Any]]:
        """Return tool definitions in OpenAI function schema format."""
        return [
            {"type": "function", "function": schema}
            for schema, _ in self._tools.values()
        ]

    def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute a registered tool by name with arguments.

        Args:
            name: Tool function name.
            arguments: Parsed JSON arguments dictionary.

        Returns:
            String output of the tool execution.
        """
        if name not in self._tools:
            return f"Error: Tool '{name}' is not recognized. Available tools: {list(self._tools.keys())}"

        _, handler = self._tools[name]
        try:
            return handler(**arguments)
        except Exception as err:
            return f"Error executing tool '{name}': {err}"

    def _register_default_tools(self) -> None:
        # 1. read_file
        read_schema = {
            "name": "read_file",
            "description": "Read the contents of a text file within the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path."},
                },
                "required": ["path"],
            },
        }

        def _read_file(path: str) -> str:
            target = self._resolve_path(path)
            if not target.is_file():
                return f"Error: File '{path}' does not exist."
            return target.read_text(encoding="utf-8", errors="replace")

        self.register("read_file", read_schema, _read_file)

        # 2. write_file
        write_schema = {
            "name": "write_file",
            "description": "Write or overwrite a file within the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path."},
                    "content": {"type": "string", "description": "Full text content."},
                },
                "required": ["path", "content"],
            },
        }

        def _write_file(path: str, content: str) -> str:
            target = self._resolve_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} characters to {path}."

        self.register("write_file", write_schema, _write_file)

        # 3. patch_file
        patch_schema = {
            "name": "patch_file",
            "description": "Replace a unique target block of text inside a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path."},
                    "find_text": {"type": "string", "description": "Unique text block to replace."},
                    "replace_text": {"type": "string", "description": "Replacement text block."},
                },
                "required": ["path", "find_text", "replace_text"],
            },
        }

        def _patch_file(path: str, find_text: str, replace_text: str) -> str:
            target = self._resolve_path(path)
            if not target.is_file():
                return f"Error: File '{path}' does not exist."
            content = target.read_text(encoding="utf-8")
            count = content.count(find_text)
            if count == 0:
                return f"Error: find_text block was not found in '{path}'."
            if count > 1:
                return f"Error: find_text matches {count} locations in '{path}'. Must match uniquely."
            new_content = content.replace(find_text, replace_text, 1)
            target.write_text(new_content, encoding="utf-8")
            return f"Successfully patched '{path}'."

        self.register("patch_file", patch_schema, _patch_file)

        # 4. list_files
        list_schema = {
            "name": "list_files",
            "description": "List files and subdirectories relative to project root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path.", "default": "."},
                    "pattern": {"type": "string", "description": "Optional glob pattern (e.g. *.py)."},
                },
            },
        }

        def _list_files(path: str = ".", pattern: Optional[str] = None) -> str:
            target = self._resolve_path(path)
            if not target.is_dir():
                return f"Error: Directory '{path}' does not exist."
            entries = []
            glob_pat = pattern or "*"
            for p in sorted(target.glob(glob_pat)):
                rel = p.relative_to(self.project_dir)
                kind = "DIR" if p.is_dir() else "FILE"
                entries.append(f"{kind:<5} {rel}")
            return "\n".join(entries) if entries else "No matching files."

        self.register("list_files", list_schema, _list_files)

        # 5. grep_search
        grep_schema = {
            "name": "grep_search",
            "description": "Search for a pattern across project files using ripgrep or python fallback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search string or regex."},
                    "path": {"type": "string", "description": "Relative directory to search.", "default": "."},
                },
                "required": ["query"],
            },
        }

        def _grep_search(query: str, path: str = ".") -> str:
            target = self._resolve_path(path)
            cmd = ["rg", "-n", "--max-count", "30", query, str(target)]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return res.stdout if res.stdout else "No matches found."
            except FileNotFoundError:
                # Fallback to python walk
                matches = []
                for root, _, files in os.walk(target):
                    for file in files:
                        p = Path(root) / file
                        try:
                            for idx, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                                if query in line:
                                    rel = p.relative_to(self.project_dir)
                                    matches.append(f"{rel}:{idx}:{line}")
                                    if len(matches) >= 30:
                                        break
                        except Exception:
                            continue
                return "\n".join(matches) if matches else "No matches found."

        self.register("grep_search", grep_schema, _grep_search)

        # 6. run_command
        run_schema = {
            "name": "run_command",
            "description": "Run a non-interactive shell command inside the project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."},
                },
                "required": ["command"],
            },
        }

        def _run_command(command: str) -> str:
            # Block forbidden commands
            forbidden = ["rm -rf /", ":(){ :|:& };:", "sudo su", "chmod -R 777 /"]
            for f in forbidden:
                if f in command:
                    return f"Error: Command '{command}' contains forbidden destructive patterns."
            try:
                proc = subprocess.run(
                    command,
                    shell=True,
                    cwd=str(self.project_dir),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                out = proc.stdout
                if proc.stderr:
                    out += f"\n[stderr]\n{proc.stderr}"
                out += f"\n[exit code: {proc.returncode}]"
                return out.strip()
            except subprocess.TimeoutExpired:
                return "Error: Command timed out after 120 seconds."
            except Exception as err:
                return f"Error executing command: {err}"

        self.register("run_command", run_schema, _run_command)

        # 7. semantic_search
        semantic_schema = {
            "name": "semantic_search",
            "description": "Perform semantic similarity search across project source code using local offline embeddings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language or technical concept to search for."},
                    "top_k": {"type": "integer", "description": "Number of top matching snippets to return. Default is 5.", "default": 5},
                },
                "required": ["query"],
            },
        }

        def _semantic_search(query: str, top_k: int = 5) -> str:
            from harness.embeddings import LocalEmbeddingClient, SemanticCodeIndex
            host = os.environ.get("LLM_HOST", "host.docker.internal")
            port = os.environ.get("LLM_PORT", "1234")
            base_url = f"http://{host}:{port}/v1"
            client = LocalEmbeddingClient(base_url=base_url)
            index = SemanticCodeIndex(project_dir=str(self.project_dir), embedding_client=client)

            # Auto-index if database is empty
            with sqlite3.connect(index.db_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                if count == 0:
                    indexed = index.index_project()
                    if indexed == 0:
                        return "No indexable project files found for semantic search."

            results = index.search(query, top_k=top_k)
            if not results:
                return "No semantically relevant code snippets found."
            return "\n\n---\n\n".join(r.format_snippet() for r in results)

        self.register("semantic_search", semantic_schema, _semantic_search)
