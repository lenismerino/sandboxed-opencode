# Recipe: Zero-Config Auto-Discovery Quickstart

This recipe demonstrates how to get up and running with a single command using the built-in auto-discovery wizard. It automatically discovers active LM Studio or Ollama instances, profiles the loaded model, tunes context parameters, and configures `.env`.

---

## 1. The Vision

The goal of `sandboxed-opencode` is zero friction: **having LM Studio OR Ollama as your single dependency** delivers completely free, unlimited, local, private, and secure AI for your development projects.

You do not need to memorize port numbers, model ID strings, or manual `.env` settings. The auto-discovery wizard probes your local machine and local area network (LAN) to find inference endpoints automatically.

---

## 2. One-Command Setup

Run the quickstart target from the repository root:

```bash
make quickstart
```

Or invoke the Python script directly:

```bash
python3 scripts/quickstart.py
```

### What Happens Behind the Scenes:
1. **Endpoint Scanning**: Probes standard local endpoints (`http://localhost:1234`, `http://localhost:11434`, `http://127.0.0.1:...`, `http://host.docker.internal:...`) and active LAN servers (e.g. `http://192.168.1.3:1234`).
2. **Model Identification**: Queries `/v1/models` (or `/api/tags` for Ollama) to retrieve loaded model identifiers.
3. **Profile Matching**: Automatically pairs the discovered model to an optimized profile in `config/model_profiles/`:
   - `google/gemma-4-e4b` → `gemma-4-e4b` (131K context, Top-K/Top-P sampling, reasoning extraction)
   - `qwen*` → `qwen-3.5-9b` (32K/64K context)
   - Fallback profiles for standard Ollama / LM Studio models
4. **Embedding Detection**: Checks for loaded embedding models (e.g., `text-embedding-nomic-embed-text-v1.5`) for semantic code search.
5. **Environment Configuration**: Writes or updates `.env` with validated paths, model profiles, and connection parameters.

---

## 3. Command Options & Flags

The quickstart wizard supports several flags for automated environments or dry runs:

| Flag | Description |
|------|-------------|
| `--dry-run` | Probes endpoints and prints the generated configuration without modifying `.env`. |
| `--host <IP>` | Explicitly scans a target host IP or hostname instead of default probe list. |
| `--port <PORT>` | Explicitly scans a target port. |
| `--force` | Overwrites existing `.env` values without prompting. |

### Example: Dry Run Probe
```bash
python3 scripts/quickstart.py --dry-run
```

Output:
```
============================================================
  sandboxed-opencode: Zero-Config Auto-Discovery Wizard
============================================================
[1/4] Probing for active local inference engines...
  ✓ Found LM Studio at http://192.168.1.3:1234
    Available models: ['google/gemma-4-e4b', 'text-embedding-nomic-embed-text-v1.5']

[2/4] Selecting optimal model profile...
  ✓ Selected Model Profile: gemma-4-e4b
  ✓ Selected Model ID: google/gemma-4-e4b

[3/4] Tuning context and sampling hyperparameters...
  - Context Window: 131,072 tokens
  - Temperature: 0.2
  - Top-P: 0.95 | Top-K: 40
  - Native Reasoning: Enabled
  - Native Tool Calling: Enabled

[4/4] Writing .env configuration...
  ✓ .env generated successfully!
```

---

## 4. Verifying the Setup

After running `make quickstart`, verify that your container can reach the inference engine and perform reasoning:

```bash
make test-model
```

Once tests pass, launch your preferred mode:
- **Interactive Web UI**: `make run` (at `http://localhost:3000`)
- **Terminal TUI**: `make run-tui`
- **Autonomous Project Generation**: `make run-autonomous TASK_FILE=sample_project_prompt.md`
- **Conductor Mode (MCP Bridge)**: `make run-conductor`
