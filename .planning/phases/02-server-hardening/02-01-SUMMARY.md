---
phase: 02-server-hardening
plan: 01
subsystem: printer
tags: [escpos, formatter, try-finally, state-safety, font-b]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "helpers.py shared utilities, config validation"
provides:
  - "Formatter with try/finally state safety guards on all 10 state-changing methods"
  - "font_b_text() method encapsulating raw ESC/POS Font B commands behind Formatter API"
  - "12 unit tests proving state reset on exception"
affects: [02-server-hardening, 04-test-suite]

# Tech tracking
tech-stack:
  added: []
  patterns: ["try/finally guards on all Formatter methods that change printer state"]

key-files:
  created:
    - tests/test_formatter.py
  modified:
    - printer_core.py

key-decisions:
  - "Strengthened tests to use MagicMock on p.set() to verify reset calls actually happen on exception, not just that subsequent operations succeed"
  - "Placed font_b_text() between small() and right() in Formatter since both small() and font_b_text() deal with Font B"

patterns-established:
  - "try/finally guard pattern: set state -> try: operation -> finally: reset state"
  - "Test pattern: mock p.set as MagicMock, mock operation to raise, assert reset call in call_args_list"

requirements-completed: [REL-03, QUAL-04]

# Metrics
duration: 3min
completed: 2026-03-09
---

# Phase 2 Plan 1: Formatter State Safety Summary

**try/finally guards on all 10 state-changing Formatter methods plus font_b_text() method for Font B printing**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-08T22:57:58Z
- **Completed:** 2026-03-09T00:01:41Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Wrapped all 10 state-changing Formatter methods (title, subtitle, center, bold, italic_text, small, right, left_right_bold, qr, barcode) with try/finally guards
- Added font_b_text() method that sets Font B + normal_textsize, prints, and resets to Font A -- replaces raw ESC/POS bytes in print_server.py
- Created 12 unit tests verifying state reset on exception for every guarded method

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for Formatter state safety** - `1113aab` (test)
2. **Task 1 (GREEN): Implement try/finally guards and font_b_text** - `a5d4ab6` (feat)

_TDD task: RED commit has failing tests, GREEN commit has implementation passing all tests._

## Files Created/Modified
- `tests/test_formatter.py` - 12 tests: 10 for state reset on exception, 2 for font_b_text normal and exception paths
- `printer_core.py` - try/finally guards on 10 methods, new font_b_text() method

## Decisions Made
- Strengthened tests to use MagicMock on p.set() and inspect call_args_list, rather than weak tests that just call methods after exception (which pass even without try/finally on Dummy printer)
- font_b_text() placed between small() and right() in the class since it's conceptually related to Font B

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Initial test design was too weak -- tests passed without try/finally because Dummy printer doesn't maintain internal state that would break subsequent operations. Strengthened to mock p.set() as MagicMock and assert the reset call appears in call_args_list even when the operation raises.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Formatter is now state-safe -- print_server.py can use font_b_text() instead of raw ESC/POS bytes (02-02-PLAN.md)
- Ready for input validation, MAX_CONTENT_LENGTH, and error consistency work in 02-02

## Self-Check: PASSED

- [x] printer_core.py exists
- [x] tests/test_formatter.py exists
- [x] 02-01-SUMMARY.md exists
- [x] Commit 1113aab (RED) exists
- [x] Commit a5d4ab6 (GREEN) exists
- [x] 28/28 tests pass

---
*Phase: 02-server-hardening*
*Completed: 2026-03-09*
