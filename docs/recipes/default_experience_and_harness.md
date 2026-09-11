# Recipe: The Default Experience (`make run`) with Harness Tools

This recipe walks through the default developer experience using `make run`, highlighting how OpenCode Web connects to local reasoning models (Google Gemma 4 E4B) and automatically gains harness tools (`semantic_search`, `compact_context`, `evaluate_codebase`, `track_milestone`).

---

## 1. Zero-Friction Launch

When you launch the sandbox using the default command:

```bash
make run
```

The container starts and automatically configures OpenCode to work with your local inference server (LM Studio or Ollama).

### What Happens Automatically:
1. **Model Profile Loaded**: Loads hyperparameters from `config/model_profiles/gemma-4-e4b.json` (131,072 context window, Top-K/Top-P sampling, reasoning extraction).
2. **OpenCode Configuration (`opencode.json`)**: Configures provider base URL (`http://<LLM_HOST>:1234/v1`) and context parameters.
3. **Automatic Harness MCP Tools Injection**: Injects the stdio `sandbox_harness` MCP server (`scripts/harness_mcp.py`) into OpenCode's configuration.
4. **Project Operating Guidelines (`.opencode/instructions.md`)**: Injects reasoning instructions directly into the project directory so the model prioritizes hypothesis formation, verification, and non-hallucination.
5. **Startup Banner**: Displays connection URLs and active configuration.

---

## 2. Available Harness Tools in OpenCode Chat

When interacting with the agent in the OpenCode Web UI (`http://localhost:3000`), the model has native access to the following harness tools:

| Tool Name | Purpose | When to Use |
|---|---|---|
| `semantic_search` | Offline semantic code search | Searching logic or concepts without exact keyword matches. |
| `compact_context` | Checkpoint and compact context | Long chat sessions or after finishing a major milestone. |
| `evaluate_codebase` | Automated testing & linting | Validating syntax (Ruff) and tests (Pytest) in one call. |
| `track_milestone` | Milestone & goal tracking | Updating the observability dashboard on task progress. |
| `get_telemetry` | Telemetry inspection | Checking token velocity, reasoning depth, and context headroom. |

---

## 3. Recommended Prompts for the Default Experience

Here are proven prompts to make the most out of **Google Gemma 4 E4B** in `make run`:

### Deep Problem Solving
> *"Inspect the codebase using `semantic_search` to understand how model profiles are validated. In your `<thought>` phase, outline three edge cases where JSON schema validation could fail, then implement corresponding unit tests."*

### Autonomous Multi-Step Feature
> *"Add an LRU cache decorator to `harness/embeddings.py`. Step 1: Write a failing pytest in `harness/harness_test.py`. Step 2: Implement the feature. Step 3: Call `evaluate_codebase` to verify all tests pass. Step 4: Call `compact_context` and summarize."*

### Long Task Checkpointing
> *"We have completed the discovery phase. Please call `compact_context` to record an architectural checkpoint and summarize the active files before we begin the implementation phase."*
