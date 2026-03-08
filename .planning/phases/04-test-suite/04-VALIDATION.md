---
phase: 04
slug: test-suite
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none (uses default discovery, `tests/` directory) |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | TEST-01 | unit | `python -m pytest tests/test_md_renderer.py::TestParseMd -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | TEST-01 | unit | `python -m pytest tests/test_md_renderer.py::TestParseInline -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | TEST-01 | unit | `python -m pytest tests/test_md_renderer.py::TestRenderMarkdown -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | TEST-02 | unit | `python -m pytest tests/test_image_printer.py::TestDitherFunctions -x` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | TEST-02 | unit | `python -m pytest tests/test_image_printer.py::TestProcessImage -x` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 1 | TEST-03 | integration | `python -m pytest tests/test_server.py::TestValidPayloads -x` | ❌ W0 | ⬜ pending |
| 04-03-02 | 03 | 1 | TEST-03 | integration | `python -m pytest tests/test_server.py::TestImageEndpoint -x` | ❌ W0 | ⬜ pending |
| 04-04-01 | - | - | TEST-04 | integration | `python -m pytest tests/test_server.py::TestAuth tests/test_server.py::TestAuthDisabled -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_md_renderer.py` — stubs for TEST-01 (parsing and rendering)
- [ ] `tests/test_image_printer.py` — stubs for TEST-02 (dithering)
- [ ] Valid payload and image endpoint tests in `tests/test_server.py` — stubs for TEST-03 gaps

*Existing `tests/conftest.py` fixtures cover shared infrastructure.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
