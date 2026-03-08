# POS Thermal Print Server

## What This Is

A reliable network thermal print server running on Raspberry Pi. Accepts markdown text and images over HTTP, renders them with full typographic control using custom fonts, and prints on 80mm ESC/POS receipt printers. Any device on the same network can send a print job — the server doesn't decide what to print, it just prints what it's told.

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

### Active

- [ ] Input validation on all server endpoints (return 400 not 500 for bad input)
- [ ] Deduplicate shared code (_resolve_font_path, wrap_text, image-open logic)
- [ ] Basic API authentication (API key header)
- [ ] Request size limits to prevent memory exhaustion on Pi
- [ ] Fix config mutation bug in portrait pipeline (shared state leak between requests)
- [ ] Move raw ESC/POS commands in server into Formatter abstraction
- [ ] Unit tests for md_renderer (parsing logic) and image_printer (dithering algorithms)
- [ ] Formatter state reset safety (try/finally guards)
- [ ] Graceful shutdown (clean mDNS deregistration, printer close)

### Out of Scope

- Face recognition, news aggregation, content generation — client responsibilities, belong in separate repos
- Multi-printer support — single printer is the use case
- User accounts / multi-tenancy — this is a single-owner appliance
- Production WSGI server (gunicorn) — Flask dev server is adequate for single-printer, low-traffic use
- Mobile app — web UI serves mobile browsers fine
- Real-time print queue / job management — single printer, sequential printing is sufficient

## Context

This project lives under the VAKUNST art practice umbrella. It started as tooling for an art installation with interactive thermal printing. The architecture is evolving toward a clean separation: this repo becomes a monofunctional print server, while creative/interactive logic (art installation, face recognition, news printing) lives in separate repos that call this server's HTTP API.

The Pi 3 (Debian Trixie, aarch64) runs as a headless network appliance at home (192.168.1.65). The printer is a USB ESC/POS receipt printer connected directly to the Pi.

Current codebase is flat Python modules at the project root — no packages, no build system, pure venv + pip. This simplicity is intentional and should be preserved.

## Constraints

- **Hardware**: Raspberry Pi 3 with 1GB RAM — must stay under 400MB (systemd limit)
- **Runtime**: Python 3, venv + pip, no build system
- **Printer**: Single USB ESC/POS printer, 80mm paper (576px / 48 chars)
- **Network**: Home WiFi, single-owner, but auth still needed to prevent accidental prints from other devices
- **Dependencies**: Keep optional heavy deps (numpy, mediapipe) optional via lazy imports
- **Simplicity**: Flat module structure, no unnecessary abstraction layers

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Markdown as universal input format | Any client can compose markdown; rich enough for news, art, messages | — Pending |
| Keep portrait pipeline in this repo | Serves as working example of an API client | — Pending |
| Keep web UI in this repo | Direct human access to printer, useful for manual printing | — Pending |
| Hardening before new features | Foundation must be solid before building more on top | — Pending |
| Flat module structure (no packages) | Simplicity matches the single-purpose nature of the project | ✓ Good |

---
*Last updated: 2026-03-08 after initialization*
