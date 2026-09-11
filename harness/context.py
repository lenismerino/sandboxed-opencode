"""Context window and token budget manager for the agent loop harness."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ContextManager:
    """Manages the conversation context window, token budgets, and history pruning.

    Optimized for reasoning models like Gemma 4 E4B with large context windows (up to 131K)
    and token reservations for reasoning traces and completion budgets.
    """

    def __init__(
        self,
        max_context_length: int = 131072,
        reserved_completion_tokens: int = 8192,
        prune_threshold_tokens: int = 120000,
        preserved_initial_turns: int = 2,
        recent_turns_budget: int = 20,
    ) -> None:
        self.max_context_length = max_context_length
        self.reserved_completion_tokens = reserved_completion_tokens
        self.prune_threshold_tokens = prune_threshold_tokens
        self.preserved_initial_turns = preserved_initial_turns
        self.recent_turns_budget = recent_turns_budget
        self.messages: List[Dict[str, Any]] = []

    def add_message(
        self,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
        reasoning_content: Optional[str] = None,
    ) -> None:
        """Append a message to the context history.

        Args:
            role: 'system', 'user', 'assistant', or 'tool'.
            content: Text payload of the message.
            tool_calls: Optional tool calls issued by the assistant.
            tool_call_id: Tool call ID if responding as 'tool'.
            name: Function/tool name if applicable.
            reasoning_content: Reasoning trace if provided by model.
        """
        msg: Dict[str, Any] = {"role": role, "content": content}
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_call_id is not None:
            msg["tool_call_id"] = tool_call_id
        if name is not None:
            msg["name"] = name
        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content

        self.messages.append(msg)
        self.prune_if_needed()

    def estimate_message_tokens(self, msg: Dict[str, Any]) -> int:
        """Estimate token count of a single message dictionary (~3.8 chars per token)."""
        content_len = len(msg.get("content") or "")
        reasoning_len = len(msg.get("reasoning_content") or "")
        tool_calls_len = len(str(msg.get("tool_calls") or ""))
        total_chars = content_len + reasoning_len + tool_calls_len + 30
        return max(1, total_chars // 4)

    def estimate_total_tokens(self) -> int:
        """Estimate the total token count of all messages in context."""
        return sum(self.estimate_message_tokens(m) for m in self.messages)

    def needs_compaction(self, headroom_threshold_pct: float = 0.20) -> bool:
        """Check if remaining token headroom is below the threshold percentage."""
        stats = self.get_stats()
        return (stats["headroom_tokens"] / max(1, self.max_context_length)) < headroom_threshold_pct

    def _synthesize_compaction_summary(self, messages_slice: List[Dict[str, Any]]) -> str:
        """Synthesize an architectural summary from a slice of messages being compacted."""
        tools_called: List[str] = []
        files_referenced: List[str] = []
        key_actions: List[str] = []
        errors_encountered: List[str] = []

        for msg in messages_slice:
            role = msg.get("role")
            content = msg.get("content") or ""

            # Check tool calls
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                name = fn.get("name")
                if name:
                    tools_called.append(name)
                    # Extract file paths from arguments if present
                    args = fn.get("arguments", "")
                    if "path" in args or "file" in args:
                        for token in args.replace('"', ' ').replace("'", ' ').split():
                            if "/" in token or token.endswith((".py", ".md", ".sh", ".json", ".yml")):
                                files_referenced.append(token.strip(" ,{}"))

            # Check tool errors or test failures
            if role == "tool" and ("Error" in content or "FAIL" in content or "Traceback" in content):
                errors_encountered.append(content[:160].replace("\n", " "))

            # Assistant key conclusions
            if role == "assistant" and len(content) > 30:
                first_line = content.strip().split("\n")[0][:120]
                if first_line and not first_line.startswith("```"):
                    key_actions.append(first_line)

        # Build compact architectural snapshot
        tools_summary = ", ".join(sorted(set(tools_called))) if tools_called else "None"
        files_summary = ", ".join(sorted(set(files_referenced))[:8]) if files_referenced else "None"
        actions_summary = "; ".join(key_actions[:4]) if key_actions else "Exploration and development steps completed."
        errors_summary = f"Handled errors: {errors_encountered[-1]}" if errors_encountered else "No persistent errors."

        return (
            f"[Architectural Context Checkpoint: Compacted {len(messages_slice)} intermediate turns]\n"
            f"- Tools Executed: {tools_summary}\n"
            f"- Working Files: {files_summary}\n"
            f"- Progress & Decisions: {actions_summary}\n"
            f"- Verification Status: {errors_summary}\n"
            f"- Status: Active working state preserved."
        )

    def compact(self, summary: Optional[str] = None) -> Dict[str, Any]:
        """Intelligently compact intermediate turns into an architectural checkpoint.

        Preserves:
        - System prompt (index 0)
        - Initial user task specification (indices up to preserved_initial_turns)
        - The most recent N messages (recent_turns_budget)

        Returns:
            Dictionary with compaction metadata.
        """
        min_messages = self.preserved_initial_turns + self.recent_turns_budget
        if len(self.messages) <= min_messages:
            return {"compacted": False, "reason": "Insufficient messages to compact", "pruned_turns": 0}

        prune_start = self.preserved_initial_turns
        prune_end = len(self.messages) - self.recent_turns_budget
        if prune_end <= prune_start:
            return {"compacted": False, "reason": "No intermediate turns in range", "pruned_turns": 0}

        slice_to_compact = self.messages[prune_start:prune_end]
        compact_text = summary or self._synthesize_compaction_summary(slice_to_compact)

        checkpoint_msg = {
            "role": "system",
            "content": compact_text,
        }

        pruned_count = len(slice_to_compact)
        self.messages = (
            self.messages[:prune_start]
            + [checkpoint_msg]
            + self.messages[prune_end:]
        )

        return {
            "compacted": True,
            "pruned_turns": pruned_count,
            "new_message_count": len(self.messages),
            "estimated_tokens": self.estimate_total_tokens(),
            "summary": compact_text,
        }

    def prune_if_needed(self) -> int:
        """Prune older intermediate turns if estimated tokens exceed prune threshold.

        Uses intelligent compaction rather than dropping messages entirely.

        Returns:
            Number of messages pruned.
        """
        estimated = self.estimate_total_tokens()
        if estimated <= self.prune_threshold_tokens:
            return 0

        res = self.compact()
        return res.get("pruned_turns", 0)

    def get_messages(self) -> List[Dict[str, Any]]:
        """Return the list of messages formatted for OpenAI-compatible API calls.

        Omits internal fields like 'reasoning_content' from the request payload
        unless specifically supported.
        """
        cleaned: List[Dict[str, Any]] = []
        for m in self.messages:
            entry: Dict[str, Any] = {"role": m["role"], "content": m.get("content") or ""}
            if "tool_calls" in m:
                entry["tool_calls"] = m["tool_calls"]
            if "tool_call_id" in m:
                entry["tool_call_id"] = m["tool_call_id"]
            if "name" in m:
                entry["name"] = m["name"]
            cleaned.append(entry)
        return cleaned

    def get_stats(self) -> Dict[str, Any]:
        """Return context budget statistics."""
        current_tokens = self.estimate_total_tokens()
        return {
            "message_count": len(self.messages),
            "estimated_tokens": current_tokens,
            "max_context_length": self.max_context_length,
            "reserved_completion": self.reserved_completion_tokens,
            "headroom_tokens": max(0, self.max_context_length - current_tokens - self.reserved_completion_tokens),
            "utilization_pct": round((current_tokens / self.max_context_length) * 100, 2),
        }

    def export_state(self) -> Dict[str, Any]:
        """Serialize context history and parameters for session checkpointing."""
        return {
            "max_context_length": self.max_context_length,
            "reserved_completion_tokens": self.reserved_completion_tokens,
            "prune_threshold_tokens": self.prune_threshold_tokens,
            "preserved_initial_turns": self.preserved_initial_turns,
            "recent_turns_budget": self.recent_turns_budget,
            "messages": self.messages,
            "stats": self.get_stats(),
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Restore context history and configuration from serialized state."""
        self.max_context_length = state.get("max_context_length", self.max_context_length)
        self.reserved_completion_tokens = state.get("reserved_completion_tokens", self.reserved_completion_tokens)
        self.prune_threshold_tokens = state.get("prune_threshold_tokens", self.prune_threshold_tokens)
        self.preserved_initial_turns = state.get("preserved_initial_turns", self.preserved_initial_turns)
        self.recent_turns_budget = state.get("recent_turns_budget", self.recent_turns_budget)
        self.messages = state.get("messages", [])
