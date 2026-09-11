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
