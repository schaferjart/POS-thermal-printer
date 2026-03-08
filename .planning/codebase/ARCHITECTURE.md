# Architecture

**Analysis Date:** 2026-03-08

## Pattern Overview

**Overall:** Flat-module pipeline architecture with dual entry points (CLI + HTTP) feeding into shared templates and rendering engines.

**Key Characteristics:**
- No src/ directory, no packages -- all Python modules live at the project root
- Dual entry points (CLI and HTTP server) call the same template functions
- Image-based text rendering: markdown and dictionary content is rendered to PIL Images, then sent to the printer as raster data -- this bypasses ESC/POS font limitations
- Configuration-driven: all layout, fonts, dither settings, and printer connection params come from `config.yaml`
- Single global printer connection managed as module-level state

## Layers

**Entry Points (Interface Layer):**
- Purpose: Accept user input via CLI args or HTTP requests, parse it, connect to printer, and delegate to templates/renderers
- Location: `print_cli.py`, `print_server.py`, `print.sh`
- Contains: Argument parsing, HTTP route handlers, connection setup
- Depends on: `printer_core`, `templates`, `image_printer`, `image_slicer`, `portrait_pipeline`
- Used by: End users, systemd service, web UI

**Templates (Layout Layer):**
- Purpose: Define print layouts -- how data is arranged on the receipt
- Location: `templates.py`
- Contains: `receipt()`, `simple_message()`, `label()`, `two_column_list()`, `dictionary_entry()`, `markdown()`
- Depends on: `printer_core.Formatter`, `md_renderer`, PIL for dictionary image rendering
- Used by: `print_cli.py`, `print_server.py`

**Renderers (Image Generation Layer):**
- Purpose: Convert content (markdown text, photos) into 1-bit PIL Images suitable for thermal printing
- Location: `md_renderer.py`, `image_printer.py`, `image_slicer.py`
- Contains: Markdown parser, text-to-image renderer, dithering algorithms (Floyd-Steinberg, Bayer, halftone), image slicing
- Depends on: PIL/Pillow, font files in `fonts/`
- Used by: `templates.py`, `print_cli.py`, `print_server.py`, `portrait_pipeline.py`

**Printer Core (Hardware Abstraction Layer):**
- Purpose: Manage printer connection and provide high-level text formatting commands
- Location: `printer_core.py`
- Contains: `load_config()`, `connect()`, `Formatter` class
- Depends on: `python-escpos` library (Usb, Network, Dummy backends), `pyyaml`
- Used by: All other modules

**Portrait Pipeline (Optional Specialty Module):**
- Purpose: AI-driven portrait-to-sculpture transformation with face-landmark-based zoom cropping
- Location: `portrait_pipeline.py`
- Contains: Photo selection via OpenRouter API, style transfer via n8n webhook, face detection via mediapipe, multi-zoom print output
- Depends on: `image_printer`, `printer_core`, `numpy`, `mediapipe`, `requests`
- Used by: `print_cli.py` (portrait command), `print_server.py` (/portrait/* endpoints)
- Note: Optional -- imported with try/except; server starts without numpy/mediapipe

**Configuration:**
- Purpose: Centralized settings for all modules
- Location: `config.yaml`
- Contains: Printer connection params, server settings, template defaults, font style definitions (dictionary/helvetica/acidic), halftone settings, portrait pipeline config
- Used by: All modules via `printer_core.load_config()`

**Web UI:**
- Purpose: Browser-based interface for printing from any device on the network
- Location: `templates/index.html`
- Contains: Single-page HTML/CSS/JS app with markdown editor, image upload, quick actions
- Depends on: HTTP API endpoints in `print_server.py`

## Data Flow

**CLI Print Flow:**

1. User runs `./print.sh <command> [args]` which activates venv and calls `print_cli.py`
2. `main()` parses args with argparse, loads config via `load_config()`
3. `connect()` creates USB/Network/Dummy printer instance
4. `Formatter` wraps the printer with high-level text commands
5. Command handler calls a template function (e.g., `templates.receipt()`) or directly uses image pipeline
6. Template renders content: text templates use `Formatter` ESC/POS commands directly; markdown and dictionary render to PIL Image first
7. Printer receives ESC/POS commands or raster image data

**HTTP Print Flow:**

1. Client POSTs JSON to endpoint (e.g., `/print/markdown`)
2. Flask route handler extracts data from request
3. `with_retry()` acquires `_print_lock` (threading.Lock) for USB serialization
4. Lambda wraps the template call: `lambda fmt: templates.markdown(fmt, data["text"], ...)`
5. If print fails, `reconnect()` closes and re-opens the USB connection, retries once
6. Returns JSON response `{"status": "ok", "template": "..."}`

**Image Rendering Flow (markdown/dictionary):**

1. Template function calls `md_renderer.render_markdown()` or `_render_dictionary_image()`
2. Renderer loads fonts from `config.yaml` paths (with fallback chain: configured path -> Linux system fonts -> bundled Burra fonts)
3. Two-pass rendering: first pass measures text to calculate total image height, second pass draws onto PIL Image
4. Returns 1-bit PIL Image (mode "1", white=1, black=0)
5. Template calls `fmt.p.image(img)` to send raster data to printer

**Photo Print Flow:**

1. `process_image()` opens image, handles EXIF rotation, drops alpha channel
2. `_prepare()` resizes to paper width (576px), converts to greyscale, applies contrast/brightness/sharpness
3. `_apply_blur()` applies optional Gaussian blur
4. Dithering function converts greyscale to 1-bit: `_dither_floyd()`, `_dither_bayer()`, or `_dither_halftone()`
5. Result sent to printer as raster image

**State Management:**
- CLI: No persistent state. Each invocation creates a fresh printer connection
- Server: Global `_printer` object persists for the server lifetime. `_print_lock` (threading.Lock) serializes all print operations. `reconnect()` replaces the global on failure
- Config: Loaded once at startup, passed by reference to all functions

## Key Abstractions

**Formatter:**
- Purpose: High-level formatting API that wraps raw ESC/POS commands into readable operations
- Examples: `printer_core.py` lines 30-159
- Pattern: Wrapper/Facade -- each method (e.g., `title()`, `left_right()`, `columns()`) sets ESC/POS attributes, prints text, then resets attributes
- Key detail: `self.p` is the underlying python-escpos printer object; `self.w` is paper width in characters (48 for 80mm)

**Font Style Configs:**
- Purpose: Define complete visual identity for text-to-image rendering
- Examples: `dictionary`, `helvetica`, `acidic` sections in `config.yaml`
- Pattern: Each style is a top-level YAML key containing font paths, sizes, spacing, margins. The style name is passed as a string (e.g., `style="dictionary"`) and used to look up the config section

**Dithering Modes:**
- Purpose: Convert greyscale images to 1-bit for thermal printing with different visual aesthetics
- Examples: `_MODES` dict in `image_printer.py` line 125
- Pattern: Strategy pattern via dict lookup. Each mode is a function `(Image) -> Image`

**with_retry():**
- Purpose: Thread-safe print execution with automatic reconnection on failure
- Examples: `print_server.py` lines 85-96
- Pattern: Accepts a callable `fn(formatter)`, wraps it in `_print_lock`, catches exceptions, reconnects, and retries once

## Entry Points

**CLI (`print_cli.py`):**
- Location: `print_cli.py`
- Triggers: `./print.sh <command>` or `python print_cli.py <command>`
- Responsibilities: Parse CLI args, load config, connect to printer, dispatch to command handler
- Commands: `test`, `message`, `receipt`, `label`, `dictionary`, `image`, `slice`, `portrait`, `md`

**HTTP Server (`print_server.py`):**
- Location: `print_server.py`
- Triggers: `python print_server.py` (or systemd service `pos-printer`)
- Responsibilities: Start Flask app on port 9100, register Bonjour/mDNS, handle HTTP print requests
- Endpoints: `POST /print/receipt`, `/print/message`, `/print/label`, `/print/list`, `/print/dictionary`, `/print/image`, `/print/markdown`, `/portrait/capture`, `/portrait/transform`, `GET /health`, `GET /`

**Shell Wrapper (`print.sh`):**
- Location: `print.sh`
- Triggers: Direct user invocation
- Responsibilities: Activate venv and forward args to `print_cli.py`

**Setup Script (`setup.sh`):**
- Location: `setup.sh`
- Triggers: First-time setup on macOS or Raspberry Pi
- Responsibilities: Install system deps, create venv, install pip packages, set up systemd/launchd auto-start service, configure udev rules and kernel module blacklist

## Error Handling

**Strategy:** Minimal -- exceptions propagate to caller. Server has retry-once-with-reconnect pattern.

**Patterns:**
- Server: `with_retry()` catches any exception during printing, calls `reconnect()`, retries once. If retry fails, exception propagates to Flask error handler
- Server: Global `@app.errorhandler(Exception)` returns JSON `{"error": str(e)}` with appropriate HTTP status code (`print_server.py` line 305)
- CLI: No try/except in command handlers -- exceptions crash with traceback
- Portrait pipeline: Lazy import with `try/except ImportError` for optional numpy/mediapipe dependencies (`print_cli.py` lines 22-26, `print_server.py` lines 47-51)
- Font loading: Fallback chain in `md_renderer._load_font()` -- tries configured path, then Linux system fonts, then bundled Burra fonts (`md_renderer.py` lines 94-121)

## Cross-Cutting Concerns

**Logging:** Server uses Python `logging` module (`logger = logging.getLogger(__name__)`) for warning/error messages. CLI and other modules use `print()` statements with `[TAG]` prefixes (e.g., `[PORTRAIT]`, `[INFO]`, `[OK]`, `[DUMMY]`).

**Validation:** Minimal. Server endpoints call `request.get_json(force=True)` without schema validation. CLI relies on argparse for argument validation. No input sanitization on print content.

**Authentication:** None. HTTP endpoints are completely open. No auth middleware or API keys.

**Configuration:** Single `config.yaml` file loaded via `printer_core.load_config()`. All modules receive config as a dict parameter. No env-var-based config except `OPENROUTER_API_KEY` for portrait pipeline.

**Service Discovery:** Bonjour/mDNS registration via `zeroconf` library in `print_server.py` `register_mdns()` -- allows iPads/devices to discover the printer on the local network.

---

*Architecture analysis: 2026-03-08*
