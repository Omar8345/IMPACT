import json
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import hosted_app


class HostedAnalyzerTests(unittest.TestCase):
    def setUp(self):
        hosted_app._jobs.clear()
        hosted_app._last_submissions.clear()

    def test_url_validation_rejects_non_public_pr_urls(self):
        request = hosted_app.AnalyzeRequest(url="https://example.test/repo.git")
        with self.assertRaises(hosted_app.HTTPException) as error:
            hosted_app.create_analysis(request, SimpleNamespace(client=None))
        self.assertEqual(error.exception.status_code, 400)

    def test_create_analysis_starts_queued_job(self):
        executor = Mock()
        with patch.object(hosted_app, "_executor", executor), \
             patch.object(hosted_app.github_pr, "parse_pr_url", return_value=("o", "r", 1)):
            result = hosted_app.create_analysis(
                hosted_app.AnalyzeRequest(url="https://github.com/o/r/pull/1"),
                SimpleNamespace(client=SimpleNamespace(host="test")))
        self.assertEqual(hosted_app._jobs[result["id"]]["state"], "queued")
        executor.submit.assert_called_once()

    def test_worker_uses_isolated_graph_and_never_runs_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            hosted_app.RESULT_ROOT = Path(directory)
            fake_graph = Mock()
            pr = {"owner": "owner", "repo": "repo", "number": 1,
                  "url": "https://github.com/owner/repo/pull/1",
                  "head_sha": "a" * 40}
            repo = Path(directory) / "checkout"
            repo.mkdir()
            (repo / "app.py").write_text("def changed():\n    return 1\n", encoding="utf-8")
            produced = {}

            def fake_produce(repo_path, diff, args, graph_obj=None):
                produced["run_tests"] = args.run_tests
                produced["graph"] = graph_obj
                Path(args.html).write_text("<html></html>", encoding="utf-8")
                Path(args.report).write_text("# report", encoding="utf-8")
                return "# report"

            job_id = "job123"
            hosted_app._jobs[job_id] = {"state": "queued"}
            checkout_context = MagicMock()
            checkout_context.__enter__.return_value = (repo, "diff")
            checkout_context.__exit__.return_value = False
            with patch.object(hosted_app.github_pr, "checkout_pr",
                              return_value=checkout_context), \
                 patch.object(hosted_app.github_pr, "get_pr", return_value=pr), \
                 patch.object(hosted_app.graph, "connect", return_value=fake_graph) as connect, \
                 patch.object(hosted_app.graph, "load"), \
                 patch.object(hosted_app.main, "produce_review", side_effect=fake_produce):
                hosted_app._analyze(job_id, "https://github.com/owner/repo/pull/1")

            self.assertEqual(hosted_app._jobs[job_id]["state"], "complete")
            connect.assert_called_once()
            graph_name = connect.call_args.args[0]
            self.assertTrue(graph_name.startswith("impact_hosted_"))
            self.assertIs(produced["graph"], fake_graph)
            self.assertFalse(produced["run_tests"])
            fake_graph.delete.assert_called_once()

    def test_metadata_never_contains_secrets(self):
        metadata = {"graph": "impact_hosted_job", "tests_run": False}
        self.assertNotIn("FALKORDB_PASSWORD", json.dumps(metadata))
        self.assertNotIn("OPENROUTER_API_KEY", json.dumps(metadata))

    def test_expired_result_files_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            result_dir = Path(directory) / "expired"
            result_dir.mkdir()
            hosted_app._jobs["expired"] = {
                "state": "complete", "finished_at": time.time() - 10_000,
                "result_dir": str(result_dir),
            }
            with patch.object(hosted_app, "RESULT_TTL_SECONDS", 1):
                hosted_app._expire_results()
            self.assertFalse(result_dir.exists())
            self.assertNotIn("expired", hosted_app._jobs)


if __name__ == "__main__":
    unittest.main()
