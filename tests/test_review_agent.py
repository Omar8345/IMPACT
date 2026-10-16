import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import review


class ReviewAgentTests(unittest.TestCase):
    def test_selected_tests_confirm_demo_regression(self):
        repo = Path(__file__).parents[1] / "demo_checkout"
        impact = {"shop/pricing.py::apply_coupon": [
            {"id": "tests/test_checkout.py::CheckoutTests.test_checkout_large_coupon", "is_test": True},
            {"id": "tests/test_checkout.py::CheckoutTests.test_checkout_normal_coupon", "is_test": True},
            {"id": "tests/test_receipts.py::ReceiptTests.test_receipt_large_coupon", "is_test": True},
        ]}
        with patch.object(review.importlib.util, "find_spec", return_value=None):
            result = review.run_selected_tests(repo, impact)
        self.assertEqual(result["statuses"]["tests/test_checkout.py::CheckoutTests::test_checkout_normal_coupon"], "passed")
        self.assertEqual(result["statuses"]["tests/test_checkout.py::CheckoutTests::test_checkout_large_coupon"], "error")
        self.assertEqual(result["statuses"]["tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon"], "failed")

    def test_changed_test_runs_even_without_graph_callers(self):
        repo = Path(__file__).parents[1] / "demo_checkout"
        direct = ["tests/test_checkout.py::CheckoutTests.test_checkout_normal_coupon"]
        with patch.object(review.importlib.util, "find_spec", return_value=None):
            result = review.run_selected_tests(repo, {}, direct_tests=direct)
        self.assertEqual(result["node_ids"], ["tests/test_checkout.py::CheckoutTests::test_checkout_normal_coupon"])
        self.assertEqual(result["statuses"][result["node_ids"][0]], "passed")

    def test_ai_priority_runs_first_but_keeps_other_selected_tests(self):
        impact = {"shop/pricing.py::apply_coupon": [
            {"id": "tests/test_checkout.py::CheckoutTests.test_checkout_large_coupon", "is_test": True},
            {"id": "tests/test_receipts.py::ReceiptTests.test_receipt_large_coupon", "is_test": True},
        ]}
        priority = "tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon"
        with patch.object(review.importlib.util, "find_spec", return_value=None):
            with patch.object(review, "_run_unittest_targets", return_value={}) as runner:
                review.run_selected_tests(".", impact, priority_test=priority)
        selected = runner.call_args.args[1]
        self.assertEqual(selected[0], priority)
        self.assertEqual(len(selected), 2)

    def test_openrouter_tool_loop_uses_graph_result(self):
        responses = [
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call-1", "type": "function", "function": {
                    "name": "impact_of_change",
                    "arguments": json.dumps({"function_id": "shop/pricing.py::apply_coupon"})
                }}]},
            {"role": "assistant", "content": json.dumps({
                "focus_function": "shop/pricing.py::apply_coupon",
                "priority_test": "tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon",
                "reason_code": "boundary_case"})},
        ]
        with patch.object(review, "_openrouter_chat", side_effect=responses) as chat:
            with patch.dict(review.tools.TOOLS, {
                "impact_of_change": lambda function_id: {"function": function_id, "total_affected": 1}
            }):
                from repo_parser import Func
                changed = [Func("shop/pricing.py::apply_coupon", "apply_coupon", "apply_coupon",
                                "shop/pricing.py", 4, 9, False)]
                impacts = {changed[0].id: [{
                    "id": "tests/test_receipts.py::ReceiptTests.test_receipt_large_coupon",
                    "is_test": True, "hops": 1,
                    "path": ["tests/test_receipts.py::ReceiptTests.test_receipt_large_coupon", changed[0].id]}]}
                result = review.llm_decision(changed, "sample diff", impacts)
        self.assertIn("## AI review priority", result["report"])
        self.assertIn("1 reachable callers", result["report"])
        self.assertIn("Graph path", result["report"])
        self.assertNotIn("negative charge", result["report"])
        self.assertEqual(result["priority_test"], "tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon")
        self.assertEqual(chat.call_count, 2)

    def test_openrouter_review_requires_a_graph_tool_call(self):
        from repo_parser import Func
        changed = [Func("shop/pricing.py::apply_coupon", "apply_coupon", "apply_coupon",
                        "shop/pricing.py", 4, 9, False)]
        with patch.object(review, "_openrouter_chat", return_value={
            "role": "assistant", "content": "Unsupported claim without graph evidence."
        }):
            with self.assertRaisesRegex(RuntimeError, "did not query impact"):
                review.llm_decision(changed, "sample diff", {changed[0].id: []})

    def test_ai_priority_must_be_a_verified_test(self):
        from repo_parser import Func
        changed = [Func("a.py::target", "target", "target", "a.py", 1, 2, False)]
        responses = [
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call-1", "type": "function", "function": {
                    "name": "impact_of_change", "arguments": json.dumps({"function_id": changed[0].id})}}]},
            {"role": "assistant", "content": json.dumps({
                "focus_function": changed[0].id, "priority_test": "tests/fake.py::test_fake",
                "reason_code": "boundary_case"})},
        ]
        with patch.object(review, "_openrouter_chat", side_effect=responses):
            with patch.dict(review.tools.TOOLS, {
                "impact_of_change": lambda function_id: {"function": function_id, "total_affected": 0}
            }):
                with self.assertRaisesRegex(RuntimeError, "outside verified options"):
                    review.llm_decision(changed, "sample diff", {changed[0].id: []})

    def test_ai_evidence_lists_every_selected_test(self):
        from repo_parser import Func
        changed = [Func("a.py::target", "target", "target", "a.py", 1, 2, False)]
        impacts = {changed[0].id: [
            {"id": "tests/test_a.py::Cases.test_one", "is_test": True,
             "hops": 1, "path": ["tests/test_a.py::Cases.test_one", changed[0].id]},
            {"id": "tests/test_a.py::Cases.test_two", "is_test": True,
             "hops": 1, "path": ["tests/test_a.py::Cases.test_two", changed[0].id]},
        ]}
        summary = review.graph_evidence_section(changed, impacts)
        self.assertIn("2 reachable tests", summary)
        self.assertIn("Cases::test_one", summary)
        self.assertIn("Cases::test_two", summary)

    def test_html_marks_actual_test_status_only_when_supplied(self):
        from repo_parser import Func
        changed = [Func("a.py::target", "target", "target", "a.py", 1, 2, False)]
        impacts = {changed[0].id: [{"id": "tests/test_a.py::test_target", "is_test": True,
                                    "hops": 1, "path": ["tests/test_a.py::test_target", "a.py::target"]}]}
        test_run = {"statuses": {"tests/test_a.py::test_target": "failed"}}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "impact.html"
            review.write_html(changed, impacts, output, test_run)
            html = output.read_text()
        self.assertIn('"status": "failed"', html)
        self.assertIn('"kind": "test"', html)

    def test_html_counts_a_directly_changed_test_without_a_call_path(self):
        from repo_parser import Func
        changed = [Func("src/app.py::calculate", "calculate", "calculate",
                        "src/app.py", 1, 3, False),
                   Func("tests/test_app.py::test_calculate", "test_calculate", "test_calculate",
                        "tests/test_app.py", 1, 3, True)]
        impacts = {f.id: [] for f in changed}
        test_run = {"statuses": {"tests/test_app.py::test_calculate": "passed"}}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "impact.html"
            review.write_html(changed, impacts, output, test_run)
            html = output.read_text()
        self.assertIn('"kind": "test", "changed": true', html)
        self.assertIn('"status": "passed"', html)

    def test_html_includes_verified_ai_priority(self):
        from repo_parser import Func
        changed = [Func("a.py::target", "target", "target", "a.py", 1, 2, False)]
        test_id = "tests/test_a.py::Case.test_target"
        impacts = {changed[0].id: [{"id": test_id, "is_test": True,
                                    "hops": 1, "path": [test_id, changed[0].id]}]}
        decision = {"focus_function": changed[0].id,
                    "priority_test": "tests/test_a.py::Case::test_target",
                    "reason": "The edit may affect a boundary case."}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "impact.html"
            review.write_html(changed, impacts, output, decision=decision)
            html = output.read_text()
        self.assertIn('"ai": {"focus": "a.py::target"', html)
        self.assertIn('"priority_test": "tests/test_a.py::Case::test_target"', html)
        self.assertIn('id="ai-panel"', html)


if __name__ == "__main__":
    unittest.main()
