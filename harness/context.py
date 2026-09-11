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

    def prune_if_needed(self) -> int:
        """Prune older intermediate turns if estimated tokens exceed prune threshold.

        Preserves:
        - System prompt (index 0)
        - Initial user task specification (indices up to preserved_initial_turns)
        - The most recent N messages (recent_turns_budget)

        Returns:
            Number of messages pruned.
        """
        estimated = self.estimate_total_tokens()
        if estimated <= self.prune_threshold_tokens:
            return 0

        # Cannot prune if message list is small
        min_messages = self.preserved_initial_turns + self.recent_turns_budget
        if len(self.messages) <= min_messages:
            return 0

        # Determine slice to prune: between preserved_initial_turns and -recent_turns_budget
        prune_start = self.preserved_initial_turns
        prune_end = len(self.messages) - self.recent_turns_budget
        if prune_end <= prune_start:
            return 0

        pruned_count = prune_end - prune_start
        # Insert a brief tombstone notice
        notice = {
            "role": "system",
            "content": f"[Context pruned: {pruned_count} intermediate turns pruned to respect the token budget]",
        }
        self.messages = (
            self.messages[:prune_start]
            + [notice]
            + self.messages[prune_end:]
        )
        return pruned_count

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
