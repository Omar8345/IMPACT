import tempfile
import unittest
from pathlib import Path

import company
import review
from repo_parser import Func, parse_repo


class CompanyContextTests(unittest.TestCase):
    def test_demo_manifest_links_real_source_files(self):
        repo = Path(__file__).parents[1] / "demo_checkout"
        funcs, _ = parse_repo(repo)
        data = company.validate_manifest(repo, repo / "company.json", funcs)
        self.assertEqual(len(data["people"]), 2)
        self.assertEqual(len(data["knowledge"]), 3)
        decision = next(s for s in data["knowledge"] if s["id"] == "DEC-14")
        self.assertIn("never create a negative balance", decision["content"])
        self.assertEqual(len(decision["sha256"]), 64)

    def test_sync_connects_knowledge_and_ownership_to_code(self):
        repo = Path(__file__).parents[1] / "demo_checkout"
        funcs, _ = parse_repo(repo)
        data = company.validate_manifest(repo, repo / "company.json", funcs)

        class FakeGraph:
            queries = []

            def query(self, cypher, params=None):
                self.queries.append((cypher, params))

        graph = FakeGraph()
        self.assertEqual(company.sync(graph, data), (2, 3))
        self.assertTrue(any("[:OWNS]" in q and p["file"] == "shop/pricing.py"
                            for q, p in graph.queries if p))
        self.assertTrue(any("[:ABOUT]" in q and p["function"] == "shop/pricing.py::apply_coupon"
                            for q, p in graph.queries if p and "function" in p))

    def test_manifest_rejects_source_outside_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            manifest = repo / "company.json"
            manifest.write_text('{"knowledge": [{"path": "../private.md"}]}')
            with self.assertRaisesRegex(ValueError, "inside the repo"):
                company.read_manifest(repo, manifest)

    def test_context_uses_graph_results_for_owner_and_sources(self):
        class FakeGraph:
            def query(self, cypher, params):
                if "MATCH (fn:Function" not in cypher:
                    raise AssertionError("Expected a function graph traversal")
                if "OWNS" in cypher:
                    rows = [["Maya Chen", "Commerce", "shop/pricing.py"]]
                else:
                    rows = [["DEC-14", "decision", "Coupon policy",
                             "company/discount-decision.md", "Discounts stop at zero", "abc"]]
                return type("Result", (), {"result_set": rows})()

        item = company.context(FakeGraph(), "shop/pricing.py::apply_coupon")
        text = company.report([item])
        self.assertIn("Maya Chen", text)
        self.assertIn("company/discount-decision.md", text)
        self.assertIn("DEC-14", text)

    def test_html_shows_company_sources_as_data(self):
        changed = [Func("shop/pricing.py::apply_coupon", "apply_coupon", "apply_coupon",
                        "shop/pricing.py", 4, 9, False)]
        context = {"function": changed[0].id,
                   "owners": [{"name": "Maya Chen", "team": "Commerce", "file": "shop/pricing.py"}],
                   "sources": [{"id": "DEC-14", "kind": "decision", "title": "Coupon policy",
                                "path": "company/discount-decision.md", "content": "private source text",
                                "sha256": "abc"}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "impact.html"
            review.write_html(changed, {changed[0].id: []}, path, company_context=[context])
            html = path.read_text()
        self.assertIn('"name": "Maya Chen"', html)
        self.assertIn('"title": "Coupon policy"', html)
        self.assertNotIn("private source text", html)


if __name__ == "__main__":
    unittest.main()
