# Coding Conventions

**Analysis Date:** 2026-03-08

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `print_cli.py`, `printer_core.py`, `image_printer.py`, `md_renderer.py`, `image_slicer.py`, `portrait_pipeline.py`
- Use `snake_case.sh` for shell scripts: `print.sh`, `setup.sh`, `stress_test.sh`, `run_portrait.sh`
- Config is a single `config.yaml` at project root

**Functions:**
- Use `snake_case` for all functions: `connect()`, `load_config()`, `process_image()`, `render_markdown()`
- CLI handler functions use `cmd_` prefix: `cmd_test()`, `cmd_message()`, `cmd_receipt()`, `cmd_image()` in `print_cli.py`
- Private/internal functions use `_` prefix: `_prepare()`, `_apply_blur()`, `_dither_floyd()`, `_dither_halftone()`, `_render_dictionary_image()`, `_resolve_font_path()`, `_parse_inline()`, `_parse_md()`
- Flask route functions match the endpoint pattern: `print_receipt()`, `print_message()`, `print_label()` in `print_server.py`

**Variables:**
- Use `snake_case` for all variables: `paper_px`, `line_spacing`, `dot_size`
- Short abbreviations are acceptable for frequently used locals: `w`, `h` (width/height), `img`, `fmt` (formatter), `cfg` (config section), `p` (printer)
- Module-level constants use `_UPPER_SNAKE` with leading underscore: `_BAYER_8x8`, `_MODES`, `_FONTS_DIR`, `_FONT_THIN`, `_FONT_BOLD`, `_INLINE_RE`
- Global mutable state in `print_server.py` uses `_lower_snake` with leading underscore: `_config`, `_printer`, `_dummy`, `_zeroconf`, `_print_lock`

**Classes:**
- Use `PascalCase`: `Formatter` (the only class in the codebase, in `printer_core.py`)

**Config Keys:**
- Use `snake_case` in `config.yaml`: `paper_width`, `vendor_id`, `font_word`, `line_spacing`

## Code Style

**Formatting:**
- No formatter configured (no `.prettierrc`, `.editorconfig`, `pyproject.toml`, or `setup.cfg`)
- Consistent 4-space indentation throughout all Python files
- Single blank line between functions within a class or module
- Double blank line between top-level definitions (classes, standalone functions)
- f-strings used exclusively for string formatting (no `%` or `.format()`)

**Linting:**
- No linter configured (no `.flake8`, `pylint`, `ruff`, or `mypy` config)
- No type checking tool
- Type hints used sparingly: function signatures in `templates.py` use them (`fmt: Formatter`, `data: dict`, `config: dict`), return types are not annotated
- `list[str]` and `list[tuple[str, str]]` used (Python 3.9+ syntax) in `templates.py` and `portrait_pipeline.py`

**Line Length:**
- No enforced limit; lines occasionally exceed 100 characters, especially in `print_server.py` lambda expressions (line 202)

## Import Organization

**Order:**
1. Standard library imports: `os`, `sys`, `io`, `math`, `re`, `json`, `time`, `socket`, `base64`, `textwrap`, `argparse`, `tempfile`, `threading`, `logging`, `atexit`, `datetime`
2. Third-party imports: `flask`, `flask_cors`, `zeroconf`, `yaml`, `PIL`, `numpy`, `requests`, `mediapipe`
3. Local imports: `printer_core`, `templates`, `image_printer`, `image_slicer`, `portrait_pipeline`, `md_renderer`

**Style:**
- Use `from X import Y` for specific items: `from printer_core import load_config, connect, Formatter`
- Use `import X` for module-level access: `import templates`
- Conditional imports for optional dependencies wrapped in try/except at module level:
```python
try:
    from portrait_pipeline import run_pipeline
    _has_portrait = True
except ImportError:
    _has_portrait = False
```
- Lazy imports used inside functions when needed only for specific code paths: `from PIL import ImageOps, ImageEnhance, ImageFilter` inside `cmd_slice()` in `print_cli.py`; `import mediapipe as mp` inside `detect_face_landmarks()` in `portrait_pipeline.py`

**Path Aliases:**
- None. All imports are relative module names (flat project structure).

## Error Handling

**Patterns:**
- **Server endpoints:** Global Flask error handler in `print_server.py` catches all exceptions and returns JSON: `{"error": str(e)}` with appropriate HTTP status code
- **Print retry:** `with_retry()` in `print_server.py` wraps print operations with mutex lock, catches first failure, reconnects printer, retries once, then raises on second failure
- **Bare except for cleanup:** `except Exception: pass` used for non-critical cleanup (closing printer before reconnect in `reconnect()`, deleting temp files in `portrait_capture()`)
- **CLI handlers:** No try/except — exceptions propagate to the user as stack traces
- **Missing dependencies:** Guarded with `_has_portrait` boolean flag; CLI prints helpful install instructions and exits with `sys.exit(1)`; server returns HTTP 501 with JSON error
- **Input validation:** Minimal — server uses `request.get_json(force=True)` which raises on invalid JSON. Missing required fields cause KeyError, caught by global handler
- **Config access:** Uses `.get()` with defaults throughout: `cfg.get("paper_px", 576)`, `cfg.get("mode", "floyd")`
- **Raise patterns:** Use `RuntimeError` for configuration/setup errors (missing API keys, webhook URLs) in `portrait_pipeline.py`; `ValueError` for invalid arguments in `image_printer.py`

## Logging

**Framework:** Mixed — `logging` module in `print_server.py`, `print()` everywhere else

**Server logging:**
```python
logger = logging.getLogger(__name__)
logger.warning("Print failed (%s), reconnecting...", e)
logger.error("Retry also failed: %s", e2)
logger.error("Request error: %s", e)
```

**Console output pattern:**
- Use bracketed prefixes for status messages: `[OK]`, `[DUMMY]`, `[INFO]`, `[WARN]`, `[PORTRAIT]`
- Examples:
```python
print("[OK] Test page printed")
print("[DUMMY] Preview saved to {out}")
print("[INFO] Server listening on http://{host}:{port}")
print("[PORTRAIT] AI selected photo {idx + 1}/{len(image_paths)}")
print(f"[md_renderer] Font fallback: {resolved} -> {candidate}")
```

## Comments

**When to Comment:**
- Module-level docstrings describe purpose and usage for every `.py` file
- Function docstrings on public functions describe parameters and expected data shapes (especially `data` dicts with example structures in `templates.py`)
- Section comments use `# --- Section Name ---` pattern in longer functions
- Inline comments for non-obvious ESC/POS byte sequences: `b'\x1b\x21\x01'  # ESC ! 0x01: Font B`
- Comments in `config.yaml` describe every key

**Docstring Style:**
- Triple-quoted multi-line docstrings
- No formal docstring format (not Google/NumPy/reST style)
- Data structure examples included inline:
```python
def receipt(fmt: Formatter, data: dict, config: dict):
    """
    Standard receipt template.

    data = {
        "items": [
            {"name": "Coffee", "qty": 2, "price": 5.00},
        ],
        "payment_method": "Card",   # optional
    }
    """
```

## Function Design

**Size:**
- Functions are generally 10-40 lines
- Largest functions: `render_markdown()` in `md_renderer.py` (~120 lines), `_render_dictionary_image()` in `templates.py` (~110 lines) — these are rendering pipelines with measurement + draw passes

**Parameters:**
- Use keyword arguments with defaults for optional parameters: `mode=None, dot_size=None, contrast=None`
- Config dict passed through function chains: `config: dict` parameter threaded from CLI/server to templates
- `None` used as sentinel, resolved against config inside function: `mode = mode or cfg.get("mode", "floyd")`
- Use `is not None` check when `0` or `0.0` is a valid value: `contrast = contrast if contrast is not None else cfg.get("contrast", 1.3)`

**Return Values:**
- Template functions return `None` (side-effect: print to printer)
- Image processing functions return `PIL.Image.Image`
- Renderer functions return `PIL.Image.Image`
- `connect()` returns a printer object (Usb, Network, or Dummy)
- `load_config()` returns a `dict`

## Module Design

**Exports:**
- No `__all__` defined in any module
- No `__init__.py` — flat module structure, not a package
- Public API is implicit: functions without `_` prefix are public

**Barrel Files:**
- Not used. Each module is imported directly by name.

## Configuration Pattern

**Centralized config:**
- All settings in `config.yaml` loaded via `load_config()` from `printer_core.py`
- Config dict threaded through all function calls
- CLI/server args override config values; config values override hardcoded defaults
- Pattern for reading a config section:
```python
cfg = (config or {}).get("halftone", {})
paper_px = cfg.get("paper_px", 576)
```

**Adding new font styles:**
- Copy an existing style block in `config.yaml` (e.g., `dictionary`, `helvetica`, `acidic`)
- Reference from CLI: `--style mystyle`
- The style name is the config section key

## CLI Pattern

**Command dispatch:**
- `argparse` with subparsers in `print_cli.py`
- Each subcommand has a `cmd_*` handler function taking `(args, config)`
- Command-to-function mapping via dict: `cmds = {"test": cmd_test, "message": cmd_message, ...}`
- Global `--dummy` and `--config` flags on the parent parser

## Server Endpoint Pattern

**Adding new endpoints in `print_server.py`:**
1. Define a Flask route function with `@app.route("/print/<name>", methods=["POST"])`
2. Parse request with `data = request.get_json(force=True)`
3. Wrap the print call in `with_retry(lambda fmt: templates.your_template(fmt, data, _config))`
4. Return `jsonify({"status": "ok", "template": "<name>"})`

**Thread safety:**
- All print operations go through `with_retry()` which acquires `_print_lock` (a `threading.Lock()`)
- Never call printer directly from a route handler without the lock

---

*Convention analysis: 2026-03-08*
