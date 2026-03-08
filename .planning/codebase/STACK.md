# Technology Stack

**Analysis Date:** 2026-03-08

## Languages

**Primary:**
- Python 3 - All application code (CLI, server, rendering, image processing)

**Secondary:**
- Bash - Shell wrappers and setup scripts (`print.sh`, `setup.sh`, `run_portrait.sh`, `stress_test.sh`)
- YAML - Configuration (`config.yaml`)
- HTML - Single web UI page (`templates/index.html`)

## Runtime

**Environment:**
- Python 3 (no version pinned; system Python 3 via `python3 -m venv`)
- No `.python-version` or `pyproject.toml` detected

**Package Manager:**
- pip (via venv)
- Lockfile: missing (only `requirements.txt` with pinned versions)

## Frameworks

**Core:**
- Flask 3.1.3 - HTTP print server (`print_server.py`)
- flask-cors 5.0.1 - Cross-origin requests for the web UI and iPad clients

**Testing:**
- No test framework configured (no pytest, unittest, etc.)
- `stress_test.sh` is a Bash integration/acceptance test suite using curl

**Build/Dev:**
- No build system - pure Python with venv + pip
- `setup.sh` handles system deps, venv creation, pip install, and systemd/launchd service setup

## Key Dependencies

**Critical:**
- `python-escpos` 3.1 - ESC/POS thermal printer protocol (USB and network). Core abstraction: `escpos.printer.Usb`, `escpos.printer.Network`, `escpos.printer.Dummy`
- `pillow` 12.1.1 - Image rendering, manipulation, dithering, font rendering for markdown-to-image pipeline
- `pyusb` 1.3.1 - Low-level USB communication (backend for python-escpos USB mode)

**Infrastructure:**
- `PyYAML` 6.0.3 - Configuration loading from `config.yaml`
- `zeroconf` 0.146.0 - Bonjour/mDNS service registration for network discovery by iPads
- `requests` >=2.31 - HTTP client for OpenRouter API and n8n webhook calls (portrait pipeline)
- `Werkzeug` 3.1.6 - WSGI toolkit (Flask dependency)
- `Jinja2` 3.1.6 - HTML template rendering (Flask dependency, used for `templates/index.html`)

**Optional (portrait pipeline only):**
- `numpy` - Array processing for face landmark detection (lazy import, not in requirements.txt)
- `mediapipe` - Face mesh/landmark detection for zoom crop computation (lazy import, not in requirements.txt)

**Utility:**
- `python-barcode` 0.16.1 - Barcode generation
- `qrcode` 8.2 - QR code generation
- `argcomplete` 3.6.3 - Bash tab completion for CLI

## Configuration

**Environment:**
- `.env` files present but gitignored - existence only noted
- `OPENROUTER_API_KEY` env var required for portrait pipeline (photo selection + style transfer)
- Config var name is configurable via `config.yaml` key `portrait.openrouter_api_key_env`

**Application Config:**
- `config.yaml` - Single config file for all settings:
  - `printer` section: USB vendor/product IDs (`0x1fc9`/`0x2016`), connection type (usb/network), paper width (48 chars), encoding
  - `server` section: host (`0.0.0.0`), port (`9100`)
  - `template` section: receipt header/footer lines, currency
  - `dictionary` section: font paths, sizes, spacing for dictionary art-print style
  - `helvetica` section: macOS-only HelveticaNeue.ttc font configuration (not available on Pi)
  - `acidic` section: large display font configuration
  - `halftone` section: dithering defaults (mode, dot_size, contrast, brightness, sharpness, blur)
  - `portrait` section: AI pipeline config (API keys, models, n8n webhook URL, style prompt, zoom crop settings)

**Build:**
- No build config - pure interpreted Python
- `requirements.txt` - pip dependencies with pinned versions

## Fonts

**Bundled fonts in `fonts/` directory:**
- `fonts/Burra-Bold.ttf` - Bold weight for headings/emphasis
- `fonts/Burra-Thin.ttf` - Thin weight for body text
- `fonts/Acidic.TTF` - Display font for large character prints

**System fonts (macOS only):**
- `/System/Library/Fonts/HelveticaNeue.ttc` - Used by `helvetica` style, with `.ttc` index for weight selection
- Linux fallback: DejaVu Sans fonts (`/usr/share/fonts/truetype/dejavu/`)

## Platform Requirements

**Development (macOS):**
- Python 3
- `libusb` (via `brew install libusb`)
- System fonts for `helvetica` style

**Production (Raspberry Pi 3, Debian Trixie aarch64):**
- `python3`, `python3-pip`, `python3-venv`
- `libusb-1.0-0-dev` - USB library
- `fonts-dejavu-core` - Fallback fonts for Linux
- `usblp` kernel module must be blacklisted (`/etc/modprobe.d/no-usblp.conf`)
- udev rule for USB printer access without root (`/etc/udev/rules.d/99-thermal-printer.rules`)
- systemd service: `pos-printer.service` (auto-start, restart-on-failure, memory-capped at 400MB)

**Target Hardware:**
- 80mm ESC/POS thermal receipt printer (USB, vendor `0x1fc9`, product `0x2016`)
- Paper: 576px width at 203 DPI

---

*Stack analysis: 2026-03-08*
