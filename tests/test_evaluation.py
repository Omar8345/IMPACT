import unittest

from evaluation.run import aggregate, filename_selection, score_selection


class EvaluationTests(unittest.TestCase):
    def test_selection_metrics_have_explicit_denominators(self):
        result = score_selection({"a", "b"}, {"b", "c"}, 5)
        self.assertEqual(result["failure_recall"], 0.5)
        self.assertEqual(result["test_reduction"], 0.6)
        self.assertEqual(result["failure_yield"], 0.5)

    def test_filename_baseline_uses_changed_module_stem(self):
        tests = {"tests/test_pricing.py::test_one", "tests/test_orders.py::test_two"}
        self.assertEqual(
            filename_selection(tests, {"store/pricing.py"}),
            {"tests/test_pricing.py::test_one"},
        )

    def test_aggregate_is_micro_averaged(self):
        rows = [
            {"total_tests": 10, "failing_tests": ["a", "b"],
             "methods": {"impact": {"selected": 2, "detected_failures": 2}}},
            {"total_tests": 10, "failing_tests": ["c"],
             "methods": {"impact": {"selected": 1, "detected_failures": 1}}},
        ]
        result = aggregate(rows, "impact")
        self.assertEqual(result["failure_recall"], 1.0)
        self.assertEqual(result["test_reduction"], 0.85)


if __name__ == "__main__":
    unittest.main()
