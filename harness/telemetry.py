"""Observability, metrics, and telemetry tracking for agent loops and long tasks."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class TelemetryTracker:
    """Tracks token velocity, reasoning depth, tool usage, and context metrics.

    Persists runtime state to JSON for consumption by dashboards, monitoring hooks,
    and external supervisors.
    """

    def __init__(
        self,
        project_dir: Optional[Path] = None,
        telemetry_file: Optional[Path] = None,
    ) -> None:
        self.project_dir = project_dir or Path(os.environ.get("PROJECTS_ROOT_PATH", "/home/agent/projects"))
        self.telemetry_file = telemetry_file or (self.project_dir / "logs" / "agent_telemetry.json")
        self.telemetry_file.parent.mkdir(parents=True, exist_ok=True)

        self.total_steps: int = 0
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_reasoning_tokens: int = 0
        self.total_duration_seconds: float = 0.0
        self.step_latencies: List[float] = []
        self.tool_calls_counts: Dict[str, int] = {}
        self.tool_errors: int = 0
        self.current_context_tokens: int = 0
        self.max_context_length: int = 131072
        self.milestones: List[Dict[str, Any]] = []
        self.active_session_id: str = "default_session"
        self.last_updated: float = time.time()

    def record_step(
        self,
        step_idx: int,
        elapsed_seconds: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        reasoning_tokens: int = 0,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
        context_stats: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an execution step into the metrics buffer."""
        self.total_steps += 1
        self.total_duration_seconds += max(0.001, elapsed_seconds)
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_reasoning_tokens += reasoning_tokens

        self.step_latencies.append(round(elapsed_seconds, 2))
        if len(self.step_latencies) > 30:
            self.step_latencies = self.step_latencies[-30:]

        if tool_calls:
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name") or "unknown"
                self.tool_calls_counts[fn_name] = self.tool_calls_counts.get(fn_name, 0) + 1

        if error:
            self.tool_errors += 1

        if context_stats:
            self.current_context_tokens = context_stats.get("estimated_tokens", self.current_context_tokens)
            self.max_context_length = context_stats.get("max_context_length", self.max_context_length)

        self.last_updated = time.time()
        self.save_to_disk()

    def record_milestone(self, title: str, status: str, details: str = "") -> None:
        """Update or register milestone in telemetry buffer."""
        for m in self.milestones:
            if m["title"] == title:
                m["status"] = status
                m["details"] = details
                m["updated_at"] = time.time()
                self.save_to_disk()
                return

        self.milestones.append({
            "id": f"m_{len(self.milestones) + 1}",
            "title": title,
            "status": status,
            "details": details,
            "updated_at": time.time(),
        })
        self.save_to_disk()

    @property
    def token_velocity_tps(self) -> float:
        """Calculate token generation velocity (completion tokens per second)."""
        if self.total_duration_seconds <= 0:
            return 0.0
        return round(self.total_completion_tokens / self.total_duration_seconds, 1)

    @property
    def reasoning_ratio(self) -> float:
        """Calculate reasoning token fraction of total completion generation."""
        if self.total_completion_tokens <= 0:
            return 0.0
        return round(self.total_reasoning_tokens / self.total_completion_tokens, 3)

    @property
    def average_latency(self) -> float:
        """Calculate average latency per turn."""
        if self.total_steps <= 0:
            return 0.0
        return round(self.total_duration_seconds / self.total_steps, 2)

    @property
    def context_utilization_pct(self) -> float:
        """Calculate current context window consumption percentage."""
        if self.max_context_length <= 0:
            return 0.0
        return round((self.current_context_tokens / self.max_context_length) * 100, 2)

    def get_summary(self) -> Dict[str, Any]:
        """Return a serializable telemetry summary dictionary."""
        return {
            "active_session_id": self.active_session_id,
            "total_steps": self.total_steps,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_reasoning_tokens": self.total_reasoning_tokens,
            "token_velocity_tps": self.token_velocity_tps,
            "reasoning_ratio": self.reasoning_ratio,
            "average_latency": self.average_latency,
            "step_latencies": self.step_latencies,
            "tool_calls_counts": self.tool_calls_counts,
            "tool_errors": self.tool_errors,
            "current_context_tokens": self.current_context_tokens,
            "max_context_length": self.max_context_length,
            "context_utilization_pct": self.context_utilization_pct,
            "milestones": self.milestones,
            "last_updated": self.last_updated,
        }

    def save_to_disk(self, target_path: Optional[Path] = None) -> Path:
        """Persist current telemetry state to file."""
        out_path = target_path or self.telemetry_file
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(self.get_summary(), f, indent=2)
        except Exception:
            pass
        return out_path

    def load_from_disk(self, target_path: Optional[Path] = None) -> bool:
        """Load telemetry state from file if present."""
        in_path = target_path or self.telemetry_file
        if not in_path.exists():
            return False
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.active_session_id = data.get("active_session_id", self.active_session_id)
            self.total_steps = data.get("total_steps", 0)
            self.total_duration_seconds = data.get("total_duration_seconds", 0.0)
            self.total_prompt_tokens = data.get("total_prompt_tokens", 0)
            self.total_completion_tokens = data.get("total_completion_tokens", 0)
            self.total_reasoning_tokens = data.get("total_reasoning_tokens", 0)
            self.step_latencies = data.get("step_latencies", [])
            self.tool_calls_counts = data.get("tool_calls_counts", {})
            self.tool_errors = data.get("tool_errors", 0)
            self.current_context_tokens = data.get("current_context_tokens", 0)
            self.max_context_length = data.get("max_context_length", self.max_context_length)
            self.milestones = data.get("milestones", [])
            self.last_updated = data.get("last_updated", time.time())
            return True
        except Exception:
            return False
