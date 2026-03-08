# Phase 4: Test Suite - Research

**Researched:** 2026-03-09
**Domain:** Python pytest test suite for thermal printer system (md_renderer, image_printer, Flask server validation, API auth)
**Confidence:** HIGH

## Summary

Phase 4 adds automated tests for four distinct domains: markdown rendering, image dithering, input validation, and API key authentication. The project already has a substantial test foundation: 55 passing tests across `test_helpers.py`, `test_config.py`, `test_formatter.py`, and `test_server.py` using pytest 9.0.2 with Flask's test client and `escpos.printer.Dummy`.

The existing test infrastructure covers significant portions of TEST-03 (input validation) and TEST-04 (API key auth) already. The primary gaps are TEST-01 (md_renderer parsing -- zero tests) and TEST-02 (image_printer dithering -- zero tests). For TEST-03, the missing pieces are valid-payload success tests for receipt/label/list/dictionary/markdown endpoints and image upload endpoint validation. For TEST-04, the existing auth tests are already comprehensive.

**Primary recommendation:** Add two new test files (`test_md_renderer.py` and `test_image_printer.py`) for the completely uncovered domains, and extend `test_server.py` with missing valid-payload and image-endpoint tests. The existing `conftest.py` fixtures and patterns should be reused.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TEST-01 | pytest test suite for md_renderer markdown parsing (headings, bold, italic, code, lists, blockquotes) | New `test_md_renderer.py` -- test `_parse_md()` block types, `_parse_inline()` style segments, and `render_markdown()` output image properties (mode, width, non-zero height). Uses bundled Burra fonts which are available in-repo. |
| TEST-02 | pytest tests for image_printer dithering functions with known inputs | New `test_image_printer.py` -- test each dither function (`_dither_floyd`, `_dither_bayer`, `_dither_halftone`) with synthetic PIL images. Verify output is mode "1", correct dimensions, pixel values are 0 or 1. Also test `process_image()` end-to-end with temp files. |
| TEST-03 | pytest tests for input validation (valid and invalid payloads for each endpoint) | Partially exists in `test_server.py` (TestValidationMissingFields, TestValidationBadJSON, TestMaxContentLength). Gaps: valid-payload success tests for receipt/label/list/dictionary/markdown, and image endpoint (multipart file upload) validation. |
| TEST-04 | pytest tests for API key auth (with key, without key, wrong key, no key configured) | Already complete in `test_server.py` (TestAuth and TestAuthDisabled classes). Six tests cover all four scenarios. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 9.0.2 | Test runner and framework | Already in requirements.txt and used by existing 55 tests |
| Pillow | 12.1.1 | Image creation/assertion for rendering and dithering tests | Already project dependency, used by md_renderer and image_printer |
| Flask test client | (bundled with Flask 3.1.3) | HTTP endpoint testing without running server | Already used in test_server.py via `app.test_client()` |
| escpos.printer.Dummy | (bundled with python-escpos 3.1) | Mock printer for print operations | Already used in conftest.py fixtures |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| unittest.mock | (stdlib) | MagicMock, patch for isolating dependencies | Already used in test_formatter.py and test_server.py |
| tempfile | (stdlib) | Create temp image files for dithering tests | Already used in conftest.py for sample images |
| io.BytesIO | (stdlib) | Create in-memory image files for multipart upload tests | Needed for image endpoint testing |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest | unittest | pytest already established in project, unittest is more verbose |
| Synthetic test images | Fixture image files committed to repo | Synthetic images via `Image.new()` are deterministic, zero storage overhead, already the pattern in conftest.py |

## Architecture Patterns

### Existing Test Structure (follow this)
```
tests/
    __init__.py          # empty, marks as package
    conftest.py          # shared fixtures: sample images, fonts, Flask clients
    test_helpers.py      # unit tests for helpers.py
    test_config.py       # unit tests for validate_config
    test_formatter.py    # unit tests for Formatter state safety
    test_server.py       # integration tests for Flask endpoints
```

### New Files Needed
```
tests/
    test_md_renderer.py  # NEW: TEST-01 (parsing + rendering)
    test_image_printer.py # NEW: TEST-02 (dithering pipeline)
```

### Pattern 1: Pure Function Unit Tests (md_renderer parsing)
**What:** Test `_parse_md()` and `_parse_inline()` as pure functions -- input string in, structured data out.
**When to use:** For TEST-01 parsing tests. These functions have no side effects or dependencies.
**Example:**
```python
# Source: md_renderer.py lines 149-177 (verified by reading source)
from md_renderer import _parse_md, _parse_inline

def test_parse_md_heading1():
    blocks = _parse_md("# Hello World")
    assert len(blocks) == 1
    assert blocks[0]["type"] == "h1"
    assert blocks[0]["text"] == "Hello World"

def test_parse_inline_bold():
    segments = _parse_inline("normal **bold** text")
    assert segments == [("normal ", "normal"), ("bold", "bold"), (" text", "normal")]
```

### Pattern 2: Image Property Assertions (rendering + dithering)
**What:** Call the function, verify the returned PIL Image has the correct mode, dimensions, and pixel value range.
**When to use:** For TEST-01 render tests and TEST-02 dithering tests. Do not pixel-compare (font rendering varies across platforms) -- assert structural properties.
**Example:**
```python
# Source: image_printer.py lines 100-102, md_renderer.py lines 180-382
from PIL import Image
from image_printer import _dither_floyd

def test_dither_floyd_returns_1bit():
    grey = Image.new("L", (100, 100), 128)
    result = _dither_floyd(grey)
    assert result.mode == "1"
    assert result.size == (100, 100)
```

### Pattern 3: Flask Test Client with Fixtures (server tests)
**What:** Use the existing `client` and `client_with_auth` fixtures from conftest.py.
**When to use:** For TEST-03 valid-payload tests and any auth extension tests.
**Example:**
```python
# Source: conftest.py lines 41-58, test_server.py (existing pattern)
def test_receipt_valid_payload(client):
    resp = client.post("/print/receipt", json={
        "items": [{"name": "Coffee", "qty": 1, "price": 3.50}]
    })
    assert resp.status_code == 200
    assert resp.get_json()["template"] == "receipt"
```

### Anti-Patterns to Avoid
- **Pixel-perfect image comparison:** Font rendering differs across macOS/Linux. Assert mode, dimensions, and non-triviality (image is not all-white) instead of exact pixel values.
- **Testing with real printer connection:** All tests must work with `Dummy` printer or without any printer at all. The `--dummy` flag pattern is for CLI, not tests.
- **Testing Flask app by starting the server:** Use `app.test_client()` (already established pattern in conftest.py).
- **Hardcoded absolute font paths:** Use the bundled `fonts/Burra-*.ttf` files. The `dictionary` style config works on all platforms; `helvetica` style uses macOS-only paths.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP request simulation | Raw socket calls or subprocess curl | Flask `app.test_client()` | Already established, handles headers/JSON/multipart correctly |
| Test image creation | Downloading/committing fixture images | `Image.new("RGB", (W, H), color)` via Pillow | Deterministic, no storage, already the pattern in conftest.py |
| Multipart file upload in tests | Manually constructing multipart bodies | `client.post(data={"file": (BytesIO(data), "test.jpg")})` | Flask test client handles multipart encoding |
| Font loading for md_renderer tests | Mocking font loading | Use `dictionary` style config pointing to bundled `fonts/Burra-*.ttf` | Fonts exist in repo, no need to mock |

**Key insight:** The project already has well-established test patterns. The task is filling coverage gaps, not building new test infrastructure.

## Common Pitfalls

### Pitfall 1: Font Path Dependencies in md_renderer Tests
**What goes wrong:** Tests for `render_markdown()` fail on CI or Pi because they reference macOS-only font paths (helvetica style).
**Why it happens:** The `helvetica` config block uses `/System/Library/Fonts/HelveticaNeue.ttc` which only exists on macOS.
**How to avoid:** Always use the `dictionary` style (default) which references `fonts/Burra-Bold.ttf` and `fonts/Burra-Thin.ttf` bundled in the repo. Or pass a config dict that explicitly points to the bundled fonts.
**Warning signs:** `FileNotFoundError` or `OSError` when running tests on Linux/Pi.

### Pitfall 2: Image Mode Confusion in Dithering Tests
**What goes wrong:** Tests pass a wrong-mode image to dither functions and get unexpected behavior.
**Why it happens:** `_dither_floyd`, `_dither_bayer`, `_dither_halftone` all expect mode "L" (greyscale) input. `_prepare()` converts to "L" in the real pipeline.
**How to avoid:** Create test input as `Image.new("L", ...)`. For `process_image()` end-to-end tests, save an RGB image to a temp file (it handles conversion internally).
**Warning signs:** AttributeError on `pixels[x, y]` returning tuples instead of ints.

### Pitfall 3: Flask Test Client Context Issues
**What goes wrong:** Tests that modify `print_server._config` bleed state into other tests.
**Why it happens:** `print_server` module globals (`_config`, `_printer`, `_dummy`) persist across tests in the same process.
**How to avoid:** Use separate fixtures for auth vs. no-auth scenarios (already done: `client` vs `client_with_auth` in conftest.py). Each fixture sets its own `_config`.
**Warning signs:** Tests pass individually but fail when run together.

### Pitfall 4: Oversized Request Test Timing
**What goes wrong:** The 11MB oversized request test is slow.
**Why it happens:** Generating and sending 11MB of data through Flask's test client takes measurable time.
**How to avoid:** The existing test already handles this correctly. Don't add more oversized payload tests.
**Warning signs:** Test suite taking > 5 seconds.

### Pitfall 5: datetime.now() in render_markdown
**What goes wrong:** Tests that check image content may get inconsistent results because the date stamp changes.
**Why it happens:** `render_markdown()` appends current date/time to the image.
**How to avoid:** Use `show_date=False` parameter in tests, or only assert on image properties (mode, width, height > minimum) rather than pixel content.
**Warning signs:** Flaky tests that pass at certain times of day.

## Code Examples

### md_renderer: Testing _parse_md Block Types
```python
# Source: md_renderer.py lines 149-177 (verified)
from md_renderer import _parse_md

def test_parse_md_all_block_types():
    md = """# Heading 1
## Heading 2
Regular paragraph
- list item
> blockquote
---

"""
    blocks = _parse_md(md)
    types = [b["type"] for b in blocks]
    assert types == ["h1", "h2", "paragraph", "list", "quote", "separator", "blank"]
```

### md_renderer: Testing _parse_inline Styles
```python
# Source: md_renderer.py lines 116-146 (verified)
from md_renderer import _parse_inline

def test_parse_inline_all_styles():
    text = "normal **bold** *italic* ~~strike~~ `code` end"
    segments = _parse_inline(text)
    styles = [s[1] for s in segments]
    assert "bold" in styles
    assert "italic" in styles
    assert "strikethrough" in styles
    assert "code" in styles
    assert "normal" in styles
```

### md_renderer: Testing render_markdown Image Output
```python
# Source: md_renderer.py lines 180-382 (verified)
from md_renderer import render_markdown

def test_render_markdown_returns_1bit_image():
    config = {
        "dictionary": {
            "font_word": "fonts/Burra-Bold.ttf",
            "font_body": "fonts/Burra-Thin.ttf",
            "font_cite": "fonts/Burra-Thin.ttf",
            "font_date": "fonts/Burra-Thin.ttf",
            "paper_px": 576,
            "margin": 20,
            "line_spacing": 1.4,
            "gap_after_word": 30,
            "size_word": 32,
            "size_body": 20,
            "size_cite": 18,
            "size_date": 16,
        }
    }
    img = render_markdown("# Hello\nWorld", config=config, show_date=False)
    assert img.mode == "1"
    assert img.size[0] == 576  # paper width
    assert img.size[1] > 0    # non-zero height
```

### image_printer: Testing Each Dither Mode
```python
# Source: image_printer.py lines 59-122 (verified)
from PIL import Image
from image_printer import _dither_floyd, _dither_bayer, _dither_halftone

def test_dither_floyd():
    grey = Image.new("L", (100, 100), 128)
    result = _dither_floyd(grey)
    assert result.mode == "1"
    assert result.size == (100, 100)

def test_dither_bayer():
    grey = Image.new("L", (100, 100), 128)
    result = _dither_bayer(grey)
    assert result.mode == "1"
    assert result.size == (100, 100)

def test_dither_halftone():
    grey = Image.new("L", (120, 120), 128)  # divisible by dot_size=6
    result = _dither_halftone(grey, dot_size=6)
    assert result.mode == "1"
    assert result.size == (120, 120)
```

### image_printer: Testing process_image End-to-End
```python
# Source: image_printer.py lines 133-164 (verified)
import os, tempfile
from PIL import Image
from image_printer import process_image

def test_process_image_returns_1bit(sample_rgb_image):
    result = process_image(sample_rgb_image, mode="floyd")
    assert result.mode == "1"
    assert result.size[0] == 576  # default paper_px
```

### Flask Test Client: Image Upload Endpoint
```python
# Source: print_server.py lines 199-257 (verified)
from io import BytesIO
from PIL import Image

def test_image_upload_no_file(client):
    resp = client.post("/print/image", data={})
    assert resp.status_code == 400
    assert "No file uploaded" in resp.get_json()["error"]

def test_image_upload_valid(client):
    img = Image.new("RGB", (100, 100), (128, 128, 128))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    resp = client.post("/print/image", data={"file": (buf, "test.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 200
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No tests | 55 tests covering config, formatter, helpers, server validation/auth | Phases 1-3 (2026-03-08) | Strong foundation to extend |
| stress_test.sh (bash integration tests) | pytest unit + integration tests | Phase 4 (this phase) | Faster, more granular, CI-friendly |

**Existing test infrastructure is modern and well-organized.** pytest 9.0.2 is current. No deprecated patterns observed.

## Open Questions

1. **Image endpoint multipart testing with dither modes**
   - What we know: The `/print/image` endpoint accepts optional form fields (mode, dot_size, contrast, etc.)
   - What's unclear: Whether Flask test client properly handles multipart/form-data with both file and form fields in all edge cases
   - Recommendation: Test with basic file upload first, add mode parameter tests if time permits. The dither logic itself is tested directly in test_image_printer.py.

2. **Cross-platform font rendering differences**
   - What we know: Burra fonts are bundled and load on macOS and Linux. Image dimensions are deterministic. Pixel values may differ slightly across platforms.
   - What's unclear: Whether render_markdown produces identical image heights across platforms (font metrics may differ)
   - Recommendation: Assert height > minimum threshold (e.g., > 50px for simple markdown) rather than exact height. Assert width == paper_px (576).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (uses default discovery, `tests/` directory) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | md_renderer parsing: _parse_md produces correct block types for h1, h2, paragraph, list, quote, separator, blank | unit | `python -m pytest tests/test_md_renderer.py::TestParseMd -x` | No -- Wave 0 |
| TEST-01 | md_renderer parsing: _parse_inline produces correct style segments for bold, italic, strikethrough, code | unit | `python -m pytest tests/test_md_renderer.py::TestParseInline -x` | No -- Wave 0 |
| TEST-01 | md_renderer rendering: render_markdown returns 1-bit image with correct width | unit | `python -m pytest tests/test_md_renderer.py::TestRenderMarkdown -x` | No -- Wave 0 |
| TEST-02 | image_printer: each dither function returns 1-bit image with correct dimensions | unit | `python -m pytest tests/test_image_printer.py::TestDitherFunctions -x` | No -- Wave 0 |
| TEST-02 | image_printer: process_image end-to-end returns 1-bit image | unit | `python -m pytest tests/test_image_printer.py::TestProcessImage -x` | No -- Wave 0 |
| TEST-03 | input validation: missing fields return 400 for each JSON endpoint | integration | `python -m pytest tests/test_server.py::TestValidationMissingFields -x` | Yes |
| TEST-03 | input validation: invalid JSON and non-object bodies return 400 | integration | `python -m pytest tests/test_server.py::TestValidationBadJSON -x` | Yes |
| TEST-03 | input validation: oversized requests return 413 | integration | `python -m pytest tests/test_server.py::TestMaxContentLength -x` | Yes |
| TEST-03 | input validation: valid payloads succeed for all endpoints | integration | `python -m pytest tests/test_server.py::TestValidPayloads -x` | No -- Wave 0 |
| TEST-03 | input validation: image endpoint file upload validation | integration | `python -m pytest tests/test_server.py::TestImageEndpoint -x` | No -- Wave 0 |
| TEST-04 | auth: correct key passes, wrong key 401, missing key 401, no config means open | integration | `python -m pytest tests/test_server.py::TestAuth tests/test_server.py::TestAuthDisabled -x` | Yes |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_md_renderer.py` -- covers TEST-01 (parsing and rendering)
- [ ] `tests/test_image_printer.py` -- covers TEST-02 (dithering functions)
- [ ] Extend `tests/test_server.py` with TestValidPayloads class -- covers TEST-03 gaps (valid payloads for receipt/label/list/dictionary/markdown)
- [ ] Extend `tests/test_server.py` with TestImageEndpoint class -- covers TEST-03 gaps (image upload validation)
- [ ] Extend `tests/conftest.py` with dictionary-config fixture for md_renderer tests

## Coverage Gap Summary

| Requirement | Existing Tests | Missing Tests | Effort |
|-------------|---------------|---------------|--------|
| TEST-01 | 0 | ~12 tests (parse_md block types, parse_inline styles, render_markdown properties) | Medium |
| TEST-02 | 0 | ~8 tests (3 dither functions, process_image e2e, edge cases) | Small |
| TEST-03 | 15 tests (validation, bad JSON, oversized, 1 valid, error format) | ~8 tests (valid payloads for 5 remaining endpoints, image endpoint) | Small |
| TEST-04 | 6 tests (all scenarios covered) | 0 | Done |

**Total new tests needed: ~28 across 2 new files and 2 extended files.**

## Sources

### Primary (HIGH confidence)
- Project source code: `md_renderer.py`, `image_printer.py`, `print_server.py`, `printer_core.py`, `helpers.py`, `templates.py` -- all read directly
- Existing test suite: `tests/conftest.py`, `tests/test_helpers.py`, `tests/test_config.py`, `tests/test_formatter.py`, `tests/test_server.py` -- all read directly
- `config.yaml` -- all font and dithering configuration verified
- `requirements.txt` -- pytest >= 7.0 already listed, pytest 9.0.2 installed
- Test suite execution: 55 passed, 1 skipped in 0.68s (verified by running)

### Secondary (MEDIUM confidence)
- None needed -- all findings verified from source code and local execution

### Tertiary (LOW confidence)
- Cross-platform font rendering consistency: assumed Burra fonts produce consistent dimensions but not verified on Pi/Linux

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- pytest, Pillow, Flask test client all verified in-repo and running
- Architecture: HIGH -- existing test patterns are clear, well-organized, and consistent
- Pitfalls: HIGH -- font path issues documented in CLAUDE.md, dithering input requirements verified from source code
- Coverage gaps: HIGH -- exhaustive comparison of requirements vs existing test class names and test methods

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable -- no moving parts, all dependencies pinned)
