import unittest

import graph


class GraphQueryTests(unittest.TestCase):
    def test_shortest_path_uses_falkordb_with_form(self):
        class FakeGraph:
            def query(self, query, params):
                self.query_text = query
                self.params = params
                return type("Result", (), {"result_set": [[['a.py::one', 'b.py::two']]]})()

        fake = FakeGraph()
        path = graph.call_path(fake, "a.py::one", "b.py::two")
        self.assertEqual(path, ["a.py::one", "b.py::two"])
        self.assertIn("WITH shortestPath((a)-[:CALLS*]->(b)) AS p", fake.query_text)
        self.assertEqual(fake.params, {"a": "a.py::one", "b": "b.py::two"})


if __name__ == "__main__":
    unittest.main()
