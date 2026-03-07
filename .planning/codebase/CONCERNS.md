# Codebase Concerns

**Analysis Date:** 2026-03-07

## Tech Debt

**Duplicated image-opening / alpha-handling logic:**
- Issue: The same pattern (open image, EXIF transpose, alpha-to-white-background) is copy-pasted in 4 places with slight variations.
- Files: `image_printer.py` (lines 152-159), `image_slicer.py` (lines 10-17), `portrait_pipeline.py` (lines 107-111, 413-418)
- Impact: Bug fixes or format support changes must be applied in all 4 locations. Easy to miss one.
- Fix approach: Extract a shared `open_image(path) -> Image` helper in `image_printer.py` or a new `image_utils.py` and import everywhere.

**Duplicated `_resolve_font_path` function:**
- Issue: Identical function defined in both `templates.py` (line 134) and `md_renderer.py` (line 29).
- Files: `templates.py`, `md_renderer.py`
- Impact: Minor -- both resolve relative font paths the same way, but changes must be synced.
- Fix approach: Move to a shared module (e.g., `printer_core.py` or `utils.py`).

**Duplicated `wrap_text` function:**
- Issue: Word-wrapping logic is reimplemented in `templates.py` (lines 171-186) and `md_renderer.py` (lines 201-216) with near-identical code.
- Files: `templates.py`, `md_renderer.py`
- Impact: Minor duplication. Both versions wrap text to pixel width using the same algorithm.
- Fix approach: Extract into a shared text utility.

**`cmd_slice` duplicates image processing pipeline from `image_printer.py`:**
- Issue: `print_cli.py` `cmd_slice` (lines 126-172) manually reimplements the contrast/brightness/sharpness/blur/dither pipeline instead of calling `process_image()`. It also imports internal functions (`_prepare`, `_apply_blur`, `_dither_floyd`, etc.) that should be private.
- Files: `print_cli.py` (lines 20, 126-172)
- Impact: Adding a new dither mode or changing defaults requires updating both `image_printer.py` and `cmd_slice`. The `_` prefix convention for private functions is violated.
- Fix approach: Refactor `image_printer.py` to expose a `dither_pil_image(img, config, **overrides)` function that takes a PIL Image (not a path), then call it from `cmd_slice`.

**Mutable config dict modified in-place:**
- Issue: `run_pipeline()` in `portrait_pipeline.py` mutates the shared config dict via `config.setdefault("portrait", {})["blur"] = blur` (lines 400-402).
- Files: `portrait_pipeline.py` (lines 399-402)
- Impact: In the HTTP server, `_config` is a module-level global. If `run_pipeline` modifies it, subsequent requests inherit those modifications. This could cause subtle bugs where blur/dither values "stick" between requests.
- Fix approach: Deep-copy the config at the start of `run_pipeline`, or pass blur/dither_mode as explicit parameters to downstream functions instead of injecting them into config.

**Setup script uses `.venv` but `print.sh` expects `venv`:**
- Issue: `setup.sh` creates the virtualenv at `.venv` (line 52), but `print.sh` hardcodes `venv/bin/python` (line 3). CLAUDE.md also documents `venv` as the venv name.
- Files: `setup.sh` (line 52: `VENV="$SCRIPT_DIR/.venv"`), `print.sh` (line 3: `"$DIR/venv/bin/python"`)
- Impact: Running `setup.sh` then `print.sh` fails because the venv paths don't match.
- Fix approach: Standardize on one name. Since `print.sh` and CLAUDE.md use `venv`, change `setup.sh` to use `VENV="$SCRIPT_DIR/venv"`.

## Known Bugs

**`cmd_image` preview filename collision for paths without extension:**
- Symptoms: If the image path has no `.` in the filename, `rsplit(".", 1)` returns the original string and the preview filename becomes malformed.
- Files: `print_cli.py` (line 108)
- Trigger: `python print_cli.py image myimage --dummy` (file named `myimage` with no extension)
- Workaround: Always use files with extensions.

**Server `/print/image` raw ESC/POS bytes bypass Formatter:**
- Symptoms: The `do_print` lambda in `print_server.py` sends raw escape sequences (`fmt.p._raw(b'\x1b\x21\x01')`) to set Font B, bypassing the `Formatter` abstraction.
- Files: `print_server.py` (lines 162-165)
- Trigger: Every image print via HTTP.
- Workaround: Works fine with current hardware, but raw bytes may not reset cleanly after reconnect/retry.

## Security Considerations

**HTTP server has no authentication:**
- Risk: Any device on the network can send print jobs, including arbitrary text, images, or triggering the portrait pipeline (which calls external APIs and costs money).
- Files: `print_server.py` (all routes)
- Current mitigation: None. CORS is fully open (`CORS(app)` with no origin restrictions, line 47).
- Recommendations: Add a shared secret / API key header check for non-GET routes. At minimum, restrict CORS origins. Consider rate limiting to prevent print spam.

**OpenRouter API key passed via HTTP header to n8n:**
- Risk: The API key is forwarded in a custom header (`X-OpenRouter-Key`) to the n8n webhook. If the n8n instance is compromised or the webhook URL is leaked, the API key is exposed.
- Files: `portrait_pipeline.py` (lines 123-125)
- Current mitigation: HTTPS is used for the n8n webhook URL.
- Recommendations: Consider having n8n store its own API key instead of receiving it from the client.

**No input validation on server endpoints:**
- Risk: `request.get_json(force=True)` on all endpoints means any Content-Type is accepted and parsed as JSON. Missing keys cause unhandled `KeyError` exceptions. No size limits on uploaded files.
- Files: `print_server.py` (lines 80, 86, 93, 99, 108, 179)
- Current mitigation: None.
- Recommendations: Validate required fields, set `MAX_CONTENT_LENGTH` on the Flask app, and return 400 errors for malformed input instead of 500s.

**Flask development server used in production:**
- Risk: `app.run()` uses Werkzeug's single-threaded development server. Not suitable for concurrent requests. No TLS.
- Files: `print_server.py` (line 334)
- Current mitigation: Single-printer hardware means concurrency is inherently limited.
- Recommendations: Use gunicorn or waitress if concurrent access is expected. For a single-printer setup, this is acceptable but should be documented.

**`.gitignore` does not cover sensitive files:**
- Risk: `.env`, `*.key`, credentials files, and preview images (beyond the three listed) are not gitignored. The `preview_acidic.png`, `preview_floyd.png`, etc. are currently untracked.
- Files: `.gitignore`
- Current mitigation: No `.env` file exists currently.
- Recommendations: Add `.env*`, `*.key`, `portrait_*.png`, `preview_*.png` to `.gitignore`.

## Performance Bottlenecks

**Halftone dithering uses pure Python pixel loops:**
- Problem: `_dither_halftone` iterates over every cell with nested Python for-loops and per-pixel access via `pixels[x, y]`. For a 576px-wide image scaled to paper width, this is slow on Raspberry Pi.
- Files: `image_printer.py` (lines 58-93)
- Cause: No NumPy vectorization; raw PIL pixel access in Python.
- Improvement path: Convert to NumPy array, use `reshape` + `mean` over cells, then draw circles with vectorized coordinates. Or use PIL's built-in quantize/dither.

**Bayer dithering uses pure Python pixel loops:**
- Problem: Same issue as halftone -- `_dither_bayer` iterates pixel-by-pixel in Python.
- Files: `image_printer.py` (lines 106-120)
- Cause: Per-pixel threshold comparison in Python loops.
- Improvement path: Convert to NumPy, create a tiled threshold matrix, and do a single vectorized comparison (`dst = (src_array > threshold_array).astype(np.uint8) * 255`).

**mediapipe imported inside function on every call:**
- Problem: `detect_face_landmarks()` does `import mediapipe as mp` inside the function body. mediapipe is a heavy import (~1-2s).
- Files: `portrait_pipeline.py` (line 160)
- Cause: Lazy import to avoid requiring mediapipe for non-portrait users.
- Improvement path: Import at module level with a try/except, or cache the import. The lazy import is a reasonable trade-off if portrait is rarely used.

## Fragile Areas

**Server global state (`_printer`, `_config`):**
- Files: `print_server.py` (lines 49-53, 62-67)
- Why fragile: Module-level mutable globals (`_printer`, `_config`) are shared across all request handlers. The `with_retry` mechanism (line 70) replaces `_printer` on failure via `reconnect()`, but if two requests fail simultaneously, the reconnect could race.
- Safe modification: Always use `get_formatter()` to access the printer. Do not cache `_printer` in closures.
- Test coverage: None.

**Raw ESC/POS byte sequences:**
- Files: `print_server.py` (lines 162-165)
- Why fragile: Hardcoded escape bytes (`\x1b\x21\x01`, `\x1d\x21\x00`) depend on the specific printer model's ESC/POS dialect. Changing printers may require updating these bytes.
- Safe modification: Move to named constants or add to `Formatter` class (e.g., `fmt.font_b()`).
- Test coverage: None.

**`config.yaml` font paths are platform-specific:**
- Files: `config.yaml` (lines 57-66)
- Why fragile: The `helvetica` style references `/System/Library/Fonts/HelveticaNeue.ttc` which only exists on macOS. Running this style on Raspberry Pi (Linux) crashes with a font-not-found error.
- Safe modification: Add a try/except around font loading with a fallback to bundled fonts, or detect the platform.
- Test coverage: None.

**Markdown renderer two-pass rendering with tuple-based ops:**
- Files: `md_renderer.py` (lines 258-378)
- Why fragile: The rendering pipeline builds a list of tuples (`ops`) with positional fields (e.g., `op[0]` is y, `op[1]` is kind, `op[2]` is text/row/None). Adding a new block type or field requires carefully matching tuple indices. No type safety.
- Safe modification: Convert ops to dataclasses or named tuples.
- Test coverage: None.

## Dependencies at Risk

**`python-escpos` version 3.1:**
- Risk: The `python-escpos` library has had breaking API changes between major versions. The codebase uses internal methods (`p._raw()`) that are not part of the public API.
- Impact: Upgrading `python-escpos` could break raw byte sending and image printing.
- Migration plan: Pin to `==3.1` (already done in `requirements.txt`). Audit `_raw()` calls if upgrading.

**`mediapipe` not in `requirements.txt`:**
- Risk: `portrait_pipeline.py` imports `mediapipe` and `numpy` at runtime, but neither appears in `requirements.txt`. The portrait pipeline silently fails on a fresh install.
- Impact: `python print_cli.py portrait` crashes with `ModuleNotFoundError`.
- Migration plan: Add `mediapipe` and `numpy` to `requirements.txt`, or document them as optional dependencies for the portrait feature.

## Missing Critical Features

**No automated tests:**
- Problem: Zero test files exist. No test framework configured. No CI pipeline.
- Blocks: Confident refactoring, regression detection, and contribution by others.

**No request logging or audit trail:**
- Problem: Print jobs are not logged. No way to review what was printed, when, or by whom.
- Files: `print_server.py`
- Blocks: Debugging print failures, usage tracking, and accountability.

**No graceful error responses from server:**
- Problem: Unhandled exceptions in print handlers return Flask's default 500 HTML error page, not JSON. The `with_retry` function silently swallows the first exception and only raises if the retry also fails.
- Files: `print_server.py` (lines 70-75)
- Blocks: Clients cannot distinguish between printer errors, validation errors, and server bugs.

## Test Coverage Gaps

**All code is untested:**
- What's not tested: Every module -- `printer_core.py`, `templates.py`, `md_renderer.py`, `image_printer.py`, `image_slicer.py`, `portrait_pipeline.py`, `print_cli.py`, `print_server.py`
- Files: All `.py` files
- Risk: Any change could introduce regressions in formatting, layout calculations, image processing, or printer communication without detection.
- Priority: High. Start with unit tests for `md_renderer.py` (pure function, testable with image comparison) and `image_printer.py` (dithering output can be snapshot-tested). The `--dummy` mode provides a natural seam for integration tests.

---

*Concerns audit: 2026-03-07*
