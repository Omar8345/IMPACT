# Requests PR #6644 — IMPACT report

Source: [Requests PR #6644](https://github.com/psf/requests/pull/6644)
Analyzed PR head: `60389df6d69c`
Machine-specific test paths are redacted below.

## PR impact report

### `src/requests/adapters.py::HTTPAdapter.request_url` (lines 369-399)
- Potentially reaches **2** callers (2 direct), including **1** tests
- Longest chain (1 hops): `adapters:HTTPAdapter.send` → `adapters:HTTPAdapter.request_url`
- Relevant tests: `tests/test_adapters.py::test_request_url_trims_leading_path_separators`

### `tests/test_adapters.py::test_request_url_trims_leading_path_separators` (lines 4-8)
This test changed directly and was included in the selected test run.

## Selected test run

Ran 1 selected test (exit code 0).

- PASSED: `tests/test_adapters.py::test_request_url_trims_leading_path_separators`

```text
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.7.0 -- <IMPACT virtualenv>/bin/python
cachedir: .pytest_cache
rootdir: <temporary PR checkout>
configfile: pyproject.toml
plugins: anyio-4.15.1
collecting ... collected 1 item

tests/test_adapters.py::test_request_url_trims_leading_path_separators PASSED [100%]

============================== 1 passed in 0.04s ===============================
```
