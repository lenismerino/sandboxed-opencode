"""Task Evaluator and Benchmark Scoring for Sandboxed Coding Tasks."""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclasses.dataclass
class EvaluationCheck:
    name: str
    passed: bool
    output: str
    command: Optional[str] = None


@dataclasses.dataclass
class EvaluationReport:
    task_name: str
    all_passed: bool
    checks: List[EvaluationCheck]
    metrics: Dict[str, Any]

    def summary(self) -> str:
        status = "PASSED" if self.all_passed else "FAILED"
        lines = [
            f"=== Evaluation Report: {self.task_name} [{status}] ===",
        ]
        for c in self.checks:
            mark = "✓" if c.passed else "✗"
            lines.append(f"  {mark} {c.name:<25} (cmd: {c.command or 'internal'})")
        return "\n".join(lines)


class TaskEvaluator:
    """Evaluates the state of a project after agent task execution."""

    def __init__(self, project_dir: str = ".") -> None:
        self.project_dir = Path(project_dir).resolve()

    def _run_cmd(self, cmd: List[str], timeout: int = 60) -> Tuple[bool, str]:
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = res.stdout
            if res.stderr:
                out += f"\n{res.stderr}"
            return (res.returncode == 0, out.strip())
        except FileNotFoundError:
            return (False, f"Command '{cmd[0]}' not installed or not in PATH.")
        except Exception as err:
            return (False, f"Execution failed: {err}")

    def evaluate(
        self,
        task_name: str,
        expected_files: Optional[List[str]] = None,
        run_ruff: bool = True,
        run_pytest: bool = True,
        run_mypy: bool = False,
    ) -> EvaluationReport:
        """Run standard verification suite against the project directory.

        Args:
            task_name: Name or description of evaluated task.
            expected_files: Optional list of files that must exist.
            run_ruff: Check code formatting and linting with ruff.
            run_pytest: Execute pytest test runner.
            run_mypy: Check static types with mypy.

        Returns:
            EvaluationReport dataclass instance.
        """
        checks: List[EvaluationCheck] = []

        # 1. Expected files
        if expected_files:
            for rel in expected_files:
                target = self.project_dir / rel
                exists = target.exists()
                checks.append(
                    EvaluationCheck(
                        name=f"File exists: {rel}",
                        passed=exists,
                        output=f"Size: {target.stat().st_size} bytes" if exists else "File not found",
                    )
                )

        # 2. Ruff format check
        if run_ruff:
            passed, out = self._run_cmd(["ruff", "format", "--check", "."])
            checks.append(
                EvaluationCheck(
                    name="Ruff Formatting",
                    passed=passed,
                    output=out,
                    command="ruff format --check .",
                )
            )

            # Ruff lint check
            passed, out = self._run_cmd(["ruff", "check", "."])
            checks.append(
                EvaluationCheck(
                    name="Ruff Linting",
                    passed=passed,
                    output=out,
                    command="ruff check .",
                )
            )

        # 3. Mypy type check
        if run_mypy:
            passed, out = self._run_cmd(["mypy", "."])
            checks.append(
                EvaluationCheck(
                    name="Mypy Type Checking",
                    passed=passed,
                    output=out,
                    command="mypy .",
                )
            )

        # 4. Pytest test suite
        if run_pytest:
            passed, out = self._run_cmd(["pytest", "-v"])
            checks.append(
                EvaluationCheck(
                    name="Pytest Suite",
                    passed=passed,
                    output=out,
                    command="pytest -v",
                )
            )

        all_passed = all(c.passed for c in checks)
        return EvaluationReport(
            task_name=task_name,
            all_passed=all_passed,
            checks=checks,
            metrics={"total_checks": len(checks), "passed_count": sum(1 for c in checks if c.passed)},
        )
