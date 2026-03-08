---
phase: 03-access-control-and-observability
plan: 01
subsystem: auth
tags: [api-key, hmac, health-endpoint, flask-before-request, observability]

# Dependency graph
requires:
  - phase: 02-server-hardening
    provides: "error_response helper, with_retry wrapper, input validation"
provides:
  - "Optional API key auth via X-Print-Key header and before_request hook"
  - "Enhanced /health endpoint with printer status, uptime, and last_print"
  - "_PUBLIC_ENDPOINTS frozenset pattern for exempting routes from auth"
affects: [stress-test-updates, rate-limiting, api-documentation]

# Tech tracking
tech-stack:
  added: [hmac]
  patterns: [before_request-auth-hook, public-endpoint-frozenset, timing-constant-comparison]

key-files:
  created: []
  modified: [print_server.py, config.yaml, tests/conftest.py, tests/test_server.py, CLAUDE.md]

key-decisions:
  - "hmac.compare_digest for timing-safe key comparison (prevents timing attacks)"
  - "_PUBLIC_ENDPOINTS frozenset for O(1) lookup and immutability"
  - "api_key commented out by default in config.yaml -- backwards compatible, zero breaking changes"
  - "_server_start_time set in both main() and test fixtures for consistent health endpoint behavior"

patterns-established:
  - "Public endpoint exemption: add endpoint name to _PUBLIC_ENDPOINTS frozenset"
  - "Auth header convention: X-Print-Key custom header"

requirements-completed: [AUTH-01, AUTH-02, AUTH-03, OBS-01, OBS-02]

# Metrics
duration: 3min
completed: 2026-03-09
---

# Phase 3 Plan 1: Auth and Health Summary

**Optional API key auth via X-Print-Key header with hmac.compare_digest, plus enhanced /health endpoint returning printer status, uptime, and last print timestamp**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-08T23:41:26Z
- **Completed:** 2026-03-08T23:44:36Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- API key authentication gate on all /print/* and /portrait/* endpoints via before_request hook
- /health and / endpoints exempted from auth via _PUBLIC_ENDPOINTS frozenset
- Backwards compatible: no api_key in config = all endpoints open
- Enhanced /health returns printer connected/disconnected/dummy, uptime_seconds, last_print ISO timestamp
- 10 new tests covering auth and health behaviors, full suite 55 passed

## Task Commits

Each task was committed atomically:

1. **Task 1: Add API key auth and enhanced health endpoint** (TDD)
   - `f430363` (test: failing tests for auth and health)
   - `8b96ee7` (feat: implementation passing all tests)
2. **Task 2: Verify full test suite and update CLAUDE.md** - `6d30105` (docs)

## Files Created/Modified
- `print_server.py` - Added check_api_key before_request hook, _PUBLIC_ENDPOINTS, enhanced health(), _server_start_time/_last_print_time tracking
- `config.yaml` - Added commented-out api_key example under server section
- `tests/conftest.py` - Added client_with_auth fixture, _server_start_time in app fixture
- `tests/test_server.py` - Added TestAuth, TestAuthDisabled, TestHealthEnhanced classes (10 tests)
- `CLAUDE.md` - Documented auth pattern, X-Print-Key header usage, updated test instructions

## Decisions Made
- Used hmac.compare_digest for timing-safe API key comparison (prevents timing side-channel attacks)
- _PUBLIC_ENDPOINTS as frozenset for immutability and O(1) lookup
- api_key commented out by default in config.yaml to maintain zero-config backwards compatibility
- _server_start_time set in both main() and test fixtures so health endpoint works in all contexts

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Auth infrastructure in place, ready to be enabled by uncommenting api_key in config.yaml
- _PUBLIC_ENDPOINTS pattern established for future public endpoint additions
- Health endpoint provides observability for monitoring and dashboards

## Self-Check: PASSED

All files found. All commits verified (f430363, 8b96ee7, 6d30105).

---
*Phase: 03-access-control-and-observability*
*Completed: 2026-03-09*
