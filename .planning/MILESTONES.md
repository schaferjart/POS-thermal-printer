# Milestones

## v1.0 MVP (Shipped: 2026-03-09)

**Phases:** 1-4 | **Plans:** 8 | **Tasks:** 16
**Timeline:** 2026-03-08 → 2026-03-09 (2 days)
**LOC:** 4,895 Python | **Tests:** 89 passed, 1 skipped
**Git range:** feat(01-01) → test(04-02)

**Key accomplishments:**
1. Shared utilities extracted to helpers.py (resolve_font_path, wrap_text, open_image) — 5 consumer modules deduplicated
2. Server hardened with input validation, 10MB limit, ESC@ init, try/finally guards, consistent JSON errors
3. Graceful SIGTERM/SIGINT shutdown with mDNS deregistration and printer close
4. Optional API key auth via X-Print-Key header with timing-safe hmac comparison
5. Enhanced /health endpoint with printer status, uptime, and last print timestamp
6. 89-test pytest suite covering parsing, dithering, validation, and auth — no hardware needed

---

