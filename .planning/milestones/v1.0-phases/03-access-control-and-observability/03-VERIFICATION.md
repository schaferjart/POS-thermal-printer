---
phase: 03-access-control-and-observability
verified: 2026-03-09T01:00:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 3: Access Control and Observability Verification Report

**Phase Goal:** Print endpoints require an API key and the health endpoint reports real printer status
**Verified:** 2026-03-09
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Sending a print request without X-Print-Key header returns 401 when api_key is configured | VERIFIED | `check_api_key` at line 115 of print_server.py uses `hmac.compare_digest`; returns `error_response(..., status=401)` at line 124. Test `test_no_key_returns_401` passes. |
| 2 | Sending a print request with the correct X-Print-Key header succeeds when api_key is configured | VERIFIED | `check_api_key` returns None (allows through) when `hmac.compare_digest` matches. Test `test_correct_key_returns_200` passes. |
| 3 | GET /health and GET / respond 200 without any API key even when api_key is configured | VERIFIED | `_PUBLIC_ENDPOINTS = frozenset({"health", "index", "static"})` at line 69; `check_api_key` returns early for these endpoints. Tests `test_health_no_key_returns_200` and `test_index_no_key_returns_200` both pass. |
| 4 | When no api_key is set in config.yaml, all endpoints work without authentication | VERIFIED | `check_api_key` returns early on `not api_key` (lines 118-119). config.yaml has `api_key` commented out by default (line 19). Test `test_no_key_config_allows_all` passes. |
| 5 | GET /health returns JSON with printer field showing connected, disconnected, or dummy | VERIFIED | Health endpoint (lines 359-374) tries `_printer.is_online()`, catches `NotImplementedError` -> "dummy", other exceptions -> "disconnected". Tests `test_health_has_printer_field` and `test_health_dummy_mode_printer_status` pass. |
| 6 | GET /health returns JSON with uptime_seconds and last_print fields | VERIFIED | Health endpoint returns `uptime_seconds` (line 365) computed from `_server_start_time` and `last_print` (line 366) from `_last_print_time`. Both set in `main()` and test fixtures. Tests `test_health_has_uptime_field` and `test_health_has_last_print_field` pass. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `print_server.py` | before_request auth hook, enhanced health endpoint, server_start_time and last_print_time tracking | VERIFIED | `check_api_key` (line 115), `_PUBLIC_ENDPOINTS` (line 69), enhanced `health()` (line 359), `_server_start_time` (line 66), `_last_print_time` (line 67), `hmac` import (line 35), `datetime` import (line 43). All substantive, no stubs. |
| `tests/test_server.py` | Auth and health test classes | VERIFIED | `TestAuth` (5 tests, lines 219-250), `TestAuthDisabled` (1 test, lines 253-258), `TestHealthEnhanced` (4 tests, lines 261-283). All 10 tests pass. |
| `tests/conftest.py` | client_with_auth fixture | VERIFIED | `client_with_auth` fixture (lines 62-73) sets `api_key: "test-secret-key"` in config and initializes `_server_start_time`. |
| `config.yaml` | Commented-out api_key example under server section | VERIFIED | Line 19: `# api_key: "your-secret-key-here"  # Uncomment to enable auth` |
| `CLAUDE.md` | Auth documentation in Key patterns and HTTP server sections | VERIFIED | Line 27: X-Print-Key curl instructions. Line 60: API key auth pattern with `_PUBLIC_ENDPOINTS` documentation. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `print_server.py` | `config.yaml` | `_config['server']['api_key'] lookup` | WIRED | Line 117: `_config.get("server", {}).get("api_key")` |
| `print_server.py (check_api_key)` | `print_server.py (error_response)` | returns 401 via error_response | WIRED | Line 124: `return error_response("Invalid or missing API key", status=401)` |
| `print_server.py (with_retry)` | `print_server.py (_last_print_time)` | updates timestamp after successful print | WIRED | Line 135 (initial try) and line 142 (retry path) both set `_last_print_time = datetime.now(timezone.utc).isoformat()` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| AUTH-01 | 03-01-PLAN | Server checks X-Print-Key header against key in config.yaml on all print endpoints | SATISFIED | `check_api_key` before_request hook at line 114-124 of print_server.py; uses `hmac.compare_digest` for timing-safe comparison |
| AUTH-02 | 03-01-PLAN | /health and / endpoints accessible without API key | SATISFIED | `_PUBLIC_ENDPOINTS` frozenset at line 69; `check_api_key` returns early for these endpoints (line 120-121) |
| AUTH-03 | 03-01-PLAN | No api_key configured = auth disabled (backwards compatible) | SATISFIED | Lines 118-119: `if not api_key: return`; config.yaml has api_key commented out by default |
| OBS-01 | 03-01-PLAN | /health reports printer connection status (connected/disconnected) | SATISFIED | Lines 368-373: tries `_printer.is_online()`, handles NotImplementedError (dummy) and other exceptions (disconnected) |
| OBS-02 | 03-01-PLAN | /health reports server uptime and last successful print timestamp | SATISFIED | Line 365: `uptime_seconds` from `_server_start_time`; Line 366: `last_print` from `_last_print_time` updated in `with_retry` |

No orphaned requirements found. All 5 requirement IDs from REQUIREMENTS.md mapped to Phase 3 (AUTH-01, AUTH-02, AUTH-03, OBS-01, OBS-02) are accounted for in the plan and verified as satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | - | - | - | No anti-patterns detected |

No TODO/FIXME/PLACEHOLDER comments, no stub implementations, no empty handlers found in any modified file.

### Human Verification Required

### 1. API Key Rejection on Live Server

**Test:** Start server with `api_key: "test123"` in config.yaml, send `curl -X POST http://localhost:9100/print/message -H "Content-Type: application/json" -d '{"text":"hi"}'` without X-Print-Key header.
**Expected:** 401 response with `{"error": "Invalid or missing API key"}`
**Why human:** Verifies the full HTTP stack including Flask middleware in a real server process, not just test client.

### 2. Health Endpoint with Real Printer

**Test:** Start server connected to real printer, run `curl http://localhost:9100/health | python -m json.tool`
**Expected:** JSON with `"printer": "connected"`, `"uptime_seconds"` as a positive number, `"last_print": null` (before any prints)
**Why human:** `is_online()` behavior depends on real USB hardware; dummy mode always returns "dummy".

### 3. Last Print Timestamp Updates

**Test:** With server running, send a valid print request, then check `/health` again.
**Expected:** `"last_print"` changes from `null` to an ISO 8601 timestamp string.
**Why human:** Requires a live server with state changing between requests.

### Gaps Summary

No gaps found. All 6 observable truths are verified. All 5 artifacts pass three-level verification (exists, substantive, wired). All 3 key links are confirmed wired. All 5 requirements are satisfied. No anti-patterns detected. All 55 tests pass (1 skipped due to optional numpy dependency). All 3 commits from SUMMARY verified in git log.

---

_Verified: 2026-03-09_
_Verifier: Claude (gsd-verifier)_
