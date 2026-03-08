# Roadmap: POS Thermal Print Server Hardening

## Overview

This is a hardening milestone for an existing, working thermal print server. The server already prints correctly but crashes on bad input, has no authentication, and has fragile printer state management. The roadmap moves from extracting shared utilities (so everything else can build on clean foundations), through hardening the server and printer interaction, to adding access control and observability, and finally writing tests against the hardened code. Four phases, no new features -- just making what exists bulletproof.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Extract shared utilities into helpers.py and add config validation on startup
- [ ] **Phase 2: Server Hardening** - Input validation, Formatter state safety, graceful shutdown, and error consistency
- [ ] **Phase 3: Access Control and Observability** - API key authentication and health endpoint improvements
- [ ] **Phase 4: Test Suite** - pytest tests for rendering, validation, auth, and dithering

## Phase Details

### Phase 1: Foundation
**Goal**: Shared code lives in one place and config errors are caught at startup, not at print time
**Depends on**: Nothing (first phase)
**Requirements**: QUAL-01, QUAL-02, QUAL-03, REL-06
**Success Criteria** (what must be TRUE):
  1. Font path resolution is called from a single helpers.py function -- templates.py and md_renderer.py both import it instead of having their own copies
  2. wrap_text and image-open logic (EXIF transpose + alpha removal) each exist in one place, imported by all consumers
  3. Server refuses to start if config.yaml is missing required keys (USB IDs, paper width, server port) and prints a clear error message naming the missing key
**Plans:** 2 plans
Plans:
- [ ] 01-01-PLAN.md -- Extract resolve_font_path, wrap_text, open_image into helpers.py and update all consumers
- [ ] 01-02-PLAN.md -- Add config validation to printer_core.py and wire into server startup

### Phase 2: Server Hardening
**Goal**: Bad input returns clear errors, the printer never gets stuck in dirty state, and shutdown is clean
**Depends on**: Phase 1
**Requirements**: REL-01, REL-02, REL-03, REL-04, REL-05, QUAL-04, QUAL-05, QUAL-06
**Success Criteria** (what must be TRUE):
  1. Sending a request with missing required fields to any print endpoint returns 400 with a JSON body naming the missing field -- not a 500 traceback
  2. Sending a request over 10MB to any endpoint returns 413 before the body is processed
  3. After a mid-print exception, the next print job succeeds without manual intervention (Formatter state is reset via try/finally and ESC@ initialize)
  4. Sending SIGTERM to the server process results in mDNS deregistration and printer connection close before exit
  5. All error responses from the server use the same JSON format: {"error": "message", "field": "name"}
**Plans**: TBD

### Phase 3: Access Control and Observability
**Goal**: Print endpoints require an API key and the health endpoint reports real printer status
**Depends on**: Phase 2
**Requirements**: AUTH-01, AUTH-02, AUTH-03, OBS-01, OBS-02
**Success Criteria** (what must be TRUE):
  1. Sending a print request without the correct X-Print-Key header returns 401
  2. The / (web UI) and /health endpoints respond successfully without any API key
  3. When no api_key is set in config.yaml, all endpoints work without authentication (backwards compatible)
  4. GET /health returns JSON with printer connection status (connected/disconnected), server uptime, and last successful print timestamp
**Plans**: TBD

### Phase 4: Test Suite
**Goal**: Automated tests verify rendering, validation, auth, and dithering without needing a physical printer
**Depends on**: Phase 3
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. Running `pytest` in the project root executes a test suite that passes without any printer hardware connected
  2. Tests cover md_renderer parsing (headings, bold, italic, code, lists, blockquotes produce correct image dimensions and modes)
  3. Tests cover input validation for each endpoint (valid payloads succeed, missing fields return 400, oversized requests return 413)
  4. Tests cover API key auth (correct key passes, wrong key returns 401, missing key returns 401, no key configured means all requests pass)
  5. Tests cover image_printer dithering with known input images (output is 1-bit, correct dimensions)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/2 | Planning complete | - |
| 2. Server Hardening | 0/? | Not started | - |
| 3. Access Control and Observability | 0/? | Not started | - |
| 4. Test Suite | 0/? | Not started | - |
