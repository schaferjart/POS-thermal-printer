---
phase: 02
slug: server-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 7.0 (already in requirements.txt) |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | REL-03 | unit (Dummy printer) | `python -m pytest tests/test_formatter.py::test_state_reset_on_exception -x` | No — Wave 0 | pending |
| 02-01-02 | 01 | 1 | REL-04 | unit (Dummy printer) | `python -m pytest tests/test_server.py::test_init_command_sent -x` | No — Wave 0 | pending |
| 02-02-01 | 02 | 1 | REL-01 | integration (Flask test client) | `python -m pytest tests/test_server.py::test_missing_fields_return_400 -x` | No — Wave 0 | pending |
| 02-02-02 | 02 | 1 | REL-02 | integration (Flask test client) | `python -m pytest tests/test_server.py::test_oversized_request_returns_413 -x` | No — Wave 0 | pending |
| 02-02-03 | 02 | 1 | QUAL-06 | integration (Flask test client) | `python -m pytest tests/test_server.py::test_error_format_consistent -x` | No — Wave 0 | pending |
| 02-02-04 | 02 | 1 | QUAL-04 | unit (grep/static check) | `python -m pytest tests/test_server.py::test_no_raw_escpos -x` | No — Wave 0 | pending |
| 02-03-01 | 03 | 2 | REL-05 | manual-only | N/A — requires `systemctl stop` on Pi | N/A | pending |
| 02-03-02 | 03 | 2 | QUAL-05 | unit | `python -m pytest tests/test_server.py::test_config_not_mutated -x` | No — Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_server.py` — Flask test client tests for validation and error format
- [ ] `tests/test_formatter.py` — Formatter state reset tests using Dummy printer
- [ ] `tests/conftest.py` — update with Flask test app fixture and sample config

*Note: Phase 1 already created `tests/` directory, `conftest.py`, and installed pytest.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SIGTERM triggers mDNS deregister + printer close | REL-05 | Requires systemd and real/emulated USB printer | SSH to Pi, run `sudo systemctl stop pos-printer`, verify clean exit in logs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
