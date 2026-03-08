# Project Research Summary

**Project:** POS Thermal Print Server Hardening
**Domain:** Embedded appliance server hardening (Flask + ESC/POS on Raspberry Pi)
**Researched:** 2026-03-08
**Confidence:** HIGH

## Executive Summary

This project is a hardening milestone for an existing, working thermal print server running on a Raspberry Pi 3. The server (Flask, python-escpos, Pillow) already handles 8 print templates over HTTP and CLI, but has no input validation, no authentication, no request size limits, and fragile printer state management. Every POST endpoint can be crashed with a malformed request body (500 KeyError), and the server is open to any device on the network. These are not hypothetical risks -- they were confirmed in stress testing and codebase analysis.

The recommended approach is surgical hardening, not restructuring. The flat module architecture (8 Python files) is appropriate for this scale and should be preserved. Two new modules (`validators.py` for request validation and auth, `helpers.py` for deduplicated utilities) plus a `tests/` directory address all identified reliability gaps. The existing stack stays; three production dependencies are added (pydantic, Flask-Pydantic, Flask-Limiter) totaling ~5MB disk and ~3MB runtime memory -- well within the Pi's 400MB systemd budget. There is a disagreement between STACK and ARCHITECTURE research on whether to use pydantic or hand-rolled validation. Given the small number of schemas (~10 endpoints) and Pi constraints, **hand-rolled validation functions are the right call** -- they add zero dependencies, are trivially testable, and the validation logic totals ~50 lines. Use pydantic only if validation complexity grows significantly.

The top risks are: (1) USB printer state becoming permanently wedged after mid-print exceptions (no try/finally guards exist), (2) memory exhaustion from unbounded request sizes on a 1GB RAM device, (3) SD card corruption from excessive writes over months of uptime, and (4) stale mDNS/dirty USB on shutdown because Flask's dev server does not reliably trigger atexit handlers. All have straightforward, well-documented mitigations that can be implemented incrementally.

## Key Findings

### Recommended Stack

The existing stack (Flask 3.1.3, Pillow 12.1.1, python-escpos 3.1, PyYAML 6.0.3, Python 3.13 on Debian Trixie) is stable and stays unchanged. Additions are minimal and targeted. See [STACK.md](STACK.md) for full rationale.

**Additions for hardening:**
- **Flask-Limiter 4.1.1:** Rate limiting with in-memory storage -- no Redis needed for single-process server. Prevents runaway scripts from draining paper rolls.
- **pytest 9.0.2 + pytest-cov 7.0.0:** Dev-only dependencies for automated testing. Not installed on Pi.
- **Custom auth decorator (no library):** A 15-line `@require_api_key` decorator checking `X-Print-Key` header against config.yaml. Full auth libraries are massive overkill for a single-owner appliance.
- **Flask built-in MAX_CONTENT_LENGTH:** One-line config, 10MB cap. Prevents OOM kills from oversized uploads.

**Explicitly rejected:** gunicorn, Redis, SQLAlchemy, Docker, mypy, pydantic (for now), celery. See STACK.md "What NOT to Install" section.

### Expected Features

Feature research identified 7 table-stakes fixes and 11 differentiators. See [FEATURES.md](FEATURES.md) for the full landscape.

**Must have (table stakes -- fix bugs and prevent crashes):**
- Input validation on all endpoints (stops 500 errors from bad input)
- Request size limits (prevents OOM kills on Pi)
- Content-Type enforcement (stop accepting garbage as JSON)
- Error response consistency (structured 400 errors, not Python tracebacks)
- Formatter state reset safety (try/finally guards prevent wedged printer)
- Graceful shutdown (SIGTERM handler for clean mDNS/USB cleanup)
- Config validation on startup (fail fast, not on first request)

**Should have (differentiators -- make the server robust):**
- API key authentication (prevents unauthorized printing on shared networks)
- Rate limiting (prevents paper waste from runaway clients)
- Structured logging (replace print() with logging module, consistent format)
- Print job acknowledgment with details (duration, template name in response)
- Config mutation fix in portrait_pipeline.py (deep-copy before mutation)

**Defer (build only if pain is felt):**
- systemd watchdog integration
- Printer status queries via DLE EOT
- USB reconnect backoff with exponential retry
- Request ID / correlation (only valuable after structured logging exists)

**Anti-features (explicitly do NOT build):**
- HTTPS/TLS, production WSGI, print queue, multi-tenancy, admin dashboard, auto-updates, multi-printer support

### Architecture Approach

Keep the flat module structure. Add `validators.py` and `helpers.py` at the root, plus a `tests/` directory. No packages, no blueprints, no restructuring. See [ARCHITECTURE.md](ARCHITECTURE.md) for component boundaries and data flow.

**Major components after hardening:**
1. **`validators.py` (NEW):** Request validation functions (one per endpoint) + `@require_api_key` decorator. Pure functions, no dependencies on other project modules. Validation happens BEFORE acquiring the print lock.
2. **`helpers.py` (NEW):** Three utilities extracted from duplicated code: `resolve_font_path()`, `wrap_text()`, `open_image()`. Foundation module that templates, renderer, and slicer import from.
3. **`print_server.py` (MODIFIED):** Adds MAX_CONTENT_LENGTH, validation calls, auth decorator, SIGTERM handler. Removes `force=True` from get_json().
4. **`printer_core.py` (MODIFIED):** Adds try/finally state guards to Formatter methods, `font_b_text()` method, ESC@ reset at start of every print job.
5. **`tests/` (NEW):** pytest suite using Flask test client and Dummy printer. No hardware dependencies.

**Key architectural decision:** Validation happens before the print lock is acquired. Bad requests never touch the printer. This is the correct separation of concerns for a single-threaded USB print server.

### Critical Pitfalls

Top 5 pitfalls from [PITFALLS.md](PITFALLS.md), ordered by impact:

1. **USB printer state wedges after exception** -- Formatter methods set bold/align/font but have no try/finally guards. An exception leaves the printer in dirty state that survives reconnection. Fix: try/finally on every state-changing method + send ESC@ (initialize) at the start of every print job.
2. **No request size limits enables OOM kill** -- No MAX_CONTENT_LENGTH means a single large upload exhausts the Pi's 400MB memory cap. Three OOM kills in 60 seconds triggers systemd start-limit-hit, printer goes offline. Fix: one line of Flask config.
3. **SD card corruption from write wear** -- Default ext4 with relatime + continuous journal writes wears out consumer SD cards. Power loss during write can brick the Pi. Fix: noatime mount, journald SystemMaxUse=20M, volatile log storage.
4. **usblp kernel module steals printer after kernel update** -- Blacklist can be overridden by kernel updates. Health check says "running" but all prints fail with "Resource busy." Fix: startup check for usblp, update-initramfs after blacklisting.
5. **Graceful shutdown fails, stale mDNS persists** -- Flask dev server does not reliably trigger atexit. SIGTERM handler must explicitly close printer and unregister mDNS. Fix: signal.signal(SIGTERM, handler) in main().

## Implications for Roadmap

Based on combined research, the hardening work naturally splits into 5 phases with clear dependencies. The ordering follows the build-dependency graph from ARCHITECTURE.md and the priority ranking from FEATURES.md.

### Phase 1: Foundation -- Shared Utilities and Config Safety
**Rationale:** Everything else depends on helpers.py existing (templates, renderer, slicer all import from it). Config validation must come first because auth depends on config keys being present. This phase has zero risk of breaking existing functionality -- it only extracts and adds, never modifies behavior.
**Delivers:** `helpers.py` module, config validation on startup, deduplicated imports across templates/renderer/slicer.
**Addresses:** Code deduplication (3 functions copied across 3 modules), config validation on startup.
**Avoids:** Circular import pitfall (helpers imports nothing from the project).

### Phase 2: Input Validation and Error Handling
**Rationale:** This is the highest-impact hardening. Every endpoint currently crashes on bad input (500 KeyError). This must be fixed before adding auth or rate limiting, because those features add new error paths that need consistent handling.
**Delivers:** `validators.py` module with per-endpoint validation, Content-Type enforcement, MAX_CONTENT_LENGTH, structured error responses, removal of `force=True` from get_json().
**Addresses:** Input validation, request size limits, Content-Type enforcement, error response consistency.
**Avoids:** Forgetting to validate `None` from invalid JSON; not testing empty body, missing keys, wrong types.

### Phase 3: Printer Reliability -- State Guards and Shutdown
**Rationale:** With validation preventing bad input from reaching the printer, this phase hardens the printer interaction itself. State guards prevent cascading corruption. Graceful shutdown prevents stale mDNS and dirty USB. The config mutation fix in portrait_pipeline prevents silent state leak.
**Delivers:** try/finally guards on all Formatter state-changing methods, ESC@ reset at start of print jobs, `font_b_text()` method, SIGTERM handler, config deep-copy in portrait pipeline.
**Addresses:** Formatter state reset safety, graceful shutdown, config mutation bug.
**Avoids:** Signal handler doing too much work (keep it minimal: close, unregister, exit); missing a Formatter method in the audit.

### Phase 4: Access Control and Rate Limiting
**Rationale:** Now that the server handles errors gracefully and the printer state is safe, add external-facing protections. Auth and rate limiting depend on validation being solid (they introduce new 401/429 error paths). Rate limiting benefits from structured logging for debugging.
**Delivers:** `@require_api_key` decorator, API key in config.yaml, Flask-Limiter with memory:// backend, structured logging with Python logging module, print job response metadata (duration, template).
**Addresses:** API key authentication, rate limiting, structured logging, print job acknowledgment.
**Avoids:** Forgetting to protect file upload endpoints; exempting /health and / from auth; using Redis (overkill).

### Phase 5: Test Suite
**Rationale:** Tests come last because they test the hardened code, not the pre-hardening state. All the modules they exercise (validators, helpers, Formatter state guards, server error handling) must exist first. The stress_test.sh remains as the hardware integration test.
**Delivers:** pytest suite with conftest.py, test_md_renderer.py, test_validators.py, test_server.py, test_templates.py; pytest-cov configuration; requirements-dev.txt.
**Addresses:** Automated testing without hardware, rendering property tests (dimensions, mode, no-crash), validation edge cases.
**Avoids:** Tests that require hardware (use Dummy printer throughout); golden image tests (brittle across platforms -- test properties instead).

### Phase Ordering Rationale

- **Phases 1-2 are foundational.** helpers.py is a dependency for all other refactoring. Validation is a dependency for auth (auth returns errors using the same error format).
- **Phase 3 is independent of Phase 2** in terms of code, but logically follows: fix input handling first, then fix output handling. Could run in parallel if desired.
- **Phase 4 requires Phase 2** (error format consistency) and benefits from Phase 3 (structured logging).
- **Phase 5 requires all prior phases** to be stable. Writing tests against pre-hardening code and then refactoring the code is wasted effort.
- **SD card hardening** (noatime, journald limits) is a Pi deployment concern, not a code change. It should be documented and applied via setup.sh, not tied to a code phase. Recommend adding it to Phase 3 as an ops task alongside the SIGTERM handler work.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Printer Reliability):** SIGTERM handling with Flask's dev server has known quirks. Needs testing on actual Pi with `systemctl stop`. The signal handler may not fire if Flask/Werkzeug intercepts it. Fallback plan documented but untested.
- **Phase 4 (Rate Limiting):** Flask-Limiter's memory:// backend behavior under Flask dev server's single-thread model needs verification. The library warns against in-memory storage, but the warning applies to multi-process deployments, not this use case. Quick spike to verify.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Pure Python extraction refactoring. No unknowns.
- **Phase 2 (Validation):** Hand-rolled validation functions, Flask MAX_CONTENT_LENGTH. Extremely well-documented patterns.
- **Phase 5 (Tests):** Flask test client, pytest fixtures, Dummy printer. Standard approach, no research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Existing stack confirmed working. Additions are minimal, all have aarch64 wheels, all verified against Python 3.13. |
| Features | HIGH | Feature list derived from direct codebase analysis and stress test results, not speculation. Every table-stakes item maps to a confirmed bug or missing guard. |
| Architecture | HIGH | Flat module structure is proven. New modules follow existing patterns. Build-dependency order verified against actual import graph. |
| Pitfalls | HIGH | Top 5 pitfalls confirmed in codebase (no try/finally, no MAX_CONTENT_LENGTH, no SIGTERM handler). SD card and usblp pitfalls confirmed from prior deployment experience in MEMORY.md. |

**Overall confidence:** HIGH

### Gaps to Address

- **SIGTERM with Flask dev server:** The signal handler approach is standard Python but Flask/Werkzeug may intercept SIGTERM. Needs hands-on testing on the Pi. If it does not work, fallback is `KillMode=mixed` + `ExecStopPost=/bin/sleep 1` in systemd unit.
- **Pydantic vs. hand-rolled validation tension:** STACK.md recommends pydantic; ARCHITECTURE.md recommends hand-rolled. This summary recommends hand-rolled for now. If validation logic grows beyond ~15 schemas or needs nested object validation, revisit pydantic.
- **Halftone/Bayer performance on Pi:** The pure-Python pixel loops may block the server for seconds during image processing. Not a hardening priority, but if image printing is used heavily, the dithering should be moved outside the print lock or rewritten with NumPy.
- **Font availability on Pi:** The helvetica style references macOS-only fonts. Config validation in Phase 1 should warn about this at startup but not fail (it is a known limitation, not a bug).

## Sources

### Primary (HIGH confidence)
- Project codebase: `print_server.py`, `printer_core.py`, `templates.py`, `md_renderer.py`, `portrait_pipeline.py`, `config.yaml`
- Project docs: `CLAUDE.md`, `MEMORY.md`, `.planning/codebase/CONCERNS.md`
- [Flask official docs](https://flask.palletsprojects.com/) -- MAX_CONTENT_LENGTH, security considerations, test client
- [python-escpos docs](https://python-escpos.readthedocs.io/) -- Dummy printer, USB connection management
- [pytest docs](https://docs.pytest.org/) -- fixtures, test client patterns
- [Flask-Limiter docs](https://flask-limiter.readthedocs.io/) -- memory:// backend, rate string format

### Secondary (MEDIUM confidence)
- [Flask MAX_CONTENT_LENGTH issue #1200](https://github.com/pallets/flask/issues/1200) -- JSON payload bypass behavior
- [pyusb Resource Busy issues #76, #391](https://github.com/pyusb/pyusb/issues/) -- kernel driver conflict patterns
- [Pi SD card reliability (dzombak.com, Hackaday)](https://www.dzombak.com/blog/2024/04/pi-reliability-reduce-writes-to-your-sd-card/) -- write wear mitigation
- [Flask-Limiter in-memory discussion #373](https://github.com/alisaifee/flask-limiter/discussions/373) -- single-process production use
- [pydantic PyPI](https://pypi.org/project/pydantic/) -- version 2.12.5, aarch64 wheel availability

### Tertiary (LOW confidence)
- Thermal printhead overheating -- general knowledge from manufacturer guides (ZYWELL, Rongta). Specific behavior depends on the actual printer model.
- Inline markdown regex nesting failures -- theoretical edge cases, not yet reported in production use.

---
*Research completed: 2026-03-08*
*Ready for roadmap: yes*
