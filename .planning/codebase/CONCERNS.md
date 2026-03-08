# Codebase Concerns

**Analysis Date:** 2026-03-08

## Tech Debt

**No Input Validation on Server Endpoints:**
- Issue: Most server endpoints access `request.get_json(force=True)` and immediately index into the result dict without checking for required keys. Missing keys produce unhelpful 500 errors with Python tracebacks in the JSON error response.
- Files: `print_server.py` (lines 101-132, all `@app.route` handlers)
- Impact: `/print/message` crashes with `KeyError: 'text'` if the key is missing. Same for `/print/label` (`data["heading"]`), `/print/list` (`data["rows"]`, `data["title"]`), `/print/dictionary` (`data` passed to template which expects `data["word"]`), `/print/markdown` (`data["text"]`).
- Fix approach: Add a validation helper that checks required keys and returns a 400 with a clear message. Example: `validate_keys(data, ["text"])` before calling templates.

**Duplicated Image-Open/Alpha-Strip Logic:**
- Issue: The same EXIF-transpose + alpha-channel-removal pattern is copy-pasted in four places with slight variations.
- Files: `image_printer.py` (lines 153-159), `image_slicer.py` (lines 10-17), `portrait_pipeline.py` (lines 107-111, 413-418)
- Impact: Bug fixes or enhancements (e.g., handling new image modes) must be applied in all four places independently.
- Fix approach: Extract a shared `open_image(path) -> Image.Image` function into a utility module or `image_printer.py`, then reuse it everywhere.

**Duplicated `_resolve_font_path` Function:**
- Issue: Identical function defined in both `templates.py` (line 134) and `md_renderer.py` (line 29).
- Files: `templates.py`, `md_renderer.py`
- Impact: Minor — any change to font resolution logic must be made in two places.
- Fix approach: Move to a shared module (e.g., `font_utils.py`) or import from one canonical location.

**Duplicated `wrap_text` Function:**
- Issue: Nearly identical word-wrapping implementations exist in `templates.py` (`_render_dictionary_image`, line 171) and `md_renderer.py` (`render_markdown`, line 225).
- Files: `templates.py` (lines 171-186), `md_renderer.py` (lines 225-240)
- Impact: Same as above — divergent bug fixes.
- Fix approach: Extract into a shared text utility.

**Config Mutation in `run_pipeline`:**
- Issue: `run_pipeline()` mutates the shared `config` dict via `config.setdefault("portrait", {})["blur"] = blur`. In the server, `_config` is a module-level global, so one request's blur/mode overrides persist for subsequent requests.
- Files: `portrait_pipeline.py` (lines 399-402)
- Impact: If a user sends a portrait request with `blur=20`, all subsequent portrait requests without explicit blur will use 20 instead of the config default (10). This is a subtle stateful bug.
- Fix approach: Deep-copy the config before mutation, or pass blur/mode as explicit function parameters rather than modifying config.

**Raw ESC/POS Commands in Server Code:**
- Issue: The `/print/image` endpoint contains raw escape sequences (`b'\x1b\x21\x01'`, `b'\x1d\x21\x00'`) instead of using the `Formatter` abstraction.
- Files: `print_server.py` (lines 183-186)
- Impact: Bypasses the Formatter layer, making the code harder to understand and maintain. If printer model changes, these raw bytes may need updating.
- Fix approach: Add a `small_text()` or equivalent method to `Formatter` in `printer_core.py` and use it here.

**Flask Dev Server in Production:**
- Issue: The server runs Flask's built-in development server (`app.run()`) which is single-threaded and not designed for production use.
- Files: `print_server.py` (line 367)
- Impact: Acceptable for a single-printer setup, but any concurrent requests block. The `_print_lock` provides thread safety, but Flask dev server is single-threaded anyway, so the lock only helps if `threaded=True` were enabled or a WSGI server used.
- Fix approach: For current use case (single printer, low traffic), this is acceptable. If scaling is needed, switch to gunicorn with `--workers 1 --threads 4`.

## Security Considerations

**No Authentication on HTTP Endpoints:**
- Risk: Anyone on the same network can send print jobs, potentially wasting paper or printing offensive content. The portrait endpoint also proxies API keys to external services.
- Files: `print_server.py` (all endpoints)
- Current mitigation: None. Server binds to `0.0.0.0` by default.
- Recommendations: Add a simple API key check via a header (e.g., `X-Print-Key`) or restrict to specific IPs. At minimum, document this as a known risk for shared networks. The mDNS broadcast (`register_mdns` at line 313) actively advertises the service to the entire network.

**API Key Forwarded via n8n Webhook:**
- Risk: The OpenRouter API key is sent as a header (`X-OpenRouter-Key`) to the n8n webhook URL configured in `config.yaml`. If the webhook URL is changed to a malicious endpoint, the API key is leaked.
- Files: `portrait_pipeline.py` (lines 120-128)
- Current mitigation: Webhook URL is in `config.yaml` which is version-controlled.
- Recommendations: Validate the webhook URL domain before sending the key, or let the n8n workflow use its own stored key.

**`force=True` on `get_json` Bypasses Content-Type Check:**
- Risk: `request.get_json(force=True)` parses the body as JSON regardless of Content-Type header. This is intentional for flexibility but means any POST with a JSON-like body will be processed.
- Files: `print_server.py` (lines 101, 107, 115, 122, 129, 201)
- Current mitigation: The global error handler returns JSON errors.
- Recommendations: Minor concern. Could enforce `Content-Type: application/json` for stricter API behavior.

**Temp File Handling:**
- Risk: Temp files in `/print/image` and `/portrait/*` endpoints are created with `delete=False` and manually cleaned up in `finally` blocks. If the process is killed between creation and cleanup, files persist.
- Files: `print_server.py` (lines 156, 227, 277)
- Current mitigation: `finally` blocks handle normal error cases.
- Recommendations: Acceptable risk for a low-traffic print server. OS `/tmp` cleanup handles stragglers.

## Performance Bottlenecks

**Halftone Dithering is Pure Python Pixel Loop:**
- Problem: `_dither_halftone()` iterates every pixel in nested Python loops to compute cell averages and draw circles.
- Files: `image_printer.py` (lines 58-94)
- Cause: No NumPy acceleration. For a 576px-wide image at ~800px tall, this processes ~460,000 pixels in pure Python.
- Improvement path: Use NumPy for cell-average computation (`reshape` + `mean`) and vectorized circle drawing, or pre-compute a lookup table. Alternatively, accept that thermal printing is slow enough that this doesn't matter in practice.

**Bayer Dithering is Pure Python Pixel Loop:**
- Problem: `_dither_bayer()` iterates every pixel individually.
- Files: `image_printer.py` (lines 106-120)
- Cause: Same as halftone — no vectorization.
- Improvement path: NumPy threshold matrix comparison can process the entire image in one operation.

**Markdown Rendering Two-Pass Architecture:**
- Problem: `render_markdown()` does a full layout pass to measure height, then a draw pass. For large documents (e.g., 50 sections), this processes all text twice.
- Files: `md_renderer.py` (lines 189-403)
- Cause: PIL images require known dimensions at creation time.
- Improvement path: Allocate an oversized canvas and crop after drawing, eliminating the measurement pass. Or accept the current approach since thermal prints are small.

## Fragile Areas

**Formatter State Leaks:**
- Files: `printer_core.py` (lines 30-160)
- Why fragile: Every `Formatter` method sets printer state (alignment, bold, font) and resets it at the end. If an exception occurs between `set()` and the reset, the printer state is left dirty for subsequent calls. No context manager or try/finally guards.
- Safe modification: Always reset state in a `finally` block, or use a context manager pattern.
- Test coverage: No unit tests. Only stress_test.sh exercises the server end-to-end.

**`left_right` Assumes ASCII-Width Characters:**
- Files: `printer_core.py` (lines 103-108)
- Why fragile: Uses `len(left)` and `len(right)` to calculate spacing, which counts characters not display width. CJK characters (2 display columns each), emojis, and accented characters will misalign.
- Safe modification: Use `unicodedata.east_asian_width()` for proper column-width calculation.
- Test coverage: None.

**Inline Markdown Regex:**
- Files: `md_renderer.py` (lines 125-130)
- Why fragile: The regex `_INLINE_RE` processes bold (`**`), italic (`*`), strikethrough (`~~`), and code (`` ` ``) patterns. Nested patterns (e.g., `**bold *italic***`) or patterns spanning multiple words with special characters can produce unexpected matches. The italic pattern `\*(.+?)\*` can match inside `**bold**` in edge cases.
- Safe modification: Test with complex nested markdown before changing the regex. The current ordering (bold before italic) mitigates the most common case.
- Test coverage: No unit tests for the parser.

**Portrait Pipeline External Dependencies:**
- Files: `portrait_pipeline.py` (lines 63-83, 120-145)
- Why fragile: Depends on OpenRouter API (for photo selection) and n8n webhook (for style transfer). If either service changes its API, is down, or rate-limits, the pipeline fails with unhelpful errors.
- Safe modification: The `requests.post()` calls have timeouts (60s, 180s) which is good. Add retry logic and better error messages for common failure modes (401, 429, 503).
- Test coverage: No tests. Cannot be tested without live API keys.

## Dependencies at Risk

**python-escpos 3.1:**
- Risk: The `python-escpos` library's API (`.set()`, `.text()`, `.image()`, `._raw()`) is used extensively. The `._raw()` call is a private API that could change in future versions.
- Impact: Formatter, templates, and server all break if the API changes.
- Migration plan: Pin the version (already done in `requirements.txt`). Wrap `._raw()` calls in a Formatter method to isolate the private API usage.

**mediapipe (Optional):**
- Risk: Large dependency (~30MB+), only used by portrait pipeline. Google occasionally deprecates mediapipe versions. Not listed in `requirements.txt` (intentionally optional).
- Impact: Portrait pipeline unavailable without it. Server handles this gracefully via lazy import.
- Migration plan: Current optional approach is correct. Could document alternative face detection libraries.

## Missing Critical Features

**No Request Size Limits:**
- Problem: The Flask server has no limit on upload size. A malicious client could upload a multi-GB image to `/print/image` or `/portrait/capture` and exhaust memory.
- Files: `print_server.py`
- Blocks: Nothing currently, but makes the server vulnerable to memory exhaustion attacks on the Pi (400MB systemd limit helps but doesn't prevent OOM).

**No Rate Limiting:**
- Problem: Any client can send unlimited requests, exhausting paper and printer resources.
- Files: `print_server.py`
- Blocks: Practical deployment on shared/public networks.

**No Graceful Shutdown:**
- Problem: The Zeroconf cleanup is registered via `atexit` (line 336), but Flask's dev server may not trigger atexit handlers on all signal types. The printer connection is never explicitly closed on shutdown.
- Files: `print_server.py` (lines 331-338)
- Blocks: Clean service restarts may leave stale mDNS registrations.

## Test Coverage Gaps

**No Unit Tests:**
- What's not tested: All Python modules — `printer_core.py`, `templates.py`, `md_renderer.py`, `image_printer.py`, `image_slicer.py`, `portrait_pipeline.py`
- Files: All `.py` files
- Risk: Refactoring any module (especially the markdown parser or image processing pipeline) could silently break functionality. The only safety net is `stress_test.sh` which is an integration test requiring a running server.
- Priority: High for `md_renderer.py` (complex parsing logic) and `image_printer.py` (pixel-level algorithms). Medium for `templates.py` and `printer_core.py`.

**Markdown Parser Edge Cases:**
- What's not tested: Nested inline styles, escaped special characters, multi-line paragraphs, ordered lists (not supported but not documented as unsupported), code blocks (fenced ```) are parsed as paragraphs not code, empty headings, headings with inline formatting.
- Files: `md_renderer.py` (lines 158-186, `_parse_md`)
- Risk: Users submitting markdown via the web UI or API may get unexpected rendering. The stress test sends a code block but doesn't verify visual output.
- Priority: Medium.

**`--dummy` Mode Does Not Verify Output:**
- What's not tested: The `Dummy` printer from `python-escpos` captures ESC/POS commands but nothing in the codebase inspects the captured output. Dummy mode is used only to avoid hardware errors, not to verify correctness.
- Files: `printer_core.py` (line 20), all CLI commands
- Risk: Tests pass in dummy mode but actual print output could be malformed.
- Priority: Low — visual inspection of thermal prints is the practical QA method for this project.

**Image Processing Correctness:**
- What's not tested: Dithering algorithms produce correct output for known inputs. No golden-image comparison tests.
- Files: `image_printer.py` (all dithering functions)
- Risk: Changes to contrast/brightness/sharpness defaults or dithering logic could degrade print quality without detection.
- Priority: Low — output quality is subjective and best judged visually.

---

*Concerns audit: 2026-03-08*
