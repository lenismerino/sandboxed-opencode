"""Model Client for communicating with LLM backends using Model Profiles."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


class ModelClient:
    """Client implementing the OpenAI-compatible chat completion protocol

    with specialized support for Gemma 4 E4B reasoning traces, K/P sampling,
    and structured tool calls.
    """

    def __init__(
        self,
        base_url: str,
        profile: Dict[str, Any],
        api_key: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    def warm_up(self) -> bool:
        """Ping the model endpoint with a minimal completion to ensure GPU layers are loaded."""
        model_id = self.profile["model_id"]
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status == 200
        except Exception:
            return False

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a chat completion request to the model with auto-retry on transient errors.

        Args:
            messages: Conversation messages.
            tools: Optional tool definitions.
            response_format: Optional JSON schema response format.
            temperature: Optional temperature override.

        Returns:
            Dictionary with 'content', 'reasoning_content', 'tool_calls', 'usage', and 'elapsed_seconds'.
        """
        sampling = self.profile.get("sampling", {})
        model_id = self.profile["model_id"]

        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature if temperature is not None else sampling.get("temperature", 0.2),
            "top_p": sampling.get("top_p", 0.95),
            "max_tokens": self.profile.get("context_window", {}).get("reserved_completion_tokens", 4096),
        }

        # Apply Gemma 4 / advanced sampling if configured
        if "top_k" in sampling and sampling["top_k"] > 0:
            payload["top_k"] = sampling["top_k"]
        if "repeat_penalty" in sampling:
            payload["repeat_penalty"] = sampling["repeat_penalty"]

        # Tools
        if tools and self.profile.get("tool_calling", {}).get("supported", False):
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Structured output
        if response_format and self.profile.get("structured_output", {}).get("supported", False):
            payload["response_format"] = response_format

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/chat/completions"
        last_err: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    elapsed = time.time() - t0
                    choice = resp_json.get("choices", [{}])[0]
                    msg = choice.get("message", {})

                    return {
                        "content": msg.get("content") or "",
                        "reasoning_content": msg.get("reasoning_content") or "",
                        "tool_calls": msg.get("tool_calls") or [],
                        "finish_reason": choice.get("finish_reason"),
                        "usage": resp_json.get("usage", {}),
                        "elapsed_seconds": round(elapsed, 3),
                    }
            except urllib.error.HTTPError as err:
                body = err.read().decode("utf-8", errors="replace")
                last_err = RuntimeError(f"Model API error HTTP {err.code}: {body}")
                # Retry on 429, 502, 503, 504
                if err.code in (429, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(1.5 * attempt)
                    continue
                raise last_err from err
            except Exception as err:
                last_err = RuntimeError(f"Network error connecting to {url}: {err}")
                if attempt < self.max_retries:
                    time.sleep(1.5 * attempt)
                    continue
                raise last_err from err

        raise last_err or RuntimeError(f"Failed to get response after {self.max_retries} attempts.")
