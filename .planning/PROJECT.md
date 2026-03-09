# POS Thermal Print Server

## What This Is

A reliable, hardened network thermal print server running on Raspberry Pi. Accepts markdown text and images over HTTP, renders them with full typographic control using custom fonts, and prints on 80mm ESC/POS receipt printers. Any device on the same network can send a print job — the server validates input, authenticates requests, recovers from errors, and prints correctly every time.

## Core Value

Any device on the network can send a print job and it prints correctly, every time.

## Requirements

### Validated

- ✓ Markdown-to-image rendering with custom fonts (dictionary, helvetica, acidic styles) — existing
- ✓ Image dithering pipeline (Floyd-Steinberg, Bayer, halftone) — existing
- ✓ HTTP API for all print operations (/print/markdown, /print/image, /print/receipt, etc.) — existing
- ✓ CLI interface with all print commands — existing
- ✓ Web UI for direct browser-based printing — existing
- ✓ Raspberry Pi deployment with systemd service — existing
- ✓ mDNS/Bonjour service discovery — existing
- ✓ Thread-safe USB printing with retry/reconnect — existing
- ✓ Image slicing for poster-size prints — existing
- ✓ Portrait pipeline as working API client example — existing
- ✓ Shared utility extraction (helpers.py: resolve_font_path, wrap_text, open_image) — v1.0
- ✓ Config validation at startup with fail-fast error reporting — v1.0
- ✓ Input validation on all server endpoints (400 for bad input, not 500) — v1.0
- ✓ Request size limits (10MB MAX_CONTENT_LENGTH) — v1.0
- ✓ Formatter try/finally state safety guards — v1.0
- ✓ ESC@ init at start of every print job — v1.0
- ✓ Consistent JSON error response format — v1.0
- ✓ Raw ESC/POS commands moved to Formatter abstraction — v1.0
- ✓ Portrait pipeline config mutation fix — v1.0
- ✓ Graceful SIGTERM/SIGINT shutdown — v1.0
- ✓ Optional API key auth via X-Print-Key header — v1.0
- ✓ Enhanced /health endpoint (printer status, uptime, last print) — v1.0
- ✓ 89-test pytest suite (rendering, dithering, validation, auth) — v1.0

### Active

(None — define in next milestone)

### Out of Scope

- Face recognition, news aggregation, content generation — client responsibilities, belong in separate repos
- Multi-printer support — single printer is the use case
- User accounts / multi-tenancy — this is a single-owner appliance
- Production WSGI server (gunicorn) — Flask dev server is adequate for single-printer, low-traffic use
- Mobile app — web UI serves mobile browsers fine
- Real-time print queue / job management — single printer, sequential printing is sufficient
- Rate limiting — deferred to v2 (AUTH-04), not critical for single-owner LAN appliance
- Structured logging — deferred to v2, print() statements adequate for current scale

## Context

Shipped v1.0 with 4,895 LOC Python, 89 passing tests. Tech stack: Python 3, Flask, python-escpos, Pillow, pytest.

This project lives under the VAKUNST art practice umbrella. It started as tooling for an art installation with interactive thermal printing. The architecture is a clean separation: this repo is a monofunctional print server, while creative/interactive logic (art installation, face recognition, news printing) lives in separate repos that call this server's HTTP API.

The Pi 3 (Debian Trixie, aarch64) runs as a headless network appliance at home (192.168.1.65). The printer is a USB ESC/POS receipt printer connected directly to the Pi.

Flat Python modules at the project root — no packages, no build system, pure venv + pip. This simplicity is intentional and should be preserved.

## Constraints

- **Hardware**: Raspberry Pi 3 with 1GB RAM — must stay under 400MB (systemd limit)
- **Runtime**: Python 3, venv + pip, no build system
- **Printer**: Single USB ESC/POS printer, 80mm paper (576px / 48 chars)
- **Network**: Home WiFi, single-owner, auth via optional API key
- **Dependencies**: Keep optional heavy deps (numpy, mediapipe) optional via lazy imports
- **Simplicity**: Flat module structure, no unnecessary abstraction layers

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Markdown as universal input format | Any client can compose markdown; rich enough for news, art, messages | ✓ Good |
| Keep portrait pipeline in this repo | Serves as working example of an API client | ✓ Good |
| Keep web UI in this repo | Direct human access to printer, useful for manual printing | ✓ Good |
| Hardening before new features | Foundation must be solid before building more on top | ✓ Good — v1.0 shipped |
| Flat module structure (no packages) | Simplicity matches the single-purpose nature of the project | ✓ Good |
| Hand-rolled validation over pydantic | Zero deps, ~50 lines, trivially testable | ✓ Good — v1.0 |
| helpers.py imports nothing from the project | Avoids circular imports, stdlib + Pillow only | ✓ Good — v1.0 |
| hmac.compare_digest for API key comparison | Prevents timing side-channel attacks | ✓ Good — v1.0 |
| No _print_lock in signal handler | Avoids deadlock during shutdown | ✓ Good — v1.0 |
| Explicit override params instead of config mutation | Prevents shared state leak between requests | ✓ Good — v1.0 |

---
*Last updated: 2026-03-09 after v1.0 milestone*
