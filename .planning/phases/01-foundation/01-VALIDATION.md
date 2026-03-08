---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (not yet installed — Wave 0 installs) |
| **Config file** | none — Wave 0 creates tests/ directory |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~2 seconds |

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
| 1-01-01 | 01 | 1 | QUAL-01 | unit | `python -m pytest tests/test_helpers.py::test_resolve_font_path -x` | No — W0 | pending |
| 1-01-02 | 01 | 1 | QUAL-02 | unit | `python -m pytest tests/test_helpers.py::test_wrap_text -x` | No — W0 | pending |
| 1-01-03 | 01 | 1 | QUAL-03 | unit | `python -m pytest tests/test_helpers.py::test_open_image -x` | No — W0 | pending |
| 1-02-01 | 02 | 1 | REL-06 | unit | `python -m pytest tests/test_helpers.py::test_validate_config -x` | No — W0 | pending |

---

## Wave 0 Requirements

- [ ] `tests/` directory created
- [ ] `tests/test_helpers.py` — stubs for QUAL-01, QUAL-02, QUAL-03, REL-06
- [ ] `tests/conftest.py` — shared fixtures (sample images, minimal config dicts)
- [ ] `pip install pytest` — not in requirements.txt yet
- [ ] Smoke test: `./print.sh test --dummy` and `./print.sh md "# Hello" --dummy` still work

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Existing `--dummy` commands still produce correct output | ALL | Visual verification of print output | Run `./print.sh test --dummy`, `./print.sh md "# Hello" --dummy`, check preview images |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
