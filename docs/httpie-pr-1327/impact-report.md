# HTTPie PR #1327 — IMPACT report

Source: [HTTPie PR #1327](https://github.com/httpie/cli/pull/1327) at commit `17ec3be65129`.

IMPACT indexed 956 Python functions and 876 call edges in the PR checkout.
The paths below indicate possible impact. The 18 graph-selected test targets expanded to 43 pytest cases. In an isolated
run, **34 passed and 9 remote-service cases were skipped**; none failed.

## PR impact report

### `httpie/cookies.py::HTTPieCookiePolicy.return_ok_secure` (lines 9-20)
Nothing in the repo calls this function.

### `httpie/cookies.py::HTTPieCookiePolicy._is_local_host` (lines 22-25)
- Potentially reaches **1** callers (1 direct), including **0** tests
- Longest chain (1 hops): `cookies:HTTPieCookiePolicy.return_ok_secure` → `cookies:HTTPieCookiePolicy._is_local_host`

### `httpie/sessions.py::Session.__init__` (lines 128-156)
- Potentially reaches **21** callers (3 direct), including **13** tests
- Longest chain (4 hops): `sessions:cli_sessions` → `sessions:cli_upgrade_all_sessions` → `sessions:upgrade_session` → `sessions:get_httpie_session` → `sessions:Session.__init__`
- Relevant tests: `tests/test_sessions.py::TestExpiredCookies::test_removes_expired_cookies_from_session_obj`, `tests/test_sessions.py::test_cookie_security_warnings_on_raw_cookies`, `tests/test_sessions.py::test_headers_old_layout_warning`, `tests/test_sessions.py::test_old_session_cookie_layout_loading`, `tests/test_sessions.py::test_old_session_cookie_layout_warning`, `tests/test_sessions.py::test_old_session_header_layout_loading`, `tests/test_sessions.py::test_old_session_version_saved_as_is`, `tests/test_sessions.py::test_outdated_layout_mixed`, `tests/test_sessions.py::test_secure_cookies_on_localhost`, `tests/test_sessions.py::test_session_cookie_layout_preservation`

### `tests/conftest.py::_remote_httpbin_available` (lines 62-68)
Nothing in the repo calls this function.

### `tests/conftest.py::remote_httpbin` (lines 71-75)
Nothing in the repo calls this function.

### `tests/test_cookie_on_redirects.py::_stringify` (lines 5-6)
- Potentially reaches **5** callers (5 direct), including **5** tests
- Longest chain (1 hops): `test_cookie_on_redirects:test_explicit_user_set_cookie` → `test_cookie_on_redirects:_stringify`
- Relevant tests: `tests/test_cookie_on_redirects.py::test_explicit_user_set_cookie`, `tests/test_cookie_on_redirects.py::test_explicit_user_set_cookie_in_session`, `tests/test_cookie_on_redirects.py::test_explicit_user_set_headers`, `tests/test_cookie_on_redirects.py::test_saved_session_cookies_on_redirect`, `tests/test_cookie_on_redirects.py::test_saved_user_set_cookie_in_session`

### `tests/test_sessions.py::test_secure_cookies_on_localhost` (lines 805-836)
This test changed directly and was included in the selected test run.

### `tests/utils/http_server.py::get_cookies` (lines 91-105)
Nothing in the repo calls this function.

### `tests/utils/http_server.py::set_cookies` (lines 108-116)
Nothing in the repo calls this function.

### `tests/utils/http_server.py::_http_server` (lines 132-139)
- Potentially reaches **2** callers (2 direct), including **0** tests
- Longest chain (1 hops): `http_server:http_server` → `http_server:_http_server`

### `tests/utils/http_server.py::http_server` (lines 142-149)
Nothing in the repo calls this function.

### `tests/utils/http_server.py::localhost_http_server` (lines 152-158)
Nothing in the repo calls this function.

## Selected test run

Ran 18 selected pytest targets in an isolated Python 3.11 environment. The 43 parameterized cases produced **34 passed, 9 skipped, 0 failed**. Outside network access was disabled; cases that require the remote `pie.dev` service were skipped. Local server cases ran.

- **PARTIAL** (1 passed, 1 skipped): `tests/test_cookie_on_redirects.py::test_explicit_user_set_cookie`
- **PARTIAL** (1 passed, 1 skipped): `tests/test_cookie_on_redirects.py::test_explicit_user_set_cookie_in_session`
- **PARTIAL** (2 passed, 2 skipped): `tests/test_cookie_on_redirects.py::test_explicit_user_set_headers`
- **PARTIAL** (1 passed, 3 skipped): `tests/test_cookie_on_redirects.py::test_saved_session_cookies_on_redirect`
- **PARTIAL** (1 passed, 1 skipped): `tests/test_cookie_on_redirects.py::test_saved_user_set_cookie_in_session`
- **PASSED** (2 passed): `tests/test_sessions.py::TestExpiredCookies::test_removes_expired_cookies_from_session_obj`
- **PASSED** (8 passed): `tests/test_sessions.py::test_cookie_security_warnings_on_raw_cookies`
- **PASSED** (4 passed): `tests/test_sessions.py::test_headers_old_layout_warning`
- **PASSED** (1 passed): `tests/test_sessions.py::test_old_session_cookie_layout_loading`
- **PASSED** (1 passed): `tests/test_sessions.py::test_old_session_cookie_layout_warning`
- **PASSED** (1 passed): `tests/test_sessions.py::test_old_session_header_layout_loading`
- **PASSED** (1 passed): `tests/test_sessions.py::test_old_session_version_saved_as_is`
- **PASSED** (1 passed): `tests/test_sessions.py::test_outdated_layout_mixed`
- **PARTIAL** (1 passed, 1 skipped): `tests/test_sessions.py::test_secure_cookies_on_localhost`
- **PASSED** (2 passed): `tests/test_sessions.py::test_session_cookie_layout_preservation`
- **PASSED** (2 passed): `tests/test_sessions.py::test_session_cookie_layout_preservation_on_new_cookies`
- **PASSED** (2 passed): `tests/test_sessions.py::test_session_header_layout_preservation`
- **PASSED** (2 passed): `tests/test_sessions.py::test_session_header_layout_preservation_on_new_headers`

The changed `test_secure_cookies_on_localhost` passed with the local server; its remote-service variant was skipped. The results above are observed pytest outcomes, while graph paths represent possible impact.
