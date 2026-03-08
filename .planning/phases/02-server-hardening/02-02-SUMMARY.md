---
phase: 02-server-hardening
plan: 02
subsystem: server
tags: [flask, validation, escpos, error-handling, input-validation, max-content-length]

# Dependency graph
requires:
  - phase: 02-server-hardening
    plan: 01
    provides: "Formatter with try/finally state safety and font_b_text() method"
provides:
  - "Input validation on all 6 JSON endpoints via _require_fields() helper"
  - "MAX_CONTENT_LENGTH 10MB limit preventing OOM on oversized requests"
  - "ESC@ printer state reset (hw('INIT')) before every print job in with_retry()"
  - "Consistent JSON error format: {error, field?} via error_response() helper"
  - "13 integration tests covering validation, 413, error format, and static checks"
affects: [04-test-suite]

# Tech tracking
tech-stack:
  added: []
  patterns: ["_require_fields() validation before with_retry() in each endpoint", "error_response() for all 400/413 error returns"]

key-files:
  created:
    - tests/test_server.py
  modified:
    - print_server.py
    - tests/conftest.py

key-decisions:
  - "Used silent=True on get_json() so invalid JSON returns None (caught by _require_fields) instead of raising 400 before our validation"
  - "error_response() includes optional 'field' key only when relevant (omitted for generic errors like invalid JSON)"

patterns-established:
  - "Validation pattern: get_json(force=True, silent=True) -> _require_fields(data, *fields) -> error_response() on failure"
  - "Flask test fixture: conftest.py app/client fixtures with Dummy printer for zero-hardware testing"

requirements-completed: [REL-01, REL-02, REL-04, QUAL-06]

# Metrics
duration: 3min
completed: 2026-03-09
---

# Phase 2 Plan 2: Server Input Validation and Error Consistency Summary

**Input validation with _require_fields() on all 6 JSON endpoints, 10MB MAX_CONTENT_LENGTH, ESC@ init in with_retry(), and consistent error_response() format**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-08T23:04:45Z
- **Completed:** 2026-03-08T23:08:15Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added _require_fields() and error_response() helpers for structured input validation and consistent error returns
- All 6 JSON endpoints validate required fields before calling with_retry(), returning 400 with field name on failure
- Set MAX_CONTENT_LENGTH to 10MB, preventing OOM from oversized POST bodies (returns 413)
- Added ESC@ printer state reset (fmt.p.hw("INIT")) at the start of every print job in with_retry()
- Replaced raw ESC/POS _raw() byte commands in /print/image with font_b_text()
- Standardized all error responses across file upload and JSON endpoints to use error_response()
- Created 13 integration tests using Flask test client with Dummy printer

## Task Commits

Each task was committed atomically:

1. **Task 1: Add validation, MAX_CONTENT_LENGTH, ESC@ init, error format, replace raw bytes** - `fed2a99` (feat)
2. **Task 2: Write integration tests for validation, 413, error format, and ESC@ init** - `c7aa0aa` (test)

## Files Created/Modified
- `print_server.py` - Added _require_fields(), error_response(), MAX_CONTENT_LENGTH, ESC@ in with_retry(), validation on all endpoints, replaced _raw() with font_b_text()
- `tests/test_server.py` - 13 integration tests: 6 missing-field validation, 2 bad-JSON, 1 oversized request, 1 valid request, 2 error format, 1 static _raw check
- `tests/conftest.py` - Added app and client fixtures for Flask test client with Dummy printer

## Decisions Made
- Used get_json(force=True, silent=True) so that invalid JSON returns None instead of Flask's default 400, allowing _require_fields() to catch it with a consistent error message
- error_response() only includes the "field" key when a specific field name is relevant (not for generic "invalid JSON" errors)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Server now validates all input and returns consistent errors -- ready for graceful shutdown work in 02-03
- Full test suite is at 41 tests (28 pre-existing + 13 new server tests), all passing

## Self-Check: PASSED

- [x] print_server.py exists and contains _require_fields
- [x] tests/test_server.py exists
- [x] tests/conftest.py updated with app/client fixtures
- [x] Commit fed2a99 (Task 1) exists
- [x] Commit c7aa0aa (Task 2) exists
- [x] 41/41 tests pass
- [x] No _raw() calls in print_server.py

---
*Phase: 02-server-hardening*
*Completed: 2026-03-09*
