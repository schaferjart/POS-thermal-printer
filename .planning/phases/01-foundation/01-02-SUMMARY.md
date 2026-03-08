---
phase: 01-foundation
plan: 02
subsystem: server
tags: [config-validation, fail-fast, printer-core, startup]

# Dependency graph
requires:
  - phase: 01-foundation plan 01
    provides: helpers.py shared utilities, test infrastructure
provides:
  - validate_config function in printer_core.py
  - config validation wired into print_server.py startup
  - unit tests for config validation (tests/test_config.py)
affects: [server-hardening, test-suite]

# Tech tracking
tech-stack:
  added: []
  patterns: [fail-fast config validation at startup, hand-rolled validation over pydantic]

key-files:
  created: [tests/test_config.py]
  modified: [printer_core.py, print_server.py]

key-decisions:
  - "Hand-rolled validation (dict traversal + sys.exit) -- zero new dependencies, ~20 lines"
  - "Reports ALL missing keys in one pass, not just the first"
  - "Uses [FATAL] prefix and names exact dotted key path in error message"

patterns-established:
  - "Config validation: required keys defined as dotted-path tuples, checked via dict traversal"
  - "Fail-fast: validation runs before printer connection to avoid dangling USB handles"

requirements-completed: [REL-06]

# Metrics
duration: 4min
completed: 2026-03-08
---

# Phase 1 Plan 2: Config Validation Summary

**Hand-rolled config validation with fail-fast startup -- validates printer.vendor_id, printer.product_id, printer.paper_width, server.port before any USB connection**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-08T16:59:37Z
- **Completed:** 2026-03-08T17:03:45Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- validate_config function in printer_core.py checks 4 required config keys
- Server now fails fast with clear "[FATAL] config.yaml: missing required key 'X'" before attempting USB connection
- 8 unit tests covering valid config, individual missing keys, missing sections, multiple missing keys, empty config
- Full test suite now at 16 tests, all passing

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): Failing tests for config validation** - `81d53b5` (test)
2. **Task 1 (TDD GREEN): Implement validate_config** - `3900c39` (feat)
3. **Task 2: Wire validate_config into server startup** - `b24918f` (feat)

## Files Created/Modified
- `tests/test_config.py` - 8 unit tests for validate_config (valid, missing keys, empty config)
- `printer_core.py` - Added validate_config function and sys import
- `print_server.py` - Added validate_config import and call in main()

## Decisions Made
- Hand-rolled validation (dict traversal + sys.exit) per locked decision from research -- zero new dependencies, ~20 lines
- Reports ALL missing keys in one pass rather than failing on the first
- Uses `[FATAL]` prefix and names exact dotted key path (e.g., `printer.vendor_id`) in error message
- Validation runs before printer connection attempt to avoid dangling USB handles on bad config

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- venv had stale paths from previous directory location -- recreated venv (not a plan deviation, just environment setup)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 1 complete: helpers.py extracted (plan 01) and config validation added (plan 02)
- Ready for Phase 2: Server Hardening (input validation, Formatter state safety, graceful shutdown)
- No blockers

## Self-Check: PASSED

All files exist, all commits verified, validate_config function and wiring confirmed, 8/8 config tests collected.

---
*Phase: 01-foundation*
*Completed: 2026-03-08*
