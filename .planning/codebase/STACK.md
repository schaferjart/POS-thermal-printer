# Technology Stack

**Analysis Date:** 2026-03-07

## Languages

**Primary:**
- Python 3.11 - All application code (8 source files at project root)

**Secondary:**
- HTML/CSS/JavaScript - Single-page web UI in `templates/index.html`
- YAML - Configuration in `config.yaml`
- Bash - Venv wrapper script `print.sh`

## Runtime

**Environment:**
- Python 3.11 (CPython, confirmed via `venv/lib/python3.11/`)
- No `.python-version` file present

**Package Manager:**
- pip (standard library)
- Lockfile: None (only `requirements.txt` with pinned versions)
- Virtual environment: `venv/` directory at project root

## Frameworks

**Core:**
- Flask 3.1.3 - HTTP server for receiving print jobs (`print_server.py`)
- flask-cors 5.0.1 - CORS support for cross-origin requests from iPad/web clients (`print_server.py`)

**Testing:**
- None configured. No test framework, no test files. All testing is manual via `--dummy` flag.

**Build/Dev:**
- No build system. Pure `venv + pip install -r requirements.txt`.
- `print.sh` is a 3-line bash wrapper that activates the venv and runs `print_cli.py`.

## Key Dependencies

**Critical:**
- `python-escpos` 3.1 - ESC/POS thermal printer protocol implementation. Core of `printer_core.py`. Provides `Usb`, `Network`, and `Dummy` printer classes.
- `Pillow` (pillow) 12.1.1 - All image rendering: markdown-to-image, dithering, image processing, font rendering. Used in `md_renderer.py`, `image_printer.py`, `image_slicer.py`, `templates.py`, `portrait_pipeline.py`.
- `PyYAML` 6.0.3 - Configuration loading from `config.yaml` via `printer_core.load_config()`.

**Infrastructure:**
- `pyusb` 1.3.1 - USB communication with thermal printer hardware. Requires `libusb` system library on macOS (`brew install libusb`).
- `zeroconf` 0.146.0 - Bonjour/mDNS service registration for automatic iPad discovery (`print_server.py:register_mdns()`).
- `requests` >=2.31 - HTTP client for OpenRouter API and n8n webhook calls in `portrait_pipeline.py`.
- `numpy` (implicit via mediapipe) - Used directly in `portrait_pipeline.py` for face landmark detection array processing.

**Image/Print Utilities:**
- `python-barcode` 0.16.1 - Barcode generation (used via `Formatter.barcode()` in `printer_core.py`)
- `qrcode` 8.2 - QR code generation (used via `Formatter.qr()` and `python-escpos` integration)

**AI/ML (portrait pipeline only):**
- `mediapipe` (imported lazily in `portrait_pipeline.py:detect_face_landmarks()`) - Face landmark detection for zoom crop computation. Not listed in `requirements.txt` -- must be installed separately.

**Flask ecosystem (transitive):**
- `Werkzeug` 3.1.6, `Jinja2` 3.1.6, `MarkupSafe` 3.0.3, `click` 8.3.1, `itsdangerous` 2.2.0, `blinker` 1.9.0

## Configuration

**Environment:**
- All configuration in `config.yaml` at project root
- Single environment variable: `OPENROUTER_API_KEY` (required only for portrait pipeline)
- No `.env` file present; env var is expected to be exported manually
- The env var name is configurable via `config.yaml` key `portrait.openrouter_api_key_env`

**Build:**
- No build step. Run directly with Python interpreter.
- `requirements.txt` - Pinned dependency versions (20 packages)
- `config.yaml` - Runtime configuration for all features

**Hardware Configuration (in `config.yaml`):**
- `printer.vendor_id` / `printer.product_id` - USB device identifiers (default: `0x1fc9` / `0x2016`)
- `printer.connection` - `"usb"` or `"network"`
- `printer.paper_width` - Character width (48 for 80mm paper)
- `halftone.paper_px` - Pixel width (576 for 80mm @ 203 DPI)

**Font Configuration (in `config.yaml`):**
- Three style presets: `dictionary`, `helvetica`, `acidic`
- Each defines font file paths, sizes, spacing, margins
- Bundled fonts in `fonts/`: `Burra-Bold.ttf`, `Burra-Thin.ttf`, `Acidic.TTF`
- `helvetica` style uses macOS system fonts (`/System/Library/Fonts/HelveticaNeue.ttc`) with face index selection

## Platform Requirements

**Development (macOS):**
- Python 3.11
- `brew install libusb` (required for `pyusb` USB communication)
- System fonts available at `/System/Library/Fonts/` (for `helvetica` style)
- No IDE config, no linting, no formatting tools configured

**Production (Raspberry Pi 3):**
- Debian Bookworm (aarch64)
- USB thermal printer connected directly
- Runs as `sudo ./venv/bin/python3 print_server.py` (root required for USB access)
- Server listens on `0.0.0.0:9100`
- Connected to eduroam WiFi (ETH Zurich campus network)
- systemd service configured for auto-start (see recent commits)

---

*Stack analysis: 2026-03-07*
