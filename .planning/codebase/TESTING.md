# Testing Patterns

**Analysis Date:** 2026-03-08

## Test Framework

**Runner:**
- No unit test framework configured (no pytest, unittest, nose)
- No test runner, no test config files
- Testing is done via integration/acceptance testing only

**Assertion Library:**
- None (no unit tests exist)

**Run Commands:**
```bash
# Integration/stress test against running server (requires server running)
./stress_test.sh [host:port]              # default: 192.168.1.65:9100

# Manual hardware test
./print.sh test                           # prints test page to real printer
./print.sh test --dummy                   # dry run without printer

# Manual preview (saves image files instead of printing)
./print.sh image photo.jpg --dummy        # saves preview_<mode>.png
./print.sh md "# Hello" --dummy           # prints to dummy (no image preview for md)
```

## Test File Organization

**Location:**
- `stress_test.sh` — single bash script at project root
- No `tests/` directory
- No `*_test.py` or `test_*.py` files
- No co-located test files

**Structure:**
```
POS/
  stress_test.sh       # Integration/acceptance test suite (bash)
  # No unit test files exist
```

## Stress Test Structure

**Suite organization in `stress_test.sh`:**
```bash
# Helper: check HTTP status code against expected
check() {
    local desc="$1" expected_code="$2" actual_code="$3" body="$4"
    # Prints [PASS] or [FAIL] with description
}

# Helper: run a curl request and check result
run() {
    local desc="$1" expected="$2" method="$3" path="$4" content_type="$5" data="$6"
    # Executes curl, passes to check()
}
```

**Test sections (10 categories, 41 total checks):**

1. **Basic Endpoints** (3 tests) — health check, web UI, 404
2. **Valid Print Jobs** (7 tests) — message, label, list, receipt, dictionary, markdown
3. **Malformed Input** (9 tests) — missing fields, empty bodies, invalid JSON
4. **Edge Cases** (5 tests) — long messages (5000 chars), unicode, special chars, code blocks, newlines
5. **Portrait Endpoints** (2 tests) — expect 501 when numpy not installed
6. **Wrong HTTP Methods** (2 tests) — GET on POST-only endpoints
7. **Rapid Fire** (10 tests) — 10 sequential requests in quick succession
8. **Large Payloads** (2 tests) — 100-row list, 50-section markdown
9. **Concurrent Requests** (5 parallel) — 5 simultaneous curl requests (not counted in pass/fail)
10. **Post-Stress Health Check** (1 test) — server still alive after all tests

**Test patterns:**
```bash
# Happy path — expect 200
run "Print message" 200 POST "/print/message" "application/json" \
    '{"text":"Stress test message","title":"TEST"}'

# Error case — expect 500 for missing required field
run "Message: missing text field" 500 POST "/print/message" "application/json" \
    '{"title":"no text"}'

# Edge case — expect 200 for valid but extreme input
run "Very long message" 200 POST "/print/message" "application/json" \
    "{\"text\":\"$(python3 -c "print('A'*5000)")\"}"

# Wrong method — expect 405
run "GET on POST endpoint" 405 GET "/print/message"
```

## Dummy Mode (Hardware Abstraction)

**Pattern:**
- Every CLI command and the server accept `--dummy` flag
- `connect()` in `printer_core.py` returns `escpos.printer.Dummy()` instead of real USB/Network printer
- Dummy printer accepts all ESC/POS commands but produces no output
- Image commands save preview files to disk in dummy mode:
```python
if args.dummy:
    out = args.path.rsplit(".", 1)[0] + f"_preview_{args.mode or 'halftone'}.png"
    img.save(out)
    print(f"[DUMMY] Preview saved to {out}")
```

**What to test without hardware:**
- All rendering logic (markdown to image, dictionary to image, dithering)
- All template layouts via dummy printer
- Server endpoint routing and JSON parsing via stress_test.sh against `--dummy` server

**What requires hardware:**
- Actual print quality, paper alignment, cut position
- USB reconnection behavior
- Thread lock contention under real print durations

## Mocking

**Framework:** None configured

**Current approach:**
- No mocking library (no `unittest.mock`, `pytest-mock`, etc.)
- The `Dummy` printer class from `python-escpos` serves as the only test double
- No mocks for external services (OpenRouter API, n8n webhook)
- No test fixtures or factories

## Coverage

**Requirements:** None enforced

**No coverage tool configured** — no `coverage`, `pytest-cov`, or similar

## Test Types

**Unit Tests:**
- Not present. No unit tests exist for any module.

**Integration Tests:**
- `stress_test.sh` is a full integration/acceptance test suite
- Requires a running server instance (real or dummy)
- Tests HTTP request/response cycle end-to-end
- Tests error handling for malformed input
- Tests concurrency and rapid-fire scenarios
- Tests server resilience (health check after stress)

**E2E Tests:**
- The stress test against a real printer + server is effectively an E2E test
- Manual testing via `./print.sh <command> --dummy` for visual inspection of generated images

## What Is NOT Tested

**No automated tests for:**
- `md_renderer.py` — markdown parsing, inline style parsing, text wrapping, image rendering
- `image_printer.py` — dithering algorithms (Floyd-Steinberg, Bayer, halftone)
- `image_slicer.py` — image slicing logic
- `printer_core.py` — `Formatter` class methods, `connect()` logic
- `templates.py` — template layout logic, `_render_dictionary_image()`
- `portrait_pipeline.py` — face detection, zoom crop computation, style transfer
- Config loading and default resolution
- Font fallback logic in `md_renderer.py`
- Edge cases in inline markdown parsing (`_parse_inline`, `_parse_md`)

## Adding Tests (Recommended Approach)

**If adding unit tests to this project:**

1. Install pytest: add `pytest` to `requirements.txt`
2. Create test files co-located or in a `tests/` directory
3. Name files `test_<module>.py`
4. The `Dummy` printer from `python-escpos` is the natural test double for print operations:
```python
from escpos.printer import Dummy
from printer_core import Formatter

def test_formatter_title():
    p = Dummy()
    fmt = Formatter(p, width=48)
    fmt.title("TEST")
    output = p.output  # Dummy stores raw ESC/POS bytes
    assert b"TEST" in output
```

5. For image rendering tests, compare output images pixel-by-pixel or use snapshot testing:
```python
from md_renderer import render_markdown

def test_render_heading():
    img = render_markdown("# Hello", config=None)
    assert img.size[0] == 576  # paper width
    assert img.size[1] > 0
```

6. For markdown parsing (pure logic, no I/O):
```python
from md_renderer import _parse_md, _parse_inline

def test_parse_heading():
    blocks = _parse_md("# Title\n\nBody text")
    assert blocks[0]["type"] == "h1"
    assert blocks[0]["text"] == "Title"

def test_parse_bold_inline():
    segments = _parse_inline("Hello **world**")
    assert segments == [("Hello ", "normal"), ("world", "bold")]
```

---

*Testing analysis: 2026-03-08*
