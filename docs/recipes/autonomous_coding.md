# Recipe: Autonomous Mode Coding

In autonomous mode, the sandbox executes a complete project specification end-to-end without requiring human intervention.

## 1. Crafting the Task File
Create a Markdown specification file in your project or repository root, e.g. `specs/build_api.md`:

```markdown
# Project Specification: Async Weather Cache Service

## Requirements
1. Build an asynchronous HTTP caching service using FastAPI and SQLite in `src/weather_service/`.
2. Implement caching with a 5-minute TTL.
3. Write unit and integration tests using `pytest` and `httpx` in `tests/`.
4. Ensure 100% type annotations compliant with `mypy --strict`.
5. Comply with `ruff format` and `ruff check`.
6. Generate a final report in `docs/final_report.md`.
```

## 2. Launching Execution
Set `TASK_FILE=specs/build_api.md` in `.env`, or pass it directly to Make:

```bash
make run-autonomous TASK_FILE=specs/build_api.md
```

## 3. Monitoring Progress
Follow the execution logs in real-time:
```bash
tail -f logs/autonomous.log
```
Or open the telemetry dashboard at `http://localhost:8080` if `DASHBOARD_ENABLED=true`.

## 4. Verification
Once execution concludes, verify the generated code and test suite:
```bash
make check
```
