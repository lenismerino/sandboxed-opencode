"""Agent Loop Runner for executing tasks with model profiles and sandboxed tools."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

from harness.context import ContextManager
from harness.model_client import ModelClient
from tools.registry import ToolRegistry


class AgentLoopRunner:
    """Orchestrates the multi-turn agent loop:

    Prompt -> Reasoning -> Tool Call -> Sandboxed Tool Execution -> Context Update -> Feedback -> Verification.
    """

    def __init__(
        self,
        model_client: ModelClient,
        tool_registry: ToolRegistry,
        profile: Dict[str, Any],
        max_steps: Optional[int] = None,
        on_step_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.model_client = model_client
        self.tool_registry = tool_registry
        self.profile = profile
        harness_cfg = profile.get("harness_profile", {})
        cw_cfg = profile.get("context_window", {})

        self.max_steps = max_steps or harness_cfg.get("max_steps_per_task", 30)
        self.on_step_hook = on_step_hook
        self.context = ContextManager(
            max_context_length=cw_cfg.get("max_context_length", 131072),
            reserved_completion_tokens=cw_cfg.get("reserved_completion_tokens", 8192),
            prune_threshold_tokens=harness_cfg.get("prune_threshold_tokens", 120000),
            preserved_initial_turns=harness_cfg.get("preserved_initial_turns", 2),
            recent_turns_budget=harness_cfg.get("recent_turns_budget", 20),
        )

    def run_task(self, task_instruction: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Execute a coding or engineering task through the autonomous loop.

        Args:
            task_instruction: The user/conductor prompt or task specification.
            system_prompt: Optional custom system prompt override.

        Returns:
            Dictionary with final response, step history, token metrics, and execution status.
        """
        sys_prompt = system_prompt or self.profile.get("system_prompt", "You are an autonomous engineering agent.")
        self.context.add_message("system", sys_prompt)
        self.context.add_message("user", task_instruction)

        tools = self.tool_registry.get_openai_tool_specs()
        steps_history: List[Dict[str, Any]] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_reasoning_tokens = 0
        t_start = time.time()

        for step_idx in range(1, self.max_steps + 1):
            messages = self.context.get_messages()

            try:
                result = self.model_client.complete(messages=messages, tools=tools)
            except Exception as err:
                error_step = {
                    "step": step_idx,
                    "error": str(err),
                    "timestamp": time.time(),
                }
                steps_history.append(error_step)
                return {
                    "status": "error",
                    "error": f"Model completion failed at step {step_idx}: {err}",
                    "steps": steps_history,
                    "duration_seconds": round(time.time() - t_start, 2),
                }

            content = result["content"]
            reasoning = result["reasoning_content"]
            tool_calls = result["tool_calls"]
            usage = result.get("usage", {})

            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
            total_reasoning_tokens += usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)

            step_record: Dict[str, Any] = {
                "step": step_idx,
                "reasoning": reasoning,
                "content": content,
                "tool_calls": tool_calls,
                "elapsed": result["elapsed_seconds"],
                "context_stats": self.context.get_stats(),
            }

            if self.on_step_hook:
                self.on_step_hook(step_record)

            steps_history.append(step_record)

            # If no tool calls, model has concluded its task turn
            if not tool_calls:
                self.context.add_message("assistant", content, reasoning_content=reasoning)
                return {
                    "status": "completed",
                    "final_response": content,
                    "reasoning_trace": reasoning,
                    "steps_count": step_idx,
                    "steps": steps_history,
                    "metrics": {
                        "duration_seconds": round(time.time() - t_start, 2),
                        "total_prompt_tokens": total_prompt_tokens,
                        "total_completion_tokens": total_completion_tokens,
                        "total_reasoning_tokens": total_reasoning_tokens,
                        "final_context_stats": self.context.get_stats(),
                    },
                }

            # Record assistant turn with tool calls
            self.context.add_message(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
                reasoning_content=reasoning,
            )

            # Execute tool calls
            for tc in tool_calls:
                call_id = tc.get("id", f"call_{step_idx}")
                func = tc.get("function", {})
                fn_name = func.get("name", "unknown")
                raw_args = func.get("arguments", "{}")

                try:
                    parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception as parse_err:
                    tool_output = f"Error parsing arguments for tool '{fn_name}': {parse_err}"
                    self.context.add_message(
                        role="tool",
                        content=tool_output,
                        tool_call_id=call_id,
                        name=fn_name,
                    )
                    continue

                tool_output = self.tool_registry.execute(fn_name, parsed_args)
                self.context.add_message(
                    role="tool",
                    content=tool_output,
                    tool_call_id=call_id,
                    name=fn_name,
                )

        # Reached max steps
        return {
            "status": "max_steps_exceeded",
            "final_response": content,
            "steps_count": self.max_steps,
            "steps": steps_history,
            "metrics": {
                "duration_seconds": round(time.time() - t_start, 2),
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_reasoning_tokens": total_reasoning_tokens,
            },
        }
