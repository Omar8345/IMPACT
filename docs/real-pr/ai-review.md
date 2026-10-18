## AI review priority

The model queried FalkorDB's `impact_of_change` tool for:

- `src/requests/adapters.py::HTTPAdapter.request_url` (2 reachable callers)
- `tests/test_adapters.py::test_request_url_trims_leading_path_separators` (0 reachable callers)

- **Inspect first:** `src/requests/adapters.py::HTTPAdapter.request_url`
- **Reason to inspect:** The edit may affect a boundary case.
- **Run first:** `tests/test_adapters.py::test_request_url_trims_leading_path_separators`
- **Graph path:** `test_adapters:test_request_url_trims_leading_path_separators` → `adapters:HTTPAdapter.request_url`

This is a review priority. Test results appear below only when tests were run.

## FalkorDB evidence

- `src/requests/adapters.py::HTTPAdapter.request_url`: 2 reachable callers; 1 reachable tests
  - Longest path: `adapters:HTTPAdapter.send` → `adapters:HTTPAdapter.request_url`
  - Test: `tests/test_adapters.py::test_request_url_trims_leading_path_separators`
- `tests/test_adapters.py::test_request_url_trims_leading_path_separators` is a changed test; it is selected directly
