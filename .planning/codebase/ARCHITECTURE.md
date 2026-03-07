# Architecture

**Analysis Date:** 2026-03-07

## Pattern Overview

**Overall:** Flat module architecture with dual entry points (CLI + HTTP), shared template layer, and image-based rendering pipeline.

**Key Characteristics:**
- No framework-imposed structure; pure Python modules in a flat directory
- Two entry points (CLI and HTTP server) calling the same template functions
- Image-based text rendering: markdown and dictionary content is rasterized to 1-bit PIL Images, then sent as raster data to the printer (bypassing ESC/POS font limitations)
- Configuration-driven: all font sizes, spacing, dithering params, and template settings live in `config.yaml`
- Printer abstraction via python-escpos: USB, Network, and Dummy backends behind a single `connect()` call

## Layers

**Entry Points (Interface Layer):**
- Purpose: Accept user input via CLI args or HTTP requests, parse/validate, dispatch to templates
- Location: `print_cli.py`, `print_server.py`
- Contains: Argument parsing (argparse), Flask route handlers, printer connection management
- Depends on: `printer_core`, `templates`, `image_printer`, `image_slicer`, `portrait_pipeline`
- Used by: End users (CLI) and network clients (HTTP)

**Templates (Layout Layer):**
- Purpose: Define print layouts that compose Formatter calls and image rendering into complete printable documents
- Location: `templates.py`
- Contains: `receipt()`, `simple_message()`, `label()`, `two_column_list()`, `dictionary_entry()`, `markdown()`
- Depends on: `printer_core.Formatter`, `md_renderer`, PIL for dictionary image rendering
- Used by: `print_cli.py`, `print_server.py`

**Rendering (Image Pipeline Layer):**
- Purpose: Convert text/markdown/photos into 1-bit PIL Images suitable for thermal printing
- Location: `md_renderer.py`, `image_printer.py`, `image_slicer.py`
- Contains: Markdown parser + rasterizer, dithering algorithms (Floyd-Steinberg, Bayer, halftone), image slicing for poster prints
- Depends on: PIL/Pillow, config font paths
- Used by: `templates.py` (markdown rendering), `print_cli.py` and `print_server.py` (image printing)

**Portrait Pipeline (Specialized Feature Layer):**
- Purpose: AI-driven portrait-to-statue transformation with multi-zoom printing
- Location: `portrait_pipeline.py`
- Contains: Photo selection via OpenRouter vision API, style transfer via n8n webhook, face landmark detection via mediapipe, zoom crop computation
- Depends on: `image_printer` (dithering functions), `printer_core`, OpenRouter API, n8n webhook, mediapipe
- Used by: `print_cli.py` (portrait command), `print_server.py` (/portrait/* endpoints)

**Printer Core (Hardware Abstraction Layer):**
- Purpose: Abstract printer hardware and provide high-level text formatting
- Location: `printer_core.py`
- Contains: `load_config()`, `connect()`, `Formatter` class
- Depends on: `python-escpos` (Usb, Network, Dummy), PyYAML
- Used by: All other layers

**Configuration:**
- Purpose: Centralize all tunable parameters
- Location: `config.yaml`
- Contains: Printer connection settings, server host/port, template defaults (receipt header/footer), font style definitions (dictionary, helvetica, acidic), halftone defaults, portrait pipeline settings
- Used by: All layers via `load_config()`

## Data Flow

**CLI Print (text-based templates):**

1. User runs `./print.sh <command> [args]` which execs `print_cli.py` via venv Python
2. `main()` parses args, calls `load_config()`, dispatches to `cmd_*` handler
3. Handler calls `connect()` to get a printer object, creates `Formatter(printer, width)`
4. Handler calls a template function (e.g., `templates.receipt(fmt, data, config)`)
5. Template composes `Formatter` method calls (title, text, columns, line, cut)
6. `Formatter` translates each call to `python-escpos` printer commands
7. `python-escpos` sends ESC/POS bytes to USB/Network/Dummy

**CLI Print (image-based templates - markdown/dictionary):**

1. Same as above through step 3
2. Template calls `md_renderer.render_markdown()` or `_render_dictionary_image()`
3. Renderer loads fonts from paths in `config.yaml`, parses text, measures/wraps, draws onto a PIL `Image.new("1", ...)` (1-bit black/white)
4. Template calls `fmt.p.image(img)` to send the PIL Image as raster data
5. `python-escpos` converts PIL Image to ESC/POS raster commands

**HTTP Print:**

1. Client POSTs JSON to `http://<host>:9100/print/<template>`
2. Flask route handler extracts data from `request.get_json()`
3. `with_retry()` wrapper calls the template function, reconnecting on failure
4. Same template/formatter/printer flow as CLI

**Image Print (dithering pipeline):**

1. `process_image(path, config)` in `image_printer.py`
2. `_prepare()`: resize to 576px width, convert to greyscale, apply contrast/brightness/sharpness
3. `_apply_blur()`: optional Gaussian blur
4. Dither function (`_dither_floyd`, `_dither_bayer`, or `_dither_halftone`): convert greyscale to 1-bit
5. Return 1-bit PIL Image; caller sends via `printer.image()`

**Portrait Pipeline:**

1. Stage A: `select_best_photo()` sends all images to OpenRouter vision model, gets back best photo index
2. Stage B: `transform_to_statue()` sends selected photo + style prompt to n8n webhook (which calls Gemini 2.5 Flash Image)
3. Stage C: `detect_face_landmarks()` uses mediapipe FaceMesh; `compute_zoom_crops()` calculates 4 crop regions; each crop is dithered and printed sequentially

**State Management:**
- No persistent state; each print job is stateless
- HTTP server holds a global `_printer` connection, reconnected on failure via `with_retry()`
- Config is loaded once at startup (`load_config()`) and passed through call chains
- Portrait pipeline mutates config dict in-place for blur/dither overrides (minor side effect)

## Key Abstractions

**Formatter:**
- Purpose: High-level text layout API that maps semantic operations (title, left_right, columns) to ESC/POS commands
- Examples: `printer_core.py` lines 30-160
- Pattern: Facade over `python-escpos` printer object; stores printer reference (`self.p`) and paper width (`self.w`)

**Font Style Config Sections:**
- Purpose: Define complete typographic profiles (font files, sizes, spacing, margins) reusable across templates
- Examples: `config.yaml` sections `dictionary`, `helvetica`, `acidic`
- Pattern: Config-driven strategy; `md_renderer.render_markdown()` accepts a `style` parameter that selects a config section by name

**Dithering Modes:**
- Purpose: Pluggable image-to-1-bit conversion algorithms
- Examples: `image_printer.py` - `_MODES` dict maps `"halftone"`, `"floyd"`, `"bayer"` to functions
- Pattern: Strategy pattern via function dict; add new modes by adding to `_MODES`

**Templates:**
- Purpose: Reusable print layouts that accept structured data
- Examples: `templates.py` - `receipt()`, `simple_message()`, `label()`, `dictionary_entry()`, `markdown()`
- Pattern: Each template is a plain function taking `(Formatter, data, config)` and calling Formatter methods

## Entry Points

**CLI (`print_cli.py`):**
- Location: `print_cli.py`
- Triggers: `./print.sh <command>` or `python print_cli.py <command>`
- Responsibilities: Parse CLI args, load config, connect to printer, dispatch to command handler
- Commands: `test`, `message`, `receipt`, `label`, `dictionary`, `image`, `slice`, `portrait`, `md`

**HTTP Server (`print_server.py`):**
- Location: `print_server.py`
- Triggers: `python print_server.py [--dummy]`, then HTTP POST requests
- Responsibilities: Start Flask server on port 9100, register mDNS/Bonjour service, handle print requests with retry logic
- Routes: `/` (web UI), `/health`, `/print/receipt`, `/print/message`, `/print/label`, `/print/list`, `/print/dictionary`, `/print/image`, `/print/markdown`, `/portrait/capture`, `/portrait/transform`

**Shell Wrapper (`print.sh`):**
- Location: `print.sh`
- Triggers: Direct shell invocation
- Responsibilities: Activate venv and exec `print_cli.py` with all args forwarded

**Portrait Pipeline standalone (`portrait_pipeline.py`):**
- Location: `portrait_pipeline.py` (has `if __name__ == "__main__"` block)
- Triggers: `python portrait_pipeline.py <images> [--dummy]`
- Responsibilities: Run the full portrait pipeline independently for testing

## Error Handling

**Strategy:** Minimal; exceptions propagate to caller. HTTP server has a single retry-on-failure pattern.

**Patterns:**
- `with_retry(fn)` in `print_server.py`: catches any exception on first attempt, reconnects printer, retries once. No error response differentiation.
- CLI commands have no try/catch; exceptions crash with traceback
- `portrait_pipeline.py` raises `RuntimeError` for missing API keys or webhook failures
- Image operations assume valid file paths; no graceful handling of missing files

## Cross-Cutting Concerns

**Logging:** Print statements to stdout (e.g., `print("[OK] ...")`, `print("[PORTRAIT] ...")`). No logging framework.

**Validation:** Minimal. HTTP endpoints call `request.get_json(force=True)` with no schema validation. CLI uses argparse for basic type checking.

**Authentication:** None. HTTP server is open; CORS is permissive (`CORS(app)`). Intended for local/trusted network use.

**Service Discovery:** mDNS/Bonjour registration via `zeroconf` in `print_server.py` for iPad/mobile discovery on local network.

---

*Architecture analysis: 2026-03-07*
