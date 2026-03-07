# Coding Conventions

**Analysis Date:** 2026-03-07

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `print_cli.py`, `printer_core.py`, `image_printer.py`, `md_renderer.py`, `image_slicer.py`, `portrait_pipeline.py`
- Entry point files are prefixed with `print_`: `print_cli.py`, `print_server.py`
- Shell wrapper: `print.sh`

**Functions:**
- Use `snake_case` throughout: `cmd_test()`, `process_image()`, `render_markdown()`, `select_best_photo()`
- CLI handler functions prefixed with `cmd_`: `cmd_test()`, `cmd_message()`, `cmd_receipt()`, `cmd_image()`, `cmd_markdown()` in `print_cli.py`
- Private/internal functions prefixed with `_`: `_prepare()`, `_apply_blur()`, `_dither_floyd()`, `_dither_halftone()`, `_resolve_font_path()`, `_render_dictionary_image()`, `_parse_inline()`, `_parse_md()`
- Flask route handlers prefixed with `print_`: `print_receipt()`, `print_message()`, `print_label()`, `print_image()` in `print_server.py`

**Variables:**
- Use `snake_case` for all variables: `paper_px`, `dot_size`, `line_spacing`, `font_body`
- Short abbreviations acceptable for local scope: `w`, `h` (width/height), `p` (printer), `fmt` (formatter), `cfg` (config section), `img` (image), `lm` (landmarks)
- Config dict keys use `snake_case`: `paper_width`, `vendor_id`, `font_word`, `size_body`
- Module-level private constants prefixed with `_`: `_BAYER_8x8`, `_MODES`, `_FONTS_DIR`, `_FONT_THIN`, `_INLINE_RE`

**Classes:**
- Use `PascalCase`: `Formatter` in `printer_core.py` (the only class in the codebase)

**Type Hints:**
- Used on public function signatures but not internal ones
- Pattern: `def receipt(fmt: Formatter, data: dict, config: dict):`
- Return types annotated on image-producing functions: `-> Image.Image`
- Not used on CLI handlers, local helper functions, or variables

## Code Style

**Formatting:**
- No formatter configured (no `.prettierrc`, `pyproject.toml`, `.editorconfig`, etc.)
- Consistent 4-space indentation throughout
- Max line length approximately 100-120 characters (not enforced)
- Blank line between function definitions; two blank lines between top-level definitions

**Linting:**
- No linter configured (no `.flake8`, `pylintrc`, `ruff.toml`, etc.)
- Code is clean and consistent despite no tooling

**String Formatting:**
- Use f-strings exclusively: `f"[OK] Receipt printed ({len(data.get('items', []))} items)"`
- Console output uses bracket-prefix convention: `[OK]`, `[DUMMY]`, `[INFO]`, `[WARN]`, `[PORTRAIT]`

## Import Organization

**Order:**
1. Standard library imports: `import os`, `import sys`, `import json`, `import math`, `import re`
2. Third-party imports: `from PIL import Image`, `from flask import Flask`, `import yaml`, `import requests`
3. Local project imports: `from printer_core import load_config, connect, Formatter`, `import templates`

**Style:**
- Mix of `import module` and `from module import name` — use whichever is cleaner
- Group related imports on one line: `from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps`
- Lazy imports inside functions for optional/heavy dependencies:
  ```python
  # In portrait_pipeline.py
  def detect_face_landmarks(image):
      import mediapipe as mp
  ```
  ```python
  # In print_cli.py cmd_slice()
  from PIL import ImageOps, ImageEnhance, ImageFilter
  ```

**Path Aliases:**
- None used. All imports are direct module references in the flat project structure.

## Error Handling

**Patterns:**
- Raise `RuntimeError` with descriptive messages for configuration/setup errors:
  ```python
  if not api_key:
      raise RuntimeError("OPENROUTER_API_KEY not set. Export it or set portrait.openrouter_api_key_env in config.")
  ```
- Raise `ValueError` for invalid user input:
  ```python
  raise ValueError(f"Unknown dither mode '{mode}'. Choose from: {', '.join(_MODES)}")
  ```
- Use `resp.raise_for_status()` for HTTP errors (lets `requests.HTTPError` propagate)
- Server retry pattern in `print_server.py` — `with_retry()` catches any `Exception` and reconnects once:
  ```python
  def with_retry(fn):
      try:
          fn(get_formatter())
      except Exception:
          fn(reconnect())
  ```
- File cleanup with `try/finally` (not context managers) for temp files:
  ```python
  tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
  try:
      # ... use tmp ...
  finally:
      os.unlink(tmp.name)
  ```
- No custom exception classes — use built-in `RuntimeError` and `ValueError` only
- No error handling in CLI handlers — exceptions propagate to terminal

## Logging

**Framework:** `print()` statements only — no logging module

**Patterns:**
- Bracket-prefixed messages for status: `print(f"[OK] Receipt printed")`
- Prefixes used: `[OK]`, `[DUMMY]`, `[INFO]`, `[WARN]`, `[PORTRAIT]`
- Server uses `[INFO]` for startup messages, `[WARN]` for non-fatal issues (e.g., Bonjour registration failure)
- Portrait pipeline uses `[PORTRAIT]` prefix for all pipeline status messages
- CLI uses `[OK]` for success, `[DUMMY]` when running without hardware

## Comments

**When to Comment:**
- Module-level docstrings on every `.py` file explaining purpose and usage
- Docstrings on all public functions describing parameters and data shapes
- Inline comments for non-obvious logic (e.g., ESC/POS byte sequences, Bayer matrix values, mediapipe landmark indices)
- Section comments using `# --- Section Name ---` or `# -- Section Name --` pattern:
  ```python
  # --- Header ---
  # --- Date/time ---
  # --- Column headers ---
  ```
- Stage labels in pipeline code: `# Stage A: Photo selection`, `# Stage B: Style transfer`

**Docstrings:**
- Use triple-quote docstrings with description on first line
- Data structure expectations documented in docstrings with example dicts:
  ```python
  def receipt(fmt: Formatter, data: dict, config: dict):
      """
      Standard receipt template.
      data = {
          "items": [{"name": "Coffee", "qty": 2, "price": 5.00}],
          "payment_method": "Card",
      }
      """
  ```
- No type-level docstring conventions (only one class)

## Function Design

**Size:**
- Functions are moderate length (10-60 lines typically)
- `render_markdown()` in `md_renderer.py` is the longest at ~210 lines — it combines parsing and rendering in one function with nested helpers

**Parameters:**
- Config values use the override pattern: CLI/server args override config values, config overrides defaults:
  ```python
  mode = mode or cfg.get("mode", "floyd")
  contrast = contrast if contrast is not None else cfg.get("contrast", 1.3)
  ```
- Use `None` as default for optional numeric params to distinguish "not provided" from `0`/`0.0`
- Pass `config` dict sections, not individual values, to template functions

**Return Values:**
- Image-producing functions return `PIL.Image.Image`
- Template functions return `None` (side-effect: prints to printer)
- `run_pipeline()` returns `(selected_path, image)` tuple

## Module Design

**Exports:**
- No `__all__` defined in any module — all public functions are importable
- No barrel files or `__init__.py` (flat module structure)
- Private functions prefixed with `_` are still imported directly where needed:
  ```python
  from image_printer import process_image, _prepare, _apply_blur, _dither_floyd, _dither_bayer, _dither_halftone
  ```

**Globals:**
- Server module uses module-level globals for printer state: `_config`, `_printer`, `_dummy`, `_zeroconf` in `print_server.py`
- Module-level constants prefixed with `_` for private, UPPER_CASE for semantic constants: `_BAYER_8x8`, `_MODES`, `_FONTS_DIR`

## Configuration Pattern

- All configuration lives in `config.yaml` — loaded via `load_config()` from `printer_core.py`
- Config is a nested dict passed to functions; each module extracts its section:
  ```python
  cfg = (config or {}).get("halftone", {})
  ```
- Default values provided inline via `.get(key, default)` — no separate defaults dict
- Font style configs (dictionary, helvetica, acidic) are top-level YAML sections with identical key structure — add a new style by copying a block

## CLI Pattern

- `argparse` with subparsers in `print_cli.py`
- Each subcommand maps to a `cmd_*` function via a dispatch dict:
  ```python
  cmds = {"test": cmd_test, "message": cmd_message, ...}
  cmds[args.command](args, config)
  ```
- All subcommands accept `--dummy` (inherited from parent parser)
- Handler signature: `def cmd_*(args, config):`

## Server Pattern

- Flask with module-level globals, no application factory
- All print endpoints follow: parse JSON -> `with_retry(lambda fmt: template_fn(fmt, ...))` -> return `jsonify({"status": "ok", ...})`
- File upload endpoints use `tempfile.NamedTemporaryFile(delete=False)` with manual cleanup
- CORS enabled globally via `flask-cors`
- mDNS/Bonjour registration at startup with `atexit` cleanup

---

*Convention analysis: 2026-03-07*
