---
phase: 02-server-hardening
plan: 03
subsystem: server
tags: [signal-handling, sigterm, config-safety, portrait-pipeline]

# Dependency graph
requires:
  - phase: 02-server-hardening
    provides: "Input validation, error consistency, Formatter state safety"
provides:
  - "graceful_shutdown signal handler for SIGTERM/SIGINT"
  - "Config-safe portrait pipeline (no shared dict mutation)"
affects: [test-suite, pi-deployment]

# Tech tracking
tech-stack:
  added: []
  patterns: ["signal handler cleanup pattern (no lock acquisition)", "explicit override parameters instead of config mutation"]

key-files:
  created: []
  modified: [print_server.py, portrait_pipeline.py, tests/test_server.py]

key-decisions:
  - "Do not acquire _print_lock in signal handler to avoid deadlock"
  - "Pass blur/dither_mode as explicit override parameters rather than mutating shared config dict"

patterns-established:
  - "Signal handlers close resources directly without acquiring locks"
  - "Override parameters passed explicitly through call chain instead of mutating shared state"

requirements-completed: [REL-05, QUAL-05]

# Metrics
duration: 3min
completed: 2026-03-09
---

# Phase 2 Plan 3: Graceful Shutdown and Config Safety Summary

**SIGTERM/SIGINT signal handler for clean mDNS+printer shutdown, and portrait pipeline config mutation fix using explicit override parameters**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-08T23:11:18Z
- **Completed:** 2026-03-08T23:14:10Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added graceful_shutdown handler that deregisters mDNS and closes printer on SIGTERM/SIGINT
- Removed config dict mutation in portrait_pipeline.run_pipeline -- overrides now passed as explicit parameters
- Added 5 new tests verifying shutdown handler and config safety (plus 1 skip on macOS due to numpy)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add SIGTERM handler and fix portrait config mutation** - `937e7fd` (feat)
2. **Task 2: Add tests for config mutation fix and verify SIGTERM handler exists** - `fc577ed` (test)

## Files Created/Modified
- `print_server.py` - Added `import signal`, `graceful_shutdown()` function, and signal registration in `main()`
- `portrait_pipeline.py` - Removed config mutation in `run_pipeline()`, added `blur_override`/`dither_mode_override` params to `print_portrait()`
- `tests/test_server.py` - Added TestGracefulShutdown (3 tests) and TestPortraitConfigNotMutated (2 tests)

## Decisions Made
- Do not acquire `_print_lock` in signal handler -- signal may arrive while a print job holds the lock, which would deadlock. Just close resources directly since the process is exiting.
- Pass blur/dither_mode as explicit override parameters through the call chain rather than mutating the shared `_config` dict. This prevents state leaks between requests when the server handles consecutive portrait requests with different parameters.
- Use `pytest.importorskip("numpy")` for the runtime config mutation test since portrait_pipeline requires numpy which is only installed on the Pi.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 (Server Hardening) is now complete -- all 3 plans done
- All success criteria met: input validation, Formatter state safety, graceful shutdown, error consistency
- Ready for Phase 3 (Access Control and Observability)
- Note: Full SIGTERM verification requires `systemctl stop pos-printer` on the Pi (REL-05 manual validation)

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 02-server-hardening*
*Completed: 2026-03-09*
