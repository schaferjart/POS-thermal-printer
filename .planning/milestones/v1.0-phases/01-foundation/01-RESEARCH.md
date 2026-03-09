# Phase 1: Foundation - Research

**Researched:** 2026-03-08
**Domain:** Python code deduplication, config validation, module extraction
**Confidence:** HIGH

## Summary

Phase 1 is a surgical refactoring phase -- no new features, no new dependencies, no architectural changes. The work is: (1) extract three duplicated utilities into a new `helpers.py` module, (2) update all consumers to import from `helpers.py` instead of defining their own copies, and (3) add startup config validation to `print_server.py` so missing required keys cause a clear failure at boot, not a cryptic crash at print time.

All three utility functions (`resolve_font_path`, `wrap_text`, `open_image`) have been directly observed as duplicates in the codebase with nearly identical implementations. The extraction is mechanically straightforward. The config validation is ~30 lines of hand-rolled Python checking a known set of keys. No new dependencies are needed.

**Primary recommendation:** Create `helpers.py` first (imports nothing from the project), then update consumers one file at a time (templates.py, md_renderer.py, image_printer.py, image_slicer.py, portrait_pipeline.py), then add config validation to print_server.py. Each step is independently testable with `--dummy` mode.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| QUAL-01 | Shared font path resolution extracted to `helpers.py`, used by `templates.py` and `md_renderer.py` | Duplicate `_resolve_font_path` found at `templates.py:134` and `md_renderer.py:29` -- identical logic, trivial extract |
| QUAL-02 | Shared `wrap_text` function extracted to single location, used by `templates.py` and `md_renderer.py` | Duplicate `wrap_text` found at `templates.py:171` (inside `_render_dictionary_image`) and `md_renderer.py:225` (inside `render_markdown`) -- near-identical, both are closures that need to become a standalone function |
| QUAL-03 | Shared image-open logic (EXIF transpose + alpha removal) extracted to single location, used by `image_printer.py`, `image_slicer.py`, `portrait_pipeline.py` | Duplicate open+transpose+alpha pattern found at: `image_printer.py:152-159`, `image_slicer.py:10-17` (`_open`), `portrait_pipeline.py:106-111`, `portrait_pipeline.py:413-418` |
| REL-06 | Server validates `config.yaml` on startup and fails fast with clear message if required keys are missing | Currently `load_config()` in `printer_core.py:10-12` does a bare `yaml.safe_load()` with no validation. Server crashes at print time, not startup, when keys are missing |
</phase_requirements>

## Standard Stack

### Core

No new libraries needed. This phase uses only what's already installed.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pillow | 12.1.1 | `Image.open`, `ImageOps.exif_transpose`, `ImageDraw`, `ImageFont` | Already in requirements.txt, used by `open_image` and `wrap_text` |
| PyYAML | 6.0.3 | Config loading (`yaml.safe_load`) | Already in requirements.txt, used by `load_config` |
| python-escpos | 3.1 | `Dummy` printer for testing | Already in requirements.txt |

### Supporting

None. Phase 1 introduces zero new dependencies.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled config validation | pydantic, cerberus, jsonschema | Overkill -- checking 4 keys doesn't justify a dependency. Locked decision from roadmap: "Hand-rolled validation over pydantic" |

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### New Module: `helpers.py`

```
POS/
  helpers.py              # NEW: resolve_font_path, wrap_text, open_image
  templates.py            # MODIFIED: remove _resolve_font_path, wrap_text; import from helpers
  md_renderer.py          # MODIFIED: remove _resolve_font_path; use helpers.wrap_text
  image_printer.py        # MODIFIED: use helpers.open_image
  image_slicer.py         # MODIFIED: remove _open; use helpers.open_image
  portrait_pipeline.py    # MODIFIED: use helpers.open_image in two places
  printer_core.py         # MODIFIED: add validate_config function
  print_server.py         # MODIFIED: call validate_config at startup
```

### Pattern 1: Zero-Import Utility Module

**What:** `helpers.py` imports ONLY from the standard library and Pillow. It imports NOTHING from the project (no `printer_core`, no `templates`, no `md_renderer`). This is a locked decision from the roadmap to prevent circular imports.

**When to use:** Always. This is the foundational constraint for this module.

**Why critical:** The current codebase has no shared utility module. Both `templates.py` and `md_renderer.py` already import from `printer_core`. If `helpers.py` also imported from `printer_core`, and `printer_core` later needed a helper, you'd get a circular import. By keeping `helpers.py` leaf-only, it can be imported by any module safely.

**Example:**
```python
# helpers.py
"""Shared utilities for the POS thermal print system.
This module imports NOTHING from the project — only stdlib and Pillow.
"""

import os
from PIL import Image, ImageDraw, ImageFont, ImageOps

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_FONTS_DIR = os.path.join(_PROJECT_DIR, "fonts")
FONT_THIN = os.path.join(_FONTS_DIR, "Burra-Thin.ttf")
FONT_BOLD = os.path.join(_FONTS_DIR, "Burra-Bold.ttf")
```

### Pattern 2: `resolve_font_path` -- Exact Current Behavior

**What:** Resolve relative font paths against the project root directory.

**Current implementations (identical):**
- `templates.py:134-138` -- `_resolve_font_path(path)`
- `md_renderer.py:29-32` -- `_resolve_font_path(path)`

Both do the same thing: check if path is absolute (return as-is), otherwise join with `os.path.dirname(os.path.abspath(__file__))`. Since all Python files live at the project root, the base directory is the same in both cases.

**Extracted version:**
```python
def resolve_font_path(path):
    """Resolve a font path relative to the project root.
    Absolute paths are returned unchanged."""
    if os.path.isabs(path):
        return path
    return os.path.join(_PROJECT_DIR, path)
```

**Note:** The function is renamed from `_resolve_font_path` (private) to `resolve_font_path` (public) since it's now a module-level export.

### Pattern 3: `wrap_text` -- Unify Two Implementations

**What:** Word-wrap text to fit within a pixel width, using Pillow's `textbbox` for measurement.

**Current implementations (near-identical):**
- `templates.py:171-186` -- closure inside `_render_dictionary_image`, uses `scratch.textbbox`
- `md_renderer.py:225-240` -- closure inside `render_markdown`, uses local `text_width` function

Key differences:
1. `md_renderer.py` version has a `hard_wrap` branch (lines 226-227) that delegates to `_hard_wrap`. The `helpers.py` version should NOT include hard_wrap -- that's `md_renderer`-specific logic.
2. Both versions use a `draw` object for `textbbox`. The shared version should accept an optional `draw` parameter.
3. Return value: `templates.py` returns `lines` (may be empty list), `md_renderer.py` returns `lines or [""]`. Use `lines or [""]` for safety.

**Extracted version:**
```python
def wrap_text(text, font, max_width, draw=None):
    """Word-wrap text to fit within max_width pixels.
    Uses Pillow textbbox for measurement."""
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
```

**Integration notes for `md_renderer.py`:**
- The `render_markdown` function's local `wrap_text` closure has extra `hard_wrap` logic. After extraction, the local function should call `helpers.wrap_text` for the soft-wrap case and `_hard_wrap` for the hard-wrap case. Or the local closure can simply delegate:
  ```python
  def wrap_text(text, font, max_w):
      if hard_wrap:
          return _hard_wrap(text, font, max_w, text_width)
      return helpers.wrap_text(text, font, max_w, scratch)
  ```
- The `templates.py` `_render_dictionary_image` function can replace its closure entirely with `helpers.wrap_text(text, font, usable, scratch)`.

### Pattern 4: `open_image` -- Consolidate EXIF + Alpha Handling

**What:** Open an image file, apply EXIF rotation, remove alpha channel (paste onto white background).

**Current implementations (4 locations):**
1. `image_printer.py:152-159` -- inline in `process_image()`
2. `image_slicer.py:10-17` -- `_open(path)` private function
3. `portrait_pipeline.py:106-111` -- inline in `transform_to_statue()`
4. `portrait_pipeline.py:413-418` -- inline in `run_pipeline()` (skip_transform branch)

All four are functionally identical. The `image_slicer.py` version is already a standalone function (`_open`). The others are inline code.

**Extracted version:**
```python
def open_image(path):
    """Open an image, apply EXIF rotation, and remove alpha channel.
    Alpha channels are composited onto a white background."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "PA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    return img
```

**Integration notes:**
- `image_printer.py:152-159` -- replace inline code with `from helpers import open_image; img = open_image(path)`
- `image_slicer.py:10-17` -- delete `_open()`, replace `_open(path)` calls with `open_image(path)`
- `portrait_pipeline.py:106-111` -- replace inline code with `open_image(image_path)`
- `portrait_pipeline.py:413-418` -- replace inline code with `open_image(selected)`
- `portrait_pipeline.py:143` (`Image.open(io.BytesIO(img_data))`) -- do NOT replace this one. It opens from bytes, not a file path, and the data is already clean (no EXIF, no alpha from API response).

### Pattern 5: Config Validation -- Fail Fast at Startup

**What:** Check that `config.yaml` contains all required keys before starting the server. Print a clear error naming the missing key and exit.

**Required keys** (derived from reading all config consumers in `printer_core.py` and `print_server.py`):

| Key Path | Used By | What Happens If Missing |
|----------|---------|------------------------|
| `printer.vendor_id` | `printer_core.connect()` line 27 | `KeyError` at first print if USB mode |
| `printer.product_id` | `printer_core.connect()` line 27 | `KeyError` at first print if USB mode |
| `printer.paper_width` | `print_server.py` lines 68, 81 | Falls back to 48 (has `.get` default) -- optional |
| `server.host` | `print_server.py` line 361 | Falls back to "0.0.0.0" -- optional |
| `server.port` | `print_server.py` line 362 | Falls back to 9100 -- optional |

The requirements say: "required keys (USB IDs, paper width, server port)". So the validation should check:
- `printer` section exists
- `printer.vendor_id` exists
- `printer.product_id` exists
- `printer.paper_width` exists (even though current code has a fallback -- the requirement explicitly wants it validated)
- `server` section exists
- `server.port` exists (even though current code has a fallback)

**Implementation location:** Add a `validate_config(config)` function. It should live in `printer_core.py` alongside `load_config()` since config loading and validation are closely related. The function raises `SystemExit` with a clear message.

**Example:**
```python
def validate_config(config):
    """Validate that required config keys are present.
    Raises SystemExit with a clear message if any are missing."""
    required = {
        "printer.vendor_id": ("printer", "vendor_id"),
        "printer.product_id": ("printer", "product_id"),
        "printer.paper_width": ("printer", "paper_width"),
        "server.port": ("server", "port"),
    }
    for label, path in required.items():
        section = config
        for key in path:
            if not isinstance(section, dict) or key not in section:
                print(f"[FATAL] config.yaml: missing required key '{label}'")
                sys.exit(1)
            section = section[key]
```

**Where to call it:** In `print_server.py main()`, immediately after `_config = load_config(args.config)`, before connecting to the printer:
```python
_config = load_config(args.config)
validate_config(_config)  # fails fast with clear error
```

**Not in CLI:** The CLI tool (`print_cli.py`) doesn't need startup validation -- it runs a single command and exits. Missing config keys will produce immediate errors that are obvious in interactive use. The requirement specifically says "Server refuses to start."

### Anti-Patterns to Avoid

- **Moving `_load_font` to helpers.py:** The `_load_font` function in `md_renderer.py` is NOT a simple wrapper around font path resolution. It has fallback logic for macOS-to-Linux font mapping and bundled font fallback chains. It should stay in `md_renderer.py`. Only `resolve_font_path` (the path resolution step) moves to helpers.
- **Making `helpers.py` import from the project:** This creates circular import risk. `helpers.py` must only import `os`, `PIL.*`. No `printer_core`, no `templates`, no `md_renderer`.
- **Changing function signatures:** The extracted functions must have the same behavior as the originals. Don't add parameters, change defaults, or alter return types. The refactoring should be invisible to callers (except the import path changes).
- **Combining extract and behavior changes:** Extract first, verify everything works, THEN (in future phases) change behavior. Mixing refactoring with feature work is how bugs hide.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing | Custom parser | `yaml.safe_load()` (already used) | PyYAML is already a dependency and handles all YAML edge cases |
| Image EXIF handling | Manual EXIF tag reading | `ImageOps.exif_transpose()` (already used) | Pillow handles all orientation tag combinations; manual EXIF is error-prone |
| Text measurement | Character counting | `ImageDraw.textbbox()` (already used) | Pixel-accurate measurement accounts for kerning and font metrics |

**Key insight:** This phase doesn't introduce any new problem domains. It's purely moving existing, working code to a shared location.

## Common Pitfalls

### Pitfall 1: Circular Imports

**What goes wrong:** `helpers.py` imports from `printer_core.py`, which is imported by `templates.py`, which imports `helpers.py` -- circular.
**Why it happens:** Natural temptation to put `load_config` or `Formatter` references in helpers.
**How to avoid:** `helpers.py` imports ONLY `os` and `PIL.*`. This is a locked decision.
**Warning signs:** `ImportError: cannot import name 'X' from partially initialized module` at startup.

### Pitfall 2: wrap_text Closure Variables

**What goes wrong:** The `wrap_text` in both `templates.py` and `md_renderer.py` are closures that capture a `scratch` (ImageDraw) object from the enclosing scope. When extracting to `helpers.py`, forgetting to pass `draw` as a parameter means the function creates a new scratch surface on every call.
**Why it happens:** Closures hide their dependencies.
**How to avoid:** The extracted `wrap_text` takes an optional `draw` parameter. Callers that already have a scratch surface pass it in for efficiency. Callers that don't (one-off use) let the default `None` trigger a temporary surface.
**Warning signs:** Subtle performance regression (unlikely to be noticeable at this scale, but bad practice).

### Pitfall 3: md_renderer wrap_text Has Extra Logic

**What goes wrong:** Replacing the `md_renderer.py` local `wrap_text` entirely with `helpers.wrap_text` breaks `hard_wrap` mode (used by the `acidic` style).
**Why it happens:** The `md_renderer.py` version checks a `hard_wrap` config flag and delegates to `_hard_wrap` for character-level wrapping. This is style-specific logic that doesn't belong in a shared helper.
**How to avoid:** Keep the local wrapper in `md_renderer.py` that handles the `hard_wrap` branch, and delegate the soft-wrap case to `helpers.wrap_text`.
**Warning signs:** Printing with `--style acidic` produces incorrect wrapping.

### Pitfall 4: portrait_pipeline Has Two Open-Image Locations

**What goes wrong:** Only replacing one of the two duplicate open-image blocks in `portrait_pipeline.py`.
**Why it happens:** Lines 106-111 and lines 413-418 are far apart in the file, easy to miss one.
**How to avoid:** Search for `exif_transpose` in `portrait_pipeline.py` -- there are exactly two hits that need replacing. A third `Image.open` at line 143 is for bytes-from-API and should NOT be changed.
**Warning signs:** EXIF-rotated portraits print sideways when using the skip_transform path.

### Pitfall 5: Config Validation Checks Wrong Keys

**What goes wrong:** Validating keys that have `.get()` defaults (like `server.host`) as required, or missing keys that are truly needed (like `printer.vendor_id`).
**Why it happens:** Not carefully checking which config accesses use `config["key"]` (will crash) vs `config.get("key", default)` (has fallback).
**How to avoid:** The requirement explicitly lists: USB IDs, paper width, server port. Validate exactly those. Don't over-validate optional keys.
**Warning signs:** Server refuses to start with a valid config because an optional key was marked required.

### Pitfall 6: Config Validation in Dummy Mode

**What goes wrong:** Config validation checks for `printer.vendor_id` and `printer.product_id`, but in `--dummy` mode the server doesn't use USB at all. If someone runs `--dummy` without configuring real USB IDs, validation fails unnecessarily.
**Why it happens:** Validation doesn't account for dummy mode.
**How to avoid:** Either skip USB-related validation when `--dummy` is passed, or make the check only warn (not fail) for USB keys. The simplest approach: always validate -- the config should be correct even in dummy mode. This is the safer choice because it catches misconfigurations before deployment.
**Warning signs:** Developer can't test with `--dummy` because they haven't set up USB IDs yet. Decide based on team preference -- validation always or conditional.

## Code Examples

### Complete `helpers.py` Module

```python
# helpers.py
"""Shared utilities for the POS thermal print system.

This module imports NOTHING from the project — only stdlib and Pillow.
This prevents circular imports since any project module can import helpers.
"""

import os
from PIL import Image, ImageDraw, ImageFont, ImageOps

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_FONTS_DIR = os.path.join(_PROJECT_DIR, "fonts")
FONT_THIN = os.path.join(_FONTS_DIR, "Burra-Thin.ttf")
FONT_BOLD = os.path.join(_FONTS_DIR, "Burra-Bold.ttf")


def resolve_font_path(path):
    """Resolve a font path relative to the project root.
    Absolute paths are returned unchanged."""
    if os.path.isabs(path):
        return path
    return os.path.join(_PROJECT_DIR, path)


def wrap_text(text, font, max_width, draw=None):
    """Word-wrap text to fit within max_width pixels using Pillow textbbox."""
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
    """Open an image, apply EXIF rotation, and remove alpha channel.
    Alpha channels are composited onto a white background."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "PA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    return img
```

### Config Validation Function

```python
# In printer_core.py, add after load_config:
import sys

def validate_config(config):
    """Validate required config keys. Exits with clear error if any missing."""
    required = {
        "printer.vendor_id": ("printer", "vendor_id"),
        "printer.product_id": ("printer", "product_id"),
        "printer.paper_width": ("printer", "paper_width"),
        "server.port": ("server", "port"),
    }
    missing = []
    for label, path in required.items():
        section = config
        for key in path:
            if not isinstance(section, dict) or key not in section:
                missing.append(label)
                break
            section = section[key]
    if missing:
        for key in missing:
            print(f"[FATAL] config.yaml: missing required key '{key}'")
        sys.exit(1)
```

### Consumer Update Pattern (templates.py)

```python
# Before (templates.py):
_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_FONT_THIN = os.path.join(_FONTS_DIR, "Burra-Thin.ttf")
_FONT_BOLD = os.path.join(_FONTS_DIR, "Burra-Bold.ttf")

def _resolve_font_path(path):
    if os.path.isabs(path):
        return path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), path)

# After (templates.py):
from helpers import resolve_font_path, wrap_text, FONT_THIN, FONT_BOLD
# Remove _FONTS_DIR, _FONT_THIN, _FONT_BOLD, _resolve_font_path definitions
# Replace _resolve_font_path(...) calls with resolve_font_path(...)
# Replace _FONT_THIN with FONT_THIN, _FONT_BOLD with FONT_BOLD
```

### Server Startup Validation

```python
# In print_server.py main():
def main():
    global _config, _printer, _dummy

    parser = argparse.ArgumentParser(description="Thermal printer HTTP server")
    parser.add_argument("--dummy", action="store_true")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    _config = load_config(args.config)

    # Fail fast if config is incomplete
    from printer_core import validate_config
    validate_config(_config)

    # ... rest of startup
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Copy-paste utilities | Shared module import | This phase | One place to fix bugs, one place to test |
| Crash at print time on bad config | Fail at startup with named key | This phase | Faster debugging, no wasted paper |

**Deprecated/outdated:**
- Nothing applies. This phase uses stable, mature Python patterns (module imports, `os.path`, Pillow).

## Open Questions

1. **Should config validation skip USB keys in `--dummy` mode?**
   - What we know: `connect()` skips USB when `dummy=True`. Checking USB IDs in dummy mode means devs need valid USB IDs even for testing.
   - What's unclear: Whether the team wants strict validation (always check everything) or lenient (skip USB in dummy).
   - Recommendation: Always validate. The config should be deployment-ready. If a dev needs to test without USB IDs, they can add placeholder values (e.g., `0x0000`).

2. **Should `print_cli.py` also call `validate_config`?**
   - What we know: The requirement says "Server refuses to start." CLI is not mentioned.
   - What's unclear: Whether CLI should also get the same validation.
   - Recommendation: Add validation to server only (per requirement). CLI users get immediate `KeyError` feedback from their single command, which is sufficient.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (not yet installed) |
| Config file | none -- see Wave 0 |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUAL-01 | `resolve_font_path` in helpers.py, imported by templates.py and md_renderer.py | unit | `python -m pytest tests/test_helpers.py::test_resolve_font_path -x` | No -- Wave 0 |
| QUAL-02 | `wrap_text` in helpers.py, imported by templates.py and md_renderer.py | unit | `python -m pytest tests/test_helpers.py::test_wrap_text -x` | No -- Wave 0 |
| QUAL-03 | `open_image` in helpers.py, imported by image_printer.py, image_slicer.py, portrait_pipeline.py | unit | `python -m pytest tests/test_helpers.py::test_open_image -x` | No -- Wave 0 |
| REL-06 | Server exits with clear error when required config keys are missing | unit | `python -m pytest tests/test_helpers.py::test_validate_config -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/` directory -- does not exist
- [ ] `tests/test_helpers.py` -- covers QUAL-01, QUAL-02, QUAL-03, REL-06
- [ ] `tests/conftest.py` -- shared fixtures (sample images, minimal config dicts)
- [ ] Framework install: `pip install pytest` -- not in requirements.txt
- [ ] Smoke test: existing `--dummy` commands still work after refactoring (`./print.sh test --dummy`, `./print.sh md "# Hello" --dummy`)

## Sources

### Primary (HIGH confidence)
- **Codebase direct inspection** -- all duplicate locations verified by reading actual source files:
  - `templates.py:134-138` (`_resolve_font_path`), `templates.py:171-186` (`wrap_text`)
  - `md_renderer.py:29-32` (`_resolve_font_path`), `md_renderer.py:225-240` (`wrap_text`)
  - `image_printer.py:152-159` (open + EXIF + alpha)
  - `image_slicer.py:10-17` (`_open`)
  - `portrait_pipeline.py:106-111`, `portrait_pipeline.py:413-418` (open + EXIF + alpha)
  - `printer_core.py:10-12` (`load_config` with no validation)
  - `print_server.py:349` (config loaded without validation)
- **config.yaml** -- all key paths verified against actual config file
- **Project roadmap decision** -- "helpers.py imports nothing from the project" (STATE.md)
- **Project roadmap decision** -- "Hand-rolled validation over pydantic" (STATE.md)

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` -- helpers.py pattern and config validation pattern
- `.planning/research/PITFALLS.md` -- circular import risk, config validation scope
- `.planning/codebase/CONCERNS.md` -- duplicated code documentation

### Tertiary (LOW confidence)
- None. All findings are from direct codebase inspection.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new deps, purely internal refactoring
- Architecture: HIGH -- all duplicate locations confirmed by reading source
- Pitfalls: HIGH -- pitfalls are about this specific codebase, not general knowledge

**Research date:** 2026-03-08
**Valid until:** Indefinite -- this research is about the current state of the codebase, not external libraries
