# Model Profiles Guide & Reference

Model profiles provide declarative, model-specific tuning for open-weights and proprietary models running locally or across private LAN infrastructure.

## What is a Model Profile?

A model profile (`config/model_profiles/<name>.json`) encapsulates:
- **Context Window & Budgeting**: Maximum sequence length, reserved output tokens, sliding-window truncation threshold.
- **Sampling Parameters**: Deterministic temperature, top-p, top-k, min-p, repetition penalties.
- **Reasoning Capabilities**: Thought trace capture (`reasoning_content`), reasoning token budgeting.
- **Tool Calling & Schema Standards**: Format (`openai_function`), strict schema validation, parallel tool execution policy.
- **Structured Outputs**: JSON Schema strictness.
- **Tuned System Prompts**: Custom engineered system prompts that exploit model strengths and enforce container security constraints.

---

## Flagship Profile: Google Gemma 4 E4B (`gemma-4-e4b`)

Google Gemma 4 E4B is an open-weights reasoning vision-language model served natively via LM Studio with an extended **131,072 token context window** and native tool calling.

### Configuration Highlights

```json
{
  "profile_name": "gemma-4-e4b",
  "display_name": "Google Gemma 4 E4B (LM Studio)",
  "model_id": "google/gemma-4-e4b",
  "provider": "lm_studio",
  "architecture": "gemma4",
  "context_window": {
    "max_context_length": 131072,
    "reserved_completion_tokens": 8192,
    "effective_prompt_limit": 122880
  },
  "sampling": {
    "temperature": 0.2,
    "top_p": 0.95,
    "top_k": 40,
    "min_p": 0.05,
    "repeat_penalty": 1.05
  },
  "reasoning": {
    "supported": true,
    "field": "reasoning_content",
    "budget_tokens": 4096
  },
  "tool_calling": {
    "supported": true,
    "format": "openai_function",
    "strict": true,
    "parallel_tool_calls": false
  },
  "structured_output": {
    "supported": true,
    "format": "json_schema",
    "strict": true
  }
}
```

### Why These Hyperparameters?
- **`temperature: 0.2` & `top_p: 0.95`**: Delivers deterministic, precise coding logic while retaining sufficient flexibility for complex algorithm design.
- **`top_k: 40`**: Restricts the search space to the top 40 candidate tokens, significantly reducing syntactic errors in code generation.
- **`max_context_length: 131072`**: Empowers the model to comprehend multi-file refactors and entire test suites simultaneously.
- **`reserved_completion_tokens: 8192`**: Guarantees that reasoning tokens (~1,000–4,000 tokens) do not truncate the final code output.
- **Sequential Tool Calling (`parallel_tool_calls: false`)**: Prevents race conditions during filesystem modification.

---

## Managing Profiles via CLI

The sandbox includes `scripts/model_profile.py` for managing profiles:

### List Available Profiles
```bash
make profiles
# or
python3 scripts/model_profile.py list
```

### Validate Profile Schemas
```bash
python3 scripts/model_profile.py validate
```

### Live Endpoint Testing
Run non-destructive live inference and tool-calling tests against your LM Studio server:
```bash
python3 scripts/model_profile.py test gemma-4-e4b --host 192.168.1.3 --port 1234
```

### Export OpenCode Configuration
```bash
python3 scripts/model_profile.py export-opencode gemma-4-e4b
```
