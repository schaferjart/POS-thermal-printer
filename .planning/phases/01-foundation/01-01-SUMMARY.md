---
phase: 01-foundation
plan: 01
subsystem: code-quality
tags: [python, pillow, refactoring, deduplication, pytest]

# Dependency graph
requires: []
provides:
  - "helpers.py with resolve_font_path, wrap_text, open_image shared utilities"
  - "tests/test_helpers.py with 8 passing unit tests"
  - "pytest test infrastructure (conftest.py, requirements.txt)"
affects: [01-foundation-plan-02, testing, all-rendering-modules]

# Tech tracking
tech-stack:
  added: [pytest]
  patterns: [shared-helpers-module, zero-project-imports-constraint]

key-files:
  created: [helpers.py, tests/test_helpers.py, tests/conftest.py, tests/__init__.py]
  modified: [templates.py, md_renderer.py, image_printer.py, image_slicer.py, portrait_pipeline.py, requirements.txt]

key-decisions:
  - "helpers.py imports only stdlib + Pillow (no project imports) to prevent circular dependencies"
  - "wrap_text returns [''] for empty input (not empty list) for safe downstream iteration"
  - "md_renderer keeps local wrap_text closure to preserve hard_wrap branch, delegates soft-wrap to helpers"
  - "Removed unused imports (os from templates.py, textwrap from templates.py, ImageOps from image_slicer.py and portrait_pipeline.py)"

patterns-established:
  - "Shared utility pattern: common functions live in helpers.py, consumers import from it"
  - "TDD workflow: RED (failing tests) -> GREEN (implementation) -> REFACTOR"
  - "Zero-import constraint: helpers.py never imports project modules"

requirements-completed: [QUAL-01, QUAL-02, QUAL-03]

# Metrics
duration: 6min
completed: 2026-03-08
---

# Phase 1 Plan 01: Extract Shared Utilities Summary

**Three duplicated utilities (resolve_font_path, wrap_text, open_image) extracted to helpers.py, all 5 consumers updated, 8 unit tests passing**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-08T16:50:16Z
- **Completed:** 2026-03-08T16:56:43Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Created helpers.py with resolve_font_path, wrap_text, and open_image -- single source of truth for all three utilities
- Updated all 5 consumer files (templates.py, md_renderer.py, image_printer.py, image_slicer.py, portrait_pipeline.py) to import from helpers
- Eliminated ~75 lines of duplicated code across the codebase
- Established pytest test infrastructure with 8 passing tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Create helpers.py and test scaffold (TDD)**
   - `120de76` (test): add failing tests for helpers.py utility functions
   - `9ee2448` (feat): create helpers.py with resolve_font_path, wrap_text, open_image
2. **Task 2: Update all consumers to import from helpers.py** - `828515b` (refactor)

## Files Created/Modified
- `helpers.py` - New shared utility module with resolve_font_path, wrap_text, open_image
- `tests/__init__.py` - Test package marker
- `tests/conftest.py` - Shared fixtures: sample images, small_font
- `tests/test_helpers.py` - 8 unit tests covering all three utility functions
- `templates.py` - Imports from helpers; removed _resolve_font_path, wrap_text closure, font constants
- `md_renderer.py` - Imports from helpers; removed _resolve_font_path, font constants; delegates soft-wrap
- `image_printer.py` - Imports open_image; replaced inline EXIF+alpha block
- `image_slicer.py` - Imports open_image; removed _open function and ImageOps import
- `portrait_pipeline.py` - Imports open_image; replaced two inline EXIF+alpha blocks
- `requirements.txt` - Added pytest>=7.0

## Decisions Made
- helpers.py uses zero project imports (only stdlib + Pillow) to prevent circular dependencies
- md_renderer.py keeps a local wrap_text closure that delegates soft-wrap to helpers but preserves the hard_wrap branch for acidic style
- Removed unused imports discovered during refactoring (os, textwrap from templates.py; ImageOps from image_slicer.py and portrait_pipeline.py)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- helpers.py provides the shared utility foundation for all subsequent phases
- pytest infrastructure is ready for Phase 4 test suite expansion
- All consumer files are cleaner and ready for Phase 2 hardening work

## Self-Check: PASSED

- All 4 created files exist (helpers.py, tests/test_helpers.py, tests/conftest.py, tests/__init__.py)
- All 3 commit hashes verified (120de76, 9ee2448, 828515b)
- All 8 unit tests pass
- Smoke tests pass (--dummy test, --dummy md)

---
*Phase: 01-foundation*
*Completed: 2026-03-08*
