"""Token Telemetry & Reasoning Monitoring Hook for Agent Loops."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


class TokenTelemetryHook:
    """Records real-time token utilization, reasoning ratio, and latency metrics."""

    def __init__(self, log_path: Optional[str] = None) -> None:
        self.log_path = Path(log_path or "logs/telemetry.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def on_step_complete(self, step_record: Dict[str, Any]) -> None:
        """Process step record and append structured JSON telemetry entry."""
        step = step_record.get("step", 0)
        elapsed = step_record.get("elapsed", 0.0)
        context_stats = step_record.get("context_stats", {})
        tool_calls = step_record.get("tool_calls", [])

        entry = {
            "timestamp": time.time(),
            "step": step,
            "latency_seconds": elapsed,
            "tools_called": [tc.get("function", {}).get("name") for tc in tool_calls],
            "context_tokens": context_stats.get("estimated_tokens", 0),
            "max_context": context_stats.get("max_context_length", 0),
            "context_utilization_pct": context_stats.get("utilization_pct", 0.0),
        }

        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass
