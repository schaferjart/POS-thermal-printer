# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-03-09
**Phases:** 4 | **Plans:** 8 | **Sessions:** ~3

### What Was Built
- Shared utility library (helpers.py) eliminating code duplication across 5 modules
- Server hardening: input validation, state safety guards, error consistency, graceful shutdown
- Optional API key authentication with timing-safe comparison
- Enhanced health endpoint for monitoring
- 89-test pytest suite covering rendering, dithering, validation, and auth

### What Worked
- TDD approach (write failing tests first, then implement) caught issues early and produced clean implementations
- Wave-based parallel execution — Plans 04-01 and 04-02 ran simultaneously, cutting test suite phase time in half
- Small, focused plans (2-3 tasks each) completed in 2-5 minutes average — predictable velocity
- Hand-rolled validation over external dependencies — simpler, testable, zero new deps
- Phase ordering (foundation → hardening → auth → tests) meant each phase built cleanly on the previous

### What Was Inefficient
- VALIDATION.md files were created for Nyquist compliance but never formally signed off — added ceremony without value for this project's size
- Phase 3 had only 1 plan — could have been combined with Phase 2 for fewer context switches
- Roadmap progress table got stale between phase completions (Phase 3 and 4 showed "In progress" / "Not started" even after completion)

### Patterns Established
- `_PUBLIC_ENDPOINTS` frozenset pattern for auth exemption — extend for future public routes
- `error_response()` helper for consistent JSON error format across all endpoints
- `with_retry()` wrapper that handles reconnection, ESC@ init, and timestamp tracking
- Tests use synthetic PIL images and Dummy printer — zero hardware dependency
- Bundled fonts (Burra) for cross-platform test reliability

### Key Lessons
1. Hardening before features is the right order — fixing the foundation first prevented compounding fragility
2. For a project this size (5 source files, 1 printer), lightweight tooling beats heavy frameworks — hand-rolled validation, no ORM, no dependency injection
3. The "no pixel comparison" rule for image tests (check mode/width/height only) prevents platform-dependent flakiness
4. Always close the old USB connection before reconnecting or you get "Resource busy" errors

### Cost Observations
- Model mix: ~80% opus (execution), ~20% sonnet (verification, plan checking)
- Sessions: ~3 (research+plan, execute phases 1-3, execute phase 4 + milestone)
- Notable: Parallel plan execution in Phase 4 saved ~3 minutes; total milestone execution under 30 minutes

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~3 | 4 | Established TDD, wave parallelism, hand-rolled validation |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | 89 | Core paths | 0 (only pytest added) |

### Top Lessons (Verified Across Milestones)

1. Small plans (2-3 tasks) with atomic commits are more predictable than large plans
2. Foundation-first ordering prevents rework in later phases
