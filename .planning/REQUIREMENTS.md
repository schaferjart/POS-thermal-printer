# Requirements: POS Thermal Print Server

**Defined:** 2026-03-08
**Core Value:** Any device on the network can send a print job and it prints correctly, every time.

## v1 Requirements

Requirements for the hardening milestone. Each maps to roadmap phases.

### Reliability

- [ ] **REL-01**: Server returns 400 with clear error message when required JSON fields are missing
- [ ] **REL-02**: Server rejects requests over 10MB with 413 status before processing
- [ ] **REL-03**: Formatter methods use try/finally guards so printer state is always reset after each operation
- [ ] **REL-04**: Printer receives ESC@ initialize command at the start of every print job
- [ ] **REL-05**: Server handles SIGTERM gracefully — deregisters mDNS, closes printer connection, then exits
- [ ] **REL-06**: Server validates config.yaml on startup and fails fast with clear message if required keys are missing

### Code Quality

- [ ] **QUAL-01**: Shared font path resolution extracted to single location (helpers.py), used by templates.py and md_renderer.py
- [ ] **QUAL-02**: Shared wrap_text function extracted to single location, used by templates.py and md_renderer.py
- [ ] **QUAL-03**: Shared image-open logic (EXIF transpose + alpha removal) extracted to single location, used by image_printer.py, image_slicer.py, portrait_pipeline.py
- [ ] **QUAL-04**: Raw ESC/POS commands in print_server.py moved into Formatter methods in printer_core.py
- [ ] **QUAL-05**: Portrait pipeline config mutation bug fixed — no shared state leak between requests
- [ ] **QUAL-06**: All server error responses use consistent structured JSON format: {"error": "message", "field": "name"}

### Access Control

- [ ] **AUTH-01**: Server checks X-Print-Key header against key in config.yaml on all print endpoints
- [ ] **AUTH-02**: /health and / (web UI) endpoints are accessible without API key
- [ ] **AUTH-03**: If no API key is configured in config.yaml, auth is disabled (backwards compatible)

### Testing

- [ ] **TEST-01**: pytest test suite for md_renderer markdown parsing (headings, bold, italic, code, lists, blockquotes)
- [ ] **TEST-02**: pytest tests for image_printer dithering functions with known inputs
- [ ] **TEST-03**: pytest tests for input validation (valid and invalid payloads for each endpoint)
- [ ] **TEST-04**: pytest tests for API key auth (with key, without key, wrong key, no key configured)

### Observability

- [ ] **OBS-01**: /health endpoint reports printer connection status (connected/disconnected)
- [ ] **OBS-02**: /health endpoint reports server uptime and last successful print timestamp

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Access Control

- **AUTH-04**: Rate limiting (10 req/min per IP, hand-rolled)
- **AUTH-05**: Content-Type enforcement (reject non-JSON with 415)

### Observability

- **OBS-03**: Structured logging (replace print() with logging module, consistent format)
- **OBS-04**: Request ID / correlation for debugging
- **OBS-05**: systemd watchdog integration for hang detection

### Resilience

- **RES-01**: USB reconnect with exponential backoff
- **RES-02**: Temp file cleanup on startup
- **RES-03**: Printer status queries via DLE EOT (hardware-dependent)

## Out of Scope

| Feature | Reason |
|---------|--------|
| HTTPS / TLS | LAN-only appliance, no sensitive data in transit |
| Production WSGI (gunicorn) | Single printer, single thread is correct behavior |
| Print queue / job management | Sequential blocking is correct for single printer |
| User accounts / multi-tenancy | Single-owner appliance |
| Admin dashboard | journalctl + /health is sufficient |
| Auto-update mechanism | Risk of bricking mid-print, manual git pull is fine |
| Multi-printer support | Different project entirely |
| Webhook callbacks / async notifications | Print jobs take 2-5s, synchronous is fine |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REL-01 | — | Pending |
| REL-02 | — | Pending |
| REL-03 | — | Pending |
| REL-04 | — | Pending |
| REL-05 | — | Pending |
| REL-06 | — | Pending |
| QUAL-01 | — | Pending |
| QUAL-02 | — | Pending |
| QUAL-03 | — | Pending |
| QUAL-04 | — | Pending |
| QUAL-05 | — | Pending |
| QUAL-06 | — | Pending |
| AUTH-01 | — | Pending |
| AUTH-02 | — | Pending |
| AUTH-03 | — | Pending |
| TEST-01 | — | Pending |
| TEST-02 | — | Pending |
| TEST-03 | — | Pending |
| TEST-04 | — | Pending |
| OBS-01 | — | Pending |
| OBS-02 | — | Pending |

**Coverage:**
- v1 requirements: 21 total
- Mapped to phases: 0
- Unmapped: 21

---
*Requirements defined: 2026-03-08*
*Last updated: 2026-03-08 after initial definition*
