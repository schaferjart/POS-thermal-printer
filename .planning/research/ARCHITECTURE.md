# Architecture Patterns

**Domain:** Flat-module Python Flask appliance server hardening
**Researched:** 2026-03-08

## Recommended Architecture

Keep the flat module structure. The project explicitly values simplicity and the module count is small enough (8 Python files) that packages/blueprints would add ceremony without solving real problems. Instead, introduce two new modules (`validators.py` and `helpers.py`) and a `tests/` directory, surgically addressing reliability gaps without restructuring.

### Target Structure After Hardening

```
POS/
  print_cli.py            # CLI entry point (unchanged role)
  print_server.py         # HTTP server (add auth, size limits, validation calls)
  printer_core.py         # Printer connection + Formatter (add state guards)
  templates.py            # Print layouts (remove duplicate helpers, import from helpers)
  md_renderer.py          # Markdown-to-image (remove duplicate helpers, import from helpers)
  image_printer.py        # Dithering pipeline (unchanged role)
  image_slicer.py         # Image slicing (use open_image from helpers)
  portrait_pipeline.py    # AI portrait (use open_image from helpers)
  validators.py           # NEW: Request schemas + validation decorators
  helpers.py              # NEW: Shared utilities extracted from duplicates
  config.yaml             # Configuration (add auth key)
  fonts/
  templates/
  tests/                  # NEW: pytest test suite
    conftest.py           # Shared fixtures (dummy printer, sample images, config)
    test_md_renderer.py   # Markdown parsing + image rendering
    test_image_printer.py # Dithering algorithms
    test_validators.py    # Schema validation
    test_templates.py     # Template output (image dimensions, no crashes)
    test_server.py        # Flask test client integration tests
    fixtures/             # Reference images, sample markdown, sample JSON
      sample.md
      sample_receipt.json
      ref_images/         # Snapshot reference images for visual regression
```

### Component Boundaries

| Component | Responsibility | Communicates With | Changes in Hardening |
|-----------|---------------|-------------------|---------------------|
| `print_server.py` | HTTP interface, auth gate, request lifecycle | `validators.py`, `templates.py`, `image_printer.py`, `printer_core.py` | Add auth decorator, validation calls, MAX_CONTENT_LENGTH, graceful shutdown |
| `print_cli.py` | CLI interface, arg parsing | `templates.py`, `image_printer.py`, `printer_core.py` | Minor: use `helpers.open_image()` |
| `validators.py` | Request shape validation, error formatting | Used by `print_server.py` only | NEW module |
| `helpers.py` | `resolve_font_path()`, `wrap_text()`, `open_image()` | Used by `templates.py`, `md_renderer.py`, `image_printer.py`, `image_slicer.py` | NEW module (extracted from duplicates) |
| `printer_core.py` | Printer connection, Formatter text commands | Used by entry points and templates | Add `font_b_text()` method, try/finally state guards |
| `templates.py` | Print layout functions | `printer_core.Formatter`, `md_renderer.py`, `helpers.py` | Remove duplicate `_resolve_font_path`, `wrap_text`; import from `helpers` |
| `md_renderer.py` | Markdown parsing, image rendering | `helpers.py`, PIL/Pillow | Remove duplicate `_resolve_font_path`; import from `helpers` |
| `image_printer.py` | Image dithering pipeline | `helpers.py`, PIL/Pillow | Use `helpers.open_image()` |
| `image_slicer.py` | Image slicing for posters | `helpers.py`, PIL/Pillow | Replace `_open()` with `helpers.open_image()` |
| `tests/` | Automated verification | All modules | NEW directory |

### Data Flow

**HTTP Request Flow (hardened):**

```
Client POST
  |
  v
Flask receives request
  |
  +-- MAX_CONTENT_LENGTH check (Flask built-in, rejects >N MB)
  |
  +-- @require_api_key decorator (validators.py)
  |     Checks X-API-Key header against config value
  |     Returns 401 JSON if missing/wrong
  |
  +-- Route handler extracts data
  |
  +-- validators.validate_<template>(data) called
  |     Returns (clean_data, None) on success
  |     Returns (None, error_dict) on failure -> 400 JSON response
  |
  +-- with_retry(lambda fmt: templates.<template>(fmt, data, config))
  |     Acquires _print_lock
  |     Creates Formatter (state always starts clean)
  |     Calls template
  |     On failure: reconnect + retry once
  |
  +-- JSON response {"status": "ok", "template": "..."}
```

**Key change:** Validation happens BEFORE acquiring the print lock. Bad requests never touch the printer.

## Patterns to Follow

### Pattern 1: Validation Module with Pure Functions (not classes)

Use plain functions that take a dict and return a validated dict or raise. No Pydantic dependency -- the project values minimal dependencies and the schemas are simple enough for hand-written validation. Pydantic would add 4+ MB to the Pi's RAM footprint for what amounts to ~15 field checks.

**What:** A `validators.py` module with one validation function per endpoint, plus a decorator for auth.
**When:** Every POST endpoint in `print_server.py`.
**Why not Pydantic:** Pi 3 has 1GB RAM with a 400MB systemd cap. Pydantic v2 pulls in `pydantic-core` (Rust compiled), which is heavy and may have aarch64 wheel issues. The validation logic here is 50 lines total.

```python
# validators.py

from functools import wraps
from flask import request, jsonify

def require_api_key(config):
    """Decorator factory: checks X-API-Key header against config."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            key = config.get("server", {}).get("api_key")
            if not key:
                return f(*args, **kwargs)  # no key configured = open access
            provided = request.headers.get("X-API-Key", "")
            if not hmac.compare_digest(provided, key):
                return jsonify({"error": "Invalid or missing API key"}), 401
            return f(*args, **kwargs)
        return decorated
    return decorator


def validate_receipt(data):
    """Validate receipt endpoint payload. Returns (data, None) or (None, error)."""
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object"
    items = data.get("items")
    if not isinstance(items, list) or len(items) == 0:
        return None, "Field 'items' is required and must be a non-empty list"
    for i, item in enumerate(items):
        if "name" not in item:
            return None, f"items[{i}] missing 'name'"
        if "price" not in item:
            return None, f"items[{i}] missing 'price'"
        if not isinstance(item["price"], (int, float)):
            return None, f"items[{i}].price must be a number"
    return data, None


def validate_markdown(data):
    """Validate markdown endpoint payload."""
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object"
    if not data.get("text"):
        return None, "Field 'text' is required and must be non-empty"
    if not isinstance(data["text"], str):
        return None, "Field 'text' must be a string"
    valid_styles = ("dictionary", "helvetica", "acidic")
    style = data.get("style", "dictionary")
    if style not in valid_styles:
        return None, f"'style' must be one of: {', '.join(valid_styles)}"
    return data, None

# ... one per endpoint
```

**Confidence:** HIGH -- this is the standard minimal-dependency approach for small Flask apps.

### Pattern 2: Shared Helpers Extracted from Duplicates

**What:** A `helpers.py` module containing the three duplicated utilities.
**When:** Create before any other refactoring -- other changes depend on this.

```python
# helpers.py
"""Shared utilities for the POS thermal print system."""

import os
from PIL import Image, ImageDraw, ImageFont, ImageOps

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_FONTS_DIR = os.path.join(_PROJECT_DIR, "fonts")
FONT_THIN = os.path.join(_FONTS_DIR, "Burra-Thin.ttf")
FONT_BOLD = os.path.join(_FONTS_DIR, "Burra-Bold.ttf")


def resolve_font_path(path):
    """Resolve a font path relative to the project root."""
    if os.path.isabs(path):
        return path
    return os.path.join(_PROJECT_DIR, path)


def wrap_text(text, font, max_width, draw=None):
    """Word-wrap text to fit within max_width pixels."""
    if draw is None:
        draw = ImageDraw.Draw(Image.new("1", (1, 1)))
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines or [""]


def open_image(path):
    """Open an image, handle EXIF rotation, drop alpha channel."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "PA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    return img
```

**Confidence:** HIGH -- these are exact copies across 2-3 modules. Extract is trivial and safe.

### Pattern 3: Formatter State Guards with try/finally

**What:** Ensure every Formatter method that changes printer state resets it, even if the template throws mid-print.
**When:** Phase where `printer_core.py` is hardened.

```python
# In Formatter class -- add a context manager method:
def bold_block(self):
    """Context manager for bold text that guarantees state reset."""
    class BoldContext:
        def __init__(self, fmt):
            self.fmt = fmt
        def __enter__(self):
            self.fmt.p.set(bold=True)
            return self.fmt
        def __exit__(self, *exc):
            self.fmt.p.set(bold=False)
            return False
    return BoldContext(self)

# Also add the missing font_b_text method to replace raw ESC/POS in server:
def font_b_text(self, text):
    """Print text in smaller Font B (replaces raw ESC/POS commands)."""
    self.p.set(font="b")
    self.p.text(f"{text}\n")
    self.p.set(font="a")
```

**Confidence:** HIGH -- standard Python resource management pattern.

### Pattern 4: Flask Test Client for Integration Tests

**What:** Use Flask's built-in test client instead of curl-based stress tests for automated, repeatable testing.
**When:** After validators.py exists (so you can test validation too).

```python
# tests/conftest.py
import pytest
from printer_core import load_config, Formatter
from escpos.printer import Dummy

@pytest.fixture
def config():
    return load_config("config.yaml")

@pytest.fixture
def dummy_printer():
    return Dummy()

@pytest.fixture
def formatter(dummy_printer, config):
    width = config.get("printer", {}).get("paper_width", 48)
    return Formatter(dummy_printer, width)

@pytest.fixture
def app(config):
    """Create Flask test app with dummy printer."""
    import print_server
    print_server._config = config
    print_server._printer = Dummy()
    print_server._dummy = True
    print_server.app.config["TESTING"] = True
    return print_server.app

@pytest.fixture
def client(app):
    return app.test_client()
```

```python
# tests/test_server.py
def test_markdown_returns_ok(client):
    resp = client.post("/print/markdown",
        json={"text": "# Hello\nWorld"})
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

def test_markdown_missing_text_returns_400(client):
    resp = client.post("/print/markdown", json={})
    assert resp.status_code == 400
    assert "error" in resp.json
```

**Confidence:** HIGH -- Flask's test client is the standard way to test Flask apps.

### Pattern 5: Image Snapshot Testing for Rendering

**What:** Test that `md_renderer.render_markdown()` and `image_printer.process_image()` produce correct output by comparing against reference images.
**When:** After helpers extraction (rendering tests need stable font paths).

```python
# tests/test_md_renderer.py
from PIL import ImageChops, ImageStat
from md_renderer import render_markdown

def _images_match(img_a, img_b, tolerance=0.5):
    """Compare two images. Returns True if mean pixel difference < tolerance."""
    if img_a.size != img_b.size:
        return False
    diff = ImageChops.difference(img_a.convert("L"), img_b.convert("L"))
    stat = ImageStat.Stat(diff)
    return stat.mean[0] < tolerance

def test_heading_renders(config):
    img = render_markdown("# Hello", config, show_date=False)
    assert img.mode == "1"  # 1-bit image
    assert img.size[0] == 576  # paper width
    assert img.size[1] > 50  # not degenerate height

def test_empty_string_does_not_crash(config):
    img = render_markdown("", config, show_date=False)
    assert img is not None
    assert img.size[0] == 576
```

**Confidence:** HIGH for property-based tests (dimensions, mode, no-crash). MEDIUM for pixel-perfect snapshot testing (font rendering can vary across OS/Pillow versions -- use on Pi only or accept tolerance).

### Pattern 6: Request Size Limiting

**What:** Set Flask's `MAX_CONTENT_LENGTH` to protect Pi's 400MB memory cap.
**When:** Earliest possible -- this is a one-line config change.

```python
# In print_server.py main():
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB
```

10 MB is generous for thermal printing (images are typically resized to 576px wide, resulting in small files). This prevents a single request from exhausting the Pi's RAM.

**Confidence:** HIGH -- Flask built-in mechanism, well documented.

### Pattern 7: Graceful Shutdown

**What:** Clean up mDNS registration and close printer connection on SIGTERM/SIGINT.
**When:** After core hardening is done.

```python
# In print_server.py:
import signal

def graceful_shutdown(signum, frame):
    """Clean up resources on shutdown."""
    logger.info("Shutting down...")
    if _zeroconf:
        try:
            _zeroconf.unregister_all_services()
            _zeroconf.close()
        except Exception:
            pass
    if _printer:
        try:
            _printer.close()
        except Exception:
            pass
    sys.exit(0)

# In main():
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)
```

**Confidence:** HIGH -- standard signal handling pattern. The existing atexit handler only fires on clean exit, not on SIGTERM from systemd.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Restructuring into a Python Package

**What:** Wrapping modules in a `src/pos/` package with `__init__.py`.
**Why bad:** Adds import complexity (`from pos.templates import receipt`), breaks all existing scripts, `print.sh`, and the systemd service. Solves no actual problem -- the flat structure works because there are <10 modules.
**Instead:** Keep flat modules. Add `helpers.py` and `validators.py` at the root alongside existing modules.

### Anti-Pattern 2: Using Flask Blueprints

**What:** Splitting routes into blueprint modules.
**Why bad:** There are 10 routes total. Blueprints add indirection (finding which file handles `/print/markdown` requires checking blueprint registrations) for zero benefit at this scale.
**Instead:** Keep all routes in `print_server.py`. Group them with comments. Use validators.py for the validation logic that would otherwise bloat the route handlers.

### Anti-Pattern 3: Adding Pydantic/marshmallow for Validation

**What:** Installing a heavyweight validation library.
**Why bad:** Pydantic v2 with pydantic-core adds ~15MB to disk and ~4MB to RSS on the Pi. The entire validation need here is checking ~5 fields per endpoint (is it a string? is it a list? is it a number?). That is 50 lines of Python, not a library.
**Instead:** Hand-written validation functions in `validators.py`. One function per endpoint, pure Python, zero dependencies.

### Anti-Pattern 4: Abstract Base Classes for Printer Backends

**What:** Creating an ABC hierarchy for USB/Network/Dummy printer backends.
**Why bad:** `python-escpos` already provides this abstraction. The `Formatter` class wraps it cleanly. Adding another layer creates a leaky abstraction sandwich.
**Instead:** Keep `Formatter` wrapping `python-escpos` directly. Add methods to Formatter when raw ESC/POS commands appear elsewhere (like `font_b_text()`).

### Anti-Pattern 5: Test Suite that Requires Hardware

**What:** Tests that need a real printer or network access.
**Why bad:** Can't run in CI, can't run on dev machine, wastes paper.
**Instead:** All tests use `Dummy()` printer. Image tests check PIL output dimensions/mode/pixel values. Server tests use Flask test client. `stress_test.sh` remains as the hardware integration test (run manually).

## Scalability Considerations

This project is a single-printer appliance. "Scalability" means surviving edge cases, not handling 10K users.

| Concern | Current State | After Hardening |
|---------|---------------|-----------------|
| Memory (400MB cap) | No request size limit; large image upload could OOM | MAX_CONTENT_LENGTH=10MB; rejects before buffering |
| Bad input | Returns 500 with traceback-like error | Returns 400 with clear JSON error message |
| Auth | Open to all network devices | API key in header (opt-in via config) |
| Crash recovery | systemd restarts (max 3/60s) | Same, but fewer crashes due to validation |
| USB contention | Thread lock, retry-once | Same pattern, but Formatter state guaranteed clean |
| Test coverage | stress_test.sh (curl, needs running server) | pytest suite (runs without hardware or server) |

## Refactoring Order (Build Dependencies)

Changes must happen in this order because later steps depend on earlier ones:

```
1. helpers.py (extract shared utils)
   |
   +-- templates.py, md_renderer.py, image_slicer.py, image_printer.py
   |   import from helpers instead of defining their own copies
   |
2. validators.py (create validation + auth)
   |
   +-- print_server.py calls validators before with_retry()
   |
3. printer_core.py (add font_b_text, state guards)
   |
   +-- print_server.py removes raw ESC/POS calls, uses fmt.font_b_text()
   |
4. print_server.py (MAX_CONTENT_LENGTH, graceful shutdown, config mutation fix)
   |
5. tests/ (requires all of the above to be stable)
   |
   +-- conftest.py + test_md_renderer.py + test_image_printer.py (pure rendering)
   +-- test_validators.py (pure validation logic)
   +-- test_server.py (Flask test client, needs validators + helpers)
   +-- test_templates.py (needs formatter + helpers)
```

**Rationale:** `helpers.py` is the foundation because templates and renderers depend on shared utilities being in one place. `validators.py` is next because it is self-contained (no imports from other project modules). Formatter state guards come before server changes because the server uses Formatter. Tests come last because they test the hardened code, not the pre-hardening state.

## Sources

- [Flask Security Considerations (official docs)](https://flask.palletsprojects.com/en/stable/web-security/)
- [Flask File Upload Patterns (MAX_CONTENT_LENGTH)](https://flask.palletsprojects.com/en/stable/patterns/fileuploads/)
- [Flask API Key Authentication Pattern](https://blog.teclado.com/api-key-authentication-with-flask/)
- [Testing Image Generation with PIL (Jacob Kaplan-Moss)](https://jacobian.org/til/testing-image-generation/)
- [python-escpos documentation](https://python-escpos.readthedocs.io/en/latest/user/usage.html)
- [pytest-image-snapshot for visual regression](https://pypi.org/project/pytest-image-snapshot/)
- [Pillow test suite patterns](https://github.com/python-pillow/Pillow/blob/main/Tests/test_image.py)
- [Flask-Pydantic (considered, rejected for weight)](https://pypi.org/project/Flask-Pydantic/)

---

*Architecture research: 2026-03-08*
