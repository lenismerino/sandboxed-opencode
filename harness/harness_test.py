"""Unit tests for the agent loop harness components."""

import unittest
from pathlib import Path
from harness.context import ContextManager
from harness.evaluator import EvaluationCheck, EvaluationReport
from tools.registry import ToolRegistry


class TestContextManager(unittest.TestCase):
    def setUp(self) -> None:
        self.cm = ContextManager(
            max_context_length=131072,
            reserved_completion_tokens=8192,
            prune_threshold_tokens=500,
            preserved_initial_turns=2,
            recent_turns_budget=4,
        )

    def test_add_and_retrieve_messages(self) -> None:
        self.cm.add_message("system", "You are an assistant.")
        self.cm.add_message("user", "Hello")
        messages = self.cm.get_messages()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["content"], "Hello")

    def test_token_stats(self) -> None:
        self.cm.add_message("system", "Short prompt")
        stats = self.cm.get_stats()
        self.assertIn("estimated_tokens", stats)
        self.assertEqual(stats["max_context_length"], 131072)
        self.assertGreater(stats["headroom_tokens"], 100000)

    def test_context_pruning(self) -> None:
        # Fill with many messages to exceed 500 threshold
        self.cm.add_message("system", "System prompt")
        self.cm.add_message("user", "Task requirement")
        for i in range(20):
            self.cm.add_message("user", f"Turn {i}: " + "word " * 50)
            self.cm.add_message("assistant", f"Response {i}: " + "reply " * 50)

        # After adding many messages, pruning should have kept the total bounded
        self.assertLessEqual(self.cm.estimate_total_tokens(), 1500)
        messages = self.cm.get_messages()
        self.assertEqual(messages[0]["content"], "System prompt")
        self.assertEqual(messages[1]["content"], "Task requirement")


class TestToolRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry(project_dir=".")

    def test_registered_tools_present(self) -> None:
        specs = self.registry.get_openai_tool_specs()
        names = [s["function"]["name"] for s in specs]
        self.assertIn("read_file", names)
        self.assertIn("write_file", names)
        self.assertIn("list_files", names)
        self.assertIn("grep_search", names)
        self.assertIn("patch_file", names)
        self.assertIn("run_command", names)
        self.assertIn("semantic_search", names)

    def test_path_traversal_blocked(self) -> None:
        out = self.registry.execute("read_file", {"path": "../../../etc/passwd"})
        self.assertIn("outside project root", out)


class TestSemanticEmbeddings(unittest.TestCase):
    def test_cosine_similarity(self) -> None:
        from harness.embeddings import _cosine_similarity
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        vec3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(_cosine_similarity(vec1, vec2), 1.0)
        self.assertAlmostEqual(_cosine_similarity(vec1, vec3), 0.0)

    def test_chunking(self) -> None:
        import tempfile
        from harness.embeddings import SemanticCodeIndex
        with tempfile.TemporaryDirectory() as tmpdir:
            sample = Path(tmpdir) / "sample.py"
            sample.write_text("\n".join(f"print({i})" for i in range(100)))
            index = SemanticCodeIndex(project_dir=tmpdir)
            chunks = index._chunk_file(sample, max_lines=30, overlap=5)
            self.assertGreater(len(chunks), 2)
            self.assertEqual(chunks[0].start_line, 1)


class TestContextCompaction(unittest.TestCase):
    def setUp(self) -> None:
        self.cm = ContextManager(
            max_context_length=1000,
            reserved_completion_tokens=100,
            prune_threshold_tokens=500,
            preserved_initial_turns=2,
            recent_turns_budget=3,
        )

    def test_compact_method(self) -> None:
        self.cm.add_message("system", "Root system instruction")
        self.cm.add_message("user", "Initial goal specification")
        for i in range(10):
            self.cm.add_message("user", f"Query {i}: details about module")
            self.cm.add_message("assistant", f"Assistant answer {i} with code snippet")

        res = self.cm.compact()
        self.assertTrue(res["compacted"])
        self.assertGreater(res["pruned_turns"], 0)
        messages = self.cm.get_messages()
        # System + Initial User + Compacted Notice + 3 recent turns = 6 messages
        self.assertEqual(messages[0]["content"], "Root system instruction")
        self.assertEqual(messages[1]["content"], "Initial goal specification")
        self.assertIn("Architectural Context Checkpoint", messages[2]["content"])

    def test_needs_compaction(self) -> None:
        self.cm.add_message("system", "Test")
        self.assertFalse(self.cm.needs_compaction(headroom_threshold_pct=0.10))

    def test_export_and_load_state(self) -> None:
        self.cm.add_message("system", "Initial prompt")
        self.cm.add_message("user", "Hello")
        state = self.cm.export_state()
        new_cm = ContextManager()
        new_cm.load_state(state)
        self.assertEqual(len(new_cm.messages), 2)
        self.assertEqual(new_cm.messages[0]["content"], "Initial prompt")


class TestSessionLifecycle(unittest.TestCase):
    def test_session_rotation(self) -> None:
        import tempfile
        from harness.session import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(project_dir=Path(tmpdir))
            state = sm.start_session(goal="Build offline feature")
            self.assertEqual(state.session_index, 1)

            sm.record_milestone("Discovery", "completed", "Analyzed files")
            sm.record_modified_files(["src/core.py", "tests/test_core.py"])

            cm = ContextManager(max_context_length=2000, reserved_completion_tokens=200)
            cm.add_message("system", "SysPrompt")
            cm.add_message("user", "Build offline feature")
            cm.add_message("assistant", "Working on code")

            fresh_cm = sm.rotate_session(cm, next_goal="Proceed to verification")
            self.assertEqual(sm.current_state.session_index, 2)
            self.assertEqual(len(fresh_cm.messages), 2)
            self.assertIn("Executive Session Handoff", fresh_cm.messages[1]["content"])
            self.assertIn("src/core.py", fresh_cm.messages[1]["content"])


class TestTelemetryTracker(unittest.TestCase):
    def test_metrics_calculation(self) -> None:
        import tempfile
        from harness.telemetry import TelemetryTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            tt = TelemetryTracker(project_dir=Path(tmpdir))
            tt.record_step(
                step_idx=1,
                elapsed_seconds=2.0,
                prompt_tokens=100,
                completion_tokens=50,
                reasoning_tokens=20,
                tool_calls=[{"function": {"name": "read_file"}}],
            )
            self.assertEqual(tt.total_steps, 1)
            self.assertEqual(tt.token_velocity_tps, 25.0)
            self.assertEqual(tt.reasoning_ratio, 0.4)
            self.assertEqual(tt.tool_calls_counts.get("read_file"), 1)

            # Test persistence
            summary = tt.get_summary()
            self.assertEqual(summary["total_prompt_tokens"], 100)


class TestEvaluationReport(unittest.TestCase):
    def test_summary_format(self) -> None:
        report = EvaluationReport(
            task_name="sample_task",
            all_passed=True,
            checks=[EvaluationCheck(name="Lint Check", passed=True, output="ok")],
            metrics={"total": 1},
        )
        summary = report.summary()
        self.assertIn("PASSED", summary)
        self.assertIn("Lint Check", summary)


if __name__ == "__main__":
    unittest.main()
