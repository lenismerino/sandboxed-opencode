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


def tool_delegate_task(arguments: dict) -> str:
    instructions = arguments.get("instructions", "")
    if not instructions:
        return "Error: instructions cannot be empty."

    sid = session_mgr.get_or_create_session()

    message_body = {
        "parts": [{"type": "text", "text": instructions}],
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
    try:
        resp = _opencode_get(f"/file/content?path={urllib.request.quote(path)}")
        return resp.get("content", json.dumps(resp))
    except RuntimeError as e:
        return f"Error: {e}"


def tool_list_project_files(arguments: dict) -> str:
    path = arguments.get("path", ".")
    pattern = arguments.get("pattern")

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
    try:
        target_path = (Path(PROJECT_DIR) / path).resolve()
        if not str(target_path).startswith(str(PROJECT_DIR)):
            return "Error: path traversal detected."
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


TOOL_HANDLERS = {
    "delegate_task": tool_delegate_task,
    "read_project_file": tool_read_project_file,
    "list_project_files": tool_list_project_files,
    "get_project_status": tool_get_project_status,
    "abort_task": tool_abort_task,
    "write_project_file": tool_write_project_file,
    "get_project_diff": tool_get_project_diff,
    "run_project_command": tool_run_project_command,
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
