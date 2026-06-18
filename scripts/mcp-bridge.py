#!/usr/bin/env python3
"""Minimal MCP bridge server that wraps OpenCode's HTTP API.

Implements the MCP Streamable HTTP transport (JSON-RPC 2.0 over HTTP)
using only Python standard library. No external dependencies.

Tools exposed:
  - delegate_task: Send instructions to the local coding agent
  - read_project_file: Read a file from the project
  - list_project_files: List/search project files
  - get_project_status: Git status and recent changes
  - abort_task: Abort the currently running task
"""

import json
import os
import subprocess
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock
from pathlib import Path

OPENCODE_URL = "http://127.0.0.1:4096"
BRIDGE_PORT = int(os.environ.get("MCP_BRIDGE_PORT", "8443"))
PROJECT_DIR = "/home/agent/projects"

SERVER_INFO = {
    "name": "xl-sandboxed-opencode-bridge",
    "version": "1.0.0",
}

TOOLS = [
    {
        "name": "delegate_task",
        "description": (
            "Send a task to the local coding agent running inside the sandbox. "
            "The agent will execute the instructions using the local LLM and return "
            "a summary of what was done. Uses a persistent session so the agent "
            "retains context across multiple calls."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "instructions": {
                    "type": "string",
                    "description": "Detailed instructions for the coding agent.",
                },
            },
            "required": ["instructions"],
        },
    },
    {
        "name": "read_project_file",
        "description": "Read the contents of a file from the project directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the project root.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_project_files",
        "description": "List files and directories in the project, or search by pattern.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to project root. Defaults to '.'.",
                    "default": ".",
                },
                "pattern": {
                    "type": "string",
                    "description": "Optional search pattern to filter files.",
                },
            },
        },
    },
    {
        "name": "get_project_status",
        "description": "Get the current project status including git state and recent changes.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "abort_task",
        "description": "Abort the currently running task in the local coding agent.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "write_project_file",
        "description": "Write or overwrite a file in the project directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the project root.",
                },
                "content": {
                    "type": "string",
                    "description": "The exact text content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "get_project_diff",
        "description": "Get the current unstaged and staged git changes (git diff).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_project_command",
        "description": "Execute a non-interactive shell command inside the project directory (e.g. running tests, linters, or builds).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "grep_search",
        "description": "Search for a pattern/string across files recursively using ripgrep.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search term or regular expression pattern.",
                },
                "path": {
                    "type": "string",
                    "description": "Optional subdirectory path relative to project root to limit the search. Defaults to '.'",
                    "default": ".",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Optional flag for case-sensitive match. Defaults to false.",
                    "default": false,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "patch_project_file",
        "description": "Replace a unique block of text inside a file with a new block.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the project root.",
                },
                "find_text": {
                    "type": "string",
                    "description": "The exact block of text to replace. Must be unique in the file.",
                },
                "replace_text": {
                    "type": "string",
                    "description": "The new content to replace find_text with.",
                },
            },
            "required": ["path", "find_text", "replace_text"],
        },
    },
    {
        "name": "crystallize_skill",
        "description": "Distill a repeatable workflow from git and logs into a reusable skill Markdown file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The name of the skill to crystallize.",
                },
            },
            "required": ["skill_name"],
        },
    },
    {
        "name": "read_project_log",
        "description": "Read recent lines from log files inside projects/logs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "log_file": {
                    "type": "string",
                    "description": "The log filename (e.g. autonomous.log). Defaults to 'autonomous.log'.",
                    "default": "autonomous.log",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of lines from the end to read. Defaults to 50.",
                    "default": 50,
                },
            },
        },
    },
    {
        "name": "list_skills",
        "description": "List all crystallized skills in the project with descriptions.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class SessionManager:
    def __init__(self) -> None:
        self._session_id: str | None = None
        self._lock = Lock()

    def get_or_create_session(self) -> str:
        with self._lock:
            if self._session_id is not None:
                return self._session_id
            resp = _opencode_request("POST", "/session", {"title": "conductor-session"})
            self._session_id = resp["id"]
            return self._session_id

    @property
    def session_id(self) -> str | None:
        return self._session_id


session_mgr = SessionManager()


def _opencode_request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{OPENCODE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"OpenCode API {method} {path} returned {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to connect to OpenCode API at {url}: {e.reason}")


def _opencode_get(path: str) -> dict:
    return _opencode_request("GET", path)


def _safe_resolve_path(path_str: str) -> Path | None:
    """Safely resolve a path relative to the project directory to prevent traversal."""
    try:
        proj_path = Path(PROJECT_DIR).resolve()
        target_path = (proj_path / path_str).resolve()
        if target_path.is_relative_to(proj_path):
            return target_path
    except Exception:
        pass
    return None


CONDUCTOR_REMINDER = (
    "[SYSTEM REMINDER] You are operating in CONDUCTOR MODE. Follow these rules strictly:\n"
    "1. Work in small, atomic, and incremental changes. Do not rewrite unrelated code.\n"
    "2. Perform self-verification: run formatters, linters, and tests immediately after writing code.\n"
    "3. No hallucinations: double-check existing file contents before writing code, and verify all imports exist.\n"
    "4. Keep your response short and structured: list modified files, test/lint results, and specific failures if any.\n"
    "5. Avoid conversational fluff. Do not explain unrelated concepts.\n"
    "--- USER INSTRUCTION ---\n"
)


def tool_delegate_task(arguments: dict) -> str:
    instructions = arguments.get("instructions", "")
    if not instructions:
        return "Error: instructions cannot be empty."

    # Prepend the system reminder to instructions to keep the local model focused
    reminded_instructions = f"{CONDUCTOR_REMINDER}{instructions}"

    sid = session_mgr.get_or_create_session()

    message_body = {
        "parts": [{"type": "text", "text": reminded_instructions}],
    }

    try:
        resp = _opencode_request("POST", f"/session/{sid}/message", message_body)
    except RuntimeError as e:
        return f"Error communicating with local agent: {e}"

    parts = resp.get("parts", [])
    texts = []
    for part in parts:
        if isinstance(part, dict):
            if part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif "content" in part:
                texts.append(str(part["content"]))
    return "\n".join(texts) if texts else json.dumps(resp, indent=2)


def tool_read_project_file(arguments: dict) -> str:
    path = arguments.get("path", "")
    if not path:
        return "Error: path is required."
    if not _safe_resolve_path(path):
        return "Error: path traversal detected."
    try:
        resp = _opencode_get(f"/file/content?path={urllib.request.quote(path)}")
        return resp.get("content", json.dumps(resp))
    except RuntimeError as e:
        return f"Error: {e}"


def tool_list_project_files(arguments: dict) -> str:
    path = arguments.get("path", ".")
    pattern = arguments.get("pattern")

    if not _safe_resolve_path(path):
        return "Error: path traversal detected."
    try:
        if pattern:
            resp = _opencode_get(f"/find/file?query={urllib.request.quote(pattern)}")
            if isinstance(resp, list):
                return "\n".join(resp) if resp else "No files found."
            return json.dumps(resp, indent=2)
        else:
            resp = _opencode_get(f"/file?path={urllib.request.quote(path)}")
            if isinstance(resp, list):
                lines = []
                for f in resp:
                    name = f.get("name", "") if isinstance(f, dict) else str(f)
                    lines.append(name)
                return "\n".join(lines) if lines else "Empty directory."
            return json.dumps(resp, indent=2)
    except RuntimeError as e:
        return f"Error: {e}"


def tool_get_project_status(arguments: dict) -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, timeout=10,
            cwd=PROJECT_DIR,
        )
        status = result.stdout.strip() or "(clean)"

        log_result = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            capture_output=True, text=True, timeout=10,
            cwd=PROJECT_DIR,
        )
        log = log_result.stdout.strip()

        return f"Git Status:\n{status}\n\nRecent Commits:\n{log}"
    except Exception as e:
        return f"Error getting project status: {e}"


def tool_abort_task(arguments: dict) -> str:
    sid = session_mgr.session_id
    if not sid:
        return "No active session to abort."
    try:
        _opencode_request("POST", f"/session/{sid}/abort")
        return "Task aborted."
    except RuntimeError as e:
        return f"Error aborting: {e}"


def tool_write_project_file(arguments: dict) -> str:
    path = arguments.get("path", "")
    content = arguments.get("content", "")
    if not path:
        return "Error: path is required."
    target_path = _safe_resolve_path(path)
    if not target_path:
        return "Error: path traversal detected."
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def tool_get_project_diff(arguments: dict) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, timeout=15,
            cwd=PROJECT_DIR,
        )
        return result.stdout.strip() or "(no changes)"
    except Exception as e:
        return f"Error getting git diff: {e}"


def tool_run_project_command(arguments: dict) -> str:
    command = arguments.get("command", "")
    if not command:
        return "Error: command is required."
    try:
        result = subprocess.run(
            ["/bin/bash", "-c", command],
            capture_output=True, text=True, timeout=60,
            cwd=PROJECT_DIR,
        )
        output = []
        if result.stdout:
            output.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output.append(f"STDERR:\n{result.stderr}")
        output_str = "\n".join(output).strip() or "(no output)"
        return f"Command exited with code {result.returncode}\n\n{output_str}"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 60 seconds."
    except Exception as e:
        return f"Error executing command: {e}"


def tool_grep_search(arguments: dict) -> str:
    query = arguments.get("query", "")
    if not query:
        return "Error: query is required."
    subpath = arguments.get("path", ".")
    case_sensitive = arguments.get("case_sensitive", False)
    
    target_dir = _safe_resolve_path(subpath)
    if not target_dir:
        return "Error: path traversal detected or invalid path."
    
    cmd = ["rg", "--line-number", "--no-heading"]
    if not case_sensitive:
        cmd.append("-i")
    cmd.extend([query, str(target_dir)])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=PROJECT_DIR)
        output = result.stdout
        if output:
            resolved_proj_dir = str(Path(PROJECT_DIR).resolve()) + "/"
            output = output.replace(resolved_proj_dir, "")
        stderr = result.stderr.strip()
        if result.returncode == 0:
            return output or "No matches found."
        elif result.returncode == 1:
            return "No matches found."
        else:
            return f"Error running ripgrep (code {result.returncode}): {stderr}"
    except subprocess.TimeoutExpired:
        return "Error: ripgrep command timed out."
    except Exception as e:
        return f"Error executing ripgrep: {e}"


def tool_patch_project_file(arguments: dict) -> str:
    path = arguments.get("path", "")
    find_text = arguments.get("find_text", "")
    replace_text = arguments.get("replace_text", "")
    if not path:
        return "Error: path is required."
    
    target_path = _safe_resolve_path(path)
    if not target_path or not target_path.is_file():
        return f"Error: path traversal detected or file does not exist: {path}"
    
    try:
        content = target_path.read_text(encoding="utf-8")
        occurrences = content.count(find_text)
        if occurrences == 0:
            return "Error: find_text not found in the file."
        if occurrences > 1:
            return f"Error: find_text is not unique; found {occurrences} occurrences."
        
        new_content = content.replace(find_text, replace_text)
        target_path.write_text(new_content, encoding="utf-8")
        return f"Successfully patched {path}. Replaced 1 occurrence."
    except Exception as e:
        return f"Error patching file: {e}"


def tool_crystallize_skill(arguments: dict) -> str:
    skill_name = arguments.get("skill_name", "")
    if not skill_name:
        return "Error: skill_name is required."
    
    try:
        result = subprocess.run(
            ["python3", "/home/agent/app/crystallize_skill.py", skill_name],
            capture_output=True, text=True, timeout=150,
            cwd=PROJECT_DIR,
        )
        output = []
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append(result.stderr)
        return "\n".join(output).strip() or f"Skill crystallization exited with code {result.returncode}."
    except Exception as e:
        return f"Error crystallizing skill: {e}"


def tool_read_project_log(arguments: dict) -> str:
    log_file = arguments.get("log_file", "autonomous.log")
    lines_count = arguments.get("lines", 50)
    
    try:
        lines_count = int(lines_count)
        if lines_count <= 0:
            lines_count = 50
    except ValueError:
        lines_count = 50
        
    logs_dir = Path(PROJECT_DIR) / "logs"
    target_path = (logs_dir / log_file).resolve()
    if not target_path.is_relative_to(logs_dir.resolve()):
        return "Error: path traversal detected."
    if not target_path.is_file():
        return f"Error: log file not found: {log_file}"
        
    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            last_lines = lines[-lines_count:]
            return "".join(last_lines)
    except Exception as e:
        return f"Error reading log: {e}"


def tool_list_skills(arguments: dict) -> str:
    try:
        skills_path = Path(PROJECT_DIR) / "skills"
        if not skills_path.exists():
            return "No skills directory found."
        skills = list(skills_path.glob("*.md"))
        if not skills:
            return "No skills crystallized yet."
        lines = []
        for s in skills:
            content = s.read_text(encoding="utf-8")
            desc = "(No description)"
            for line in content.splitlines():
                if line.strip().startswith("## When To Use") or line.strip().startswith("### When To Use"):
                    idx = content.splitlines().index(line)
                    if idx + 1 < len(content.splitlines()):
                        desc = content.splitlines()[idx + 1].strip()
                    break
            lines.append(f"- {s.name}: {desc}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing skills: {e}"


TOOL_HANDLERS = {
    "delegate_task": tool_delegate_task,
    "read_project_file": tool_read_project_file,
    "list_project_files": tool_list_project_files,
    "get_project_status": tool_get_project_status,
    "abort_task": tool_abort_task,
    "write_project_file": tool_write_project_file,
    "get_project_diff": tool_get_project_diff,
    "run_project_command": tool_run_project_command,
    "grep_search": tool_grep_search,
    "patch_project_file": tool_patch_project_file,
    "crystallize_skill": tool_crystallize_skill,
    "read_project_log": tool_read_project_log,
    "list_skills": tool_list_skills,
}


def handle_jsonrpc(request: dict) -> dict | None:
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)

        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }

        try:
            result_text = handler(arguments)
        except Exception as e:
            result_text = f"Tool execution error: {e}"

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": result_text}],
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


class MCPHandler(BaseHTTPRequestHandler):
    def check_csrf(self) -> bool:
        host = self.headers.get("Host", "")
        allowed_hosts = {
            f"localhost:{BRIDGE_PORT}",
            f"127.0.0.1:{BRIDGE_PORT}",
            "localhost",
            "127.0.0.1",
        }
        if host not in allowed_hosts:
            self.send_error(400, "Bad Request: Invalid Host header")
            return False

        origin = self.headers.get("Origin")
        if origin:
            allowed_origins = {
                f"http://localhost:{BRIDGE_PORT}",
                f"http://127.0.0.1:{BRIDGE_PORT}",
            }
            if origin not in allowed_origins:
                self.send_error(403, "Forbidden: Cross-Origin Request Blocked")
                return False
        return True

    def do_POST(self) -> None:
        if not self.check_csrf():
            return

        if self.path != "/mcp":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        response = handle_jsonrpc(request)

        if response is None:
            self.send_response(204)
            self.end_headers()
            return

        response_bytes = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_GET(self) -> None:
        if not self.check_csrf():
            return

        if self.path == "/health":
            body = json.dumps({"healthy": True, "server": SERVER_INFO}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    server = HTTPServer(("0.0.0.0", BRIDGE_PORT), MCPHandler)
    print(f"MCP bridge server listening on port {BRIDGE_PORT}")
    print(f"Connect your AI coding agent to: http://localhost:{BRIDGE_PORT}/mcp")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
