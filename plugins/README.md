# Plugins Architecture & Lifecycle Hooks

Plugins provide an extensible lifecycle hook system for the sandboxed agent loops, harness evaluations, and OpenCode workflows.

## Plugin Directory Layout

```
plugins/
├── README.md
└── hooks/
    ├── __init__.py
    └── token_telemetry.py
```

## Hook Lifecycle Interfaces

A plugin hook implements any of the following lifecycle callbacks:

```python
class BaseHook:
    def on_task_start(self, task_instruction: str, model_profile: str) -> None:
        """Invoked when a task execution starts."""
        pass

    def on_step_complete(self, step_record: dict) -> None:
        """Invoked after each step completion (model response + tool execution)."""
        pass

    def on_task_finish(self, task_result: dict) -> None:
        """Invoked when the task concludes or aborts."""
        pass
```

## Built-In Plugins
- `token_telemetry.py`: Logs real-time token metrics, reasoning token ratio, context window utilization, and per-step latencies to `logs/telemetry.jsonl`.
