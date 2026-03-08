# Phase 2: Server Hardening - Research

**Researched:** 2026-03-08
**Domain:** Flask request validation, ESC/POS printer state management, signal handling, error consistency
**Confidence:** HIGH

## Summary

Phase 2 hardens the HTTP print server against bad input, dirty printer state, and unclean shutdown. The work decomposes into four distinct concerns: (1) input validation on all JSON endpoints so missing fields return 400 with structured error JSON instead of 500 tracebacks, (2) request size limiting via Flask's built-in `MAX_CONTENT_LENGTH` to prevent OOM kills on the Pi, (3) Formatter state safety via try/finally guards and ESC@ initialization at the start of every print job, and (4) graceful SIGTERM handling to deregister mDNS and close the USB printer connection before exit.

All four concerns have well-documented solutions using existing Flask/Python features -- no new dependencies are needed. The Formatter state guards and ESC@ initialization are the most impactful changes: without them, a single mid-print exception permanently wedges the printer's text style until a power cycle. The SIGTERM handler replaces the current unreliable `atexit` approach that Flask's dev server may not trigger.

There are also two code quality requirements: moving raw ESC/POS byte commands from `print_server.py` into a proper Formatter method (QUAL-04), and fixing a config mutation bug in `portrait_pipeline.py` where `run_pipeline()` modifies the shared `_config` dict in place (QUAL-05).

**Primary recommendation:** Handle these in order: (1) Formatter hardening + ESC@ init in `printer_core.py` / `with_retry`, (2) input validation + MAX_CONTENT_LENGTH + error consistency in `print_server.py`, (3) SIGTERM handler + portrait config fix. Each is independently testable with `--dummy` mode.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REL-01 | Server returns 400 with clear error message when required JSON fields are missing | All 6 JSON endpoints use `data["key"]` with no validation; `get_json(force=True)` returns `None` on invalid JSON which causes `TypeError`. Hand-rolled validation functions per endpoint, checked before `with_retry()`. |
| REL-02 | Server rejects requests over 10MB with 413 status before processing | Flask 3.1.2 / Werkzeug 3.1.3 `MAX_CONTENT_LENGTH` is enforced at the input stream level, including for `get_json(force=True)`. One line: `app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024`. Returns `RequestEntityTooLarge` (413) automatically. |
| REL-03 | Formatter methods use try/finally guards so printer state is always reset after each operation | 9 Formatter methods change printer state (title, subtitle, center, bold, italic_text, small, right, left_right_bold, qr, barcode). None have try/finally. Add guards to all that call `self.p.set()` with non-default values. |
| REL-04 | Printer receives ESC@ initialize command at the start of every print job | python-escpos provides `printer.hw("INIT")` which sends `HW_INIT` = `b"\x1b\x40"` (ESC @). Call this in `with_retry()` at the top of every print job, before calling the template function. Also call after reconnect. |
| REL-05 | Server handles SIGTERM gracefully -- deregisters mDNS, closes printer connection, then exits | Current cleanup uses `atexit` which Flask's dev server may not trigger on SIGTERM. Replace with `signal.signal(signal.SIGTERM, handler)` in `main()` that calls `_printer.close()`, `_zeroconf.unregister_all_services()`, `_zeroconf.close()`, then `sys.exit(0)`. |
| QUAL-04 | Raw ESC/POS commands in print_server.py moved into Formatter methods | Lines 183-186 in `print_server.py` use `fmt.p._raw()` to set Font B. Move into a `Formatter.font_b_text()` method that wraps the `self.p.set(font="b")` / `self.p.set(font="a")` pattern (which is already what `small()` does, but also sets the GS ! size command). |
| QUAL-05 | Portrait pipeline config mutation bug fixed -- no shared state leak between requests | `portrait_pipeline.py` lines 395-398: `config.setdefault("portrait", {})["blur"] = blur` mutates the shared `_config` dict. Fix by passing blur/dither_mode as explicit parameters through the call chain instead of modifying config, or deep-copy config before passing to `run_pipeline()`. |
| QUAL-06 | All server error responses use consistent structured JSON format: `{"error": "message", "field": "name"}` | Current error handler at line 305-310 returns `{"error": str(e)}` which varies in format. Validation errors need `{"error": "message", "field": "field_name"}`. Standardize the global error handler and all 400 responses. |
</phase_requirements>

## Standard Stack

### Core

No new libraries needed. Phase 2 uses only what is already installed.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | 3.1.2 | `MAX_CONTENT_LENGTH`, error handlers, `request.get_json()` | Already installed |
| Werkzeug | 3.1.3 | `RequestEntityTooLarge` (413) enforcement at input stream level | Ships with Flask |
| python-escpos | 3.1 | `printer.hw("INIT")` for ESC@ reset, `Dummy` for testing | Already installed |
| zeroconf | 0.146.0 | `_zeroconf.unregister_all_services()` for graceful shutdown | Already installed |
| Python stdlib `signal` | -- | `signal.signal(signal.SIGTERM, handler)` for graceful shutdown | No install needed |
| Python stdlib `copy` | -- | `copy.deepcopy()` for config mutation fix | No install needed |

### Supporting

None. Phase 2 introduces zero new dependencies.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled validation | pydantic, marshmallow, cerberus | Overkill for ~6 fields per endpoint. Pydantic v2 pulls in pydantic-core (Rust compiled), heavy on Pi 3. Locked decision from roadmap. |
| `try/finally` in each method | Context managers (`with fmt.state(bold=True):`) | Context managers are cleaner but require changing every template call site. try/finally inside Formatter methods is invisible to callers -- zero migration cost. |
| `atexit` cleanup | `signal.signal(SIGTERM)` | `atexit` does not fire reliably on SIGTERM from systemd. Signal handler is the correct approach for daemon processes. |

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Files Modified

```
POS/
  printer_core.py       # MODIFIED: try/finally guards on Formatter methods, font_b_text(), initialize()
  print_server.py       # MODIFIED: validation, MAX_CONTENT_LENGTH, SIGTERM handler, error format, ESC@ in with_retry
  portrait_pipeline.py  # MODIFIED: remove config mutation in run_pipeline()
```

No new files are created in this phase. The validation logic is simple enough to live inline in `print_server.py` (or as helper functions at the top of the file). A separate `validators.py` module is more appropriate for Phase 3 when auth decorators are added -- for now, keep the validation functions in `print_server.py` to minimize file churn.

### Pattern 1: Input Validation Before Print Lock

**What:** Validate request data BEFORE acquiring `_print_lock`. Bad requests should never touch the printer.

**When to use:** Every JSON POST endpoint.

**Example:**
```python
# In print_server.py -- validation helper
def _require_fields(data, *fields):
    """Check that data is a dict and contains all required fields.
    Returns (data, None) on success or (None, (error_msg, field_name)) on failure."""
    if data is None:
        return None, ("Invalid or missing JSON body", None)
    if not isinstance(data, dict):
        return None, ("Request body must be a JSON object", None)
    for field in fields:
        if field not in data:
            return None, (f"Missing required field '{field}'", field)
    return data, None

# In an endpoint:
@app.route("/print/message", methods=["POST"])
def print_message():
    data = request.get_json(force=True, silent=True)
    data, err = _require_fields(data, "text")
    if err:
        return jsonify({"error": err[0], "field": err[1]}), 400
    with_retry(lambda fmt: templates.simple_message(fmt, data["text"], data.get("title")))
    return jsonify({"status": "ok", "template": "message"})
```

**Key detail:** Use `get_json(force=True, silent=True)` instead of `get_json(force=True)`. The `silent=True` parameter makes `get_json` return `None` on parse failure instead of raising a `BadRequest` exception. This lets the validation function handle it with a consistent error format.

**Confidence:** HIGH -- standard Flask validation pattern.

### Pattern 2: ESC@ Initialize in with_retry

**What:** Send the ESC@ (hardware initialize) command at the start of every print job. This resets the printer's internal state machine to defaults (left-aligned, Font A, normal size, no bold/underline).

**When to use:** Every print job, before calling the template function.

**Example:**
```python
# In print_server.py
def with_retry(fn):
    """Run a print function with mutex lock, ESC@ init, and reconnect on failure."""
    with _print_lock:
        try:
            fmt = get_formatter()
            fmt.p.hw("INIT")  # ESC@ -- reset printer state to defaults
            fn(fmt)
        except Exception as e:
            logger.warning("Print failed (%s), reconnecting...", e)
            try:
                fmt = reconnect()
                fmt.p.hw("INIT")  # ESC@ after reconnect too
                fn(fmt)
            except Exception as e2:
                logger.error("Retry also failed: %s", e2)
                raise
```

**Why this matters:** The printer's state machine is independent of the USB connection. Reconnecting does NOT reset printer state. Only ESC@ (`\x1b\x40`) or a power cycle resets it. Without this, a mid-print exception that leaves bold/center/double-size active will affect ALL subsequent prints.

**Confidence:** HIGH -- `printer.hw("INIT")` confirmed in python-escpos source at `escpos/escpos.py:1183`, sends `HW_INIT = b"\x1b\x40"` from `escpos/constants.py:42`.

### Pattern 3: try/finally Guards on Formatter State Changes

**What:** Wrap the set-do-reset pattern in try/finally so the reset always executes.

**When to use:** Every Formatter method that calls `self.p.set()` with non-default values.

**Example:**
```python
def title(self, text):
    """Large centered bold text."""
    self.p.set(align="center", bold=True, double_height=True, double_width=True)
    try:
        self.p.text(f"{text}\n")
    finally:
        self.p.set(align="left", bold=False, double_height=False, double_width=False)
```

**Methods that need guards (9 total):**

| Method | State Changed | Reset To |
|--------|--------------|----------|
| `title()` | align=center, bold, double_height, double_width | align=left, bold=False, double_height=False, double_width=False |
| `subtitle()` | align=center, bold | align=left, bold=False |
| `center()` | align=center | align=left |
| `bold()` | bold=True | bold=False |
| `italic_text()` | underline=1 | underline=0 |
| `small()` | font=b | font=a |
| `right()` | align=right | align=left |
| `left_right_bold()` | bold=True | bold=False |
| `qr()` | align=center | align=left |
| `barcode()` | align=center | align=left |

**Methods that do NOT need guards:** `text()`, `wrap()`, `line()`, `double_line()`, `blank()`, `left_right()`, `columns()`, `cut()`, `feed()` -- these either don't change state or set-to-defaults first.

**Note:** The `text()` method calls `self.p.set(align="left", bold=False)` before printing. This is a reset-to-defaults, not a state change. No guard needed -- if this fails, the state is already default.

**Confidence:** HIGH -- directly observed: all 10 methods follow set-do-reset without try/finally.

### Pattern 4: Formatter.font_b_text() Method (QUAL-04)

**What:** Replace raw ESC/POS byte commands in `print_server.py` with a proper Formatter method.

**Current code in `print_server.py:183-186`:**
```python
fmt.p._raw(b'\x1b\x21\x01')  # ESC ! 0x01: Font B
fmt.p._raw(b'\x1d\x21\x00')  # GS ! 0x00: 1x width, 1x height
fmt.p.text(label + '\n')
fmt.p._raw(b'\x1b\x21\x00')  # reset to Font A normal
```

**New Formatter method:**
```python
def font_b_text(self, text):
    """Print text in smaller Font B with normal size, then reset to Font A."""
    self.p.set(font="b", normal_textsize=True)
    try:
        self.p.text(f"{text}\n")
    finally:
        self.p.set(font="a")
```

**Why `set(font="b", normal_textsize=True)` instead of raw bytes:** The raw commands `ESC ! 0x01` (Font B) and `GS ! 0x00` (normal size) are exactly what python-escpos `set()` sends for `font="b"` and `normal_textsize=True`. Using the public API isolates the Formatter from python-escpos internals.

**Usage in print_server.py:**
```python
# Replace the raw commands with:
fmt.font_b_text(label)
```

**Confidence:** HIGH -- the `small()` method already uses this pattern. The difference is that `font_b_text()` also forces normal text size (the raw GS ! command), which `small()` does not do.

### Pattern 5: SIGTERM Handler (REL-05)

**What:** Register a signal handler for SIGTERM and SIGINT that cleanly shuts down mDNS and USB.

**Example:**
```python
import signal

def graceful_shutdown(signum, frame):
    """Clean up mDNS and printer connection on shutdown signal."""
    logger.info("Received signal %s, shutting down...", signum)
    if _zeroconf:
        try:
            _zeroconf.unregister_all_services()
            _zeroconf.close()
            logger.info("mDNS deregistered")
        except Exception:
            pass
    if _printer:
        try:
            _printer.close()
            logger.info("Printer connection closed")
        except Exception:
            pass
    sys.exit(0)

# In main(), BEFORE app.run():
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)
```

**Key details:**
- Register BEFORE `app.run()` so the handler is active during the Flask server loop.
- Keep the handler minimal -- no long operations, no acquiring locks. systemd sends SIGKILL after `TimeoutStopSec=15`.
- `sys.exit(0)` is important -- it raises `SystemExit` which triggers remaining cleanup.
- Remove the `atexit.register(cleanup)` call in `register_mdns()` since the signal handler now handles cleanup explicitly. Or keep it as a belt-and-suspenders approach for clean interpreter exit.

**Confidence:** MEDIUM -- the signal handler pattern itself is standard Python. The uncertainty is whether Flask/Werkzeug's dev server intercepts SIGTERM before our handler runs. This needs testing on the actual Pi with `systemctl stop pos-printer`. If Flask intercepts it, the fallback is to also keep the `atexit` handler.

### Pattern 6: Portrait Config Mutation Fix (QUAL-05)

**What:** Stop `run_pipeline()` from modifying the shared `_config` dict.

**Current bug at `portrait_pipeline.py:395-398`:**
```python
if blur is not None:
    config.setdefault("portrait", {})["blur"] = blur
if dither_mode is not None:
    config.setdefault("portrait", {})["dither_mode"] = dither_mode
```

**Fix -- option A (recommended): pass as parameters, don't touch config:**
```python
def run_pipeline(image_paths, config, printer, dummy=False, save_dir=None,
                 skip_selection=False, skip_transform=False,
                 blur=None, dither_mode=None):
    # Don't modify config. Pass overrides down explicitly.
    # ...
    print_portrait(image, config, printer, dummy=dummy, save_dir=save_dir,
                   blur_override=blur, dither_mode_override=dither_mode)
```

Then in `print_portrait()`:
```python
def print_portrait(image, config, printer, dummy=False, save_dir=None,
                   blur_override=None, dither_mode_override=None):
    cfg = config.get("portrait", {})
    blur = blur_override if blur_override is not None else cfg.get("blur", 10)
    dither_mode = dither_mode_override if dither_mode_override is not None else cfg.get("dither_mode", "bayer")
    # ...
```

**Fix -- option B (simpler): deep-copy at the call site in print_server.py:**
```python
import copy

@app.route("/portrait/capture", methods=["POST"])
def portrait_capture():
    # ...
    local_config = copy.deepcopy(_config)
    run_pipeline(tmp_paths, local_config, _printer, ...)
```

**Recommendation:** Option A is cleaner (removes the mutation entirely), but Option B is faster to implement (one line at each call site). Either satisfies the requirement.

**Confidence:** HIGH -- mutation directly observed at lines 395-398.

### Pattern 7: Consistent Error Response Format (QUAL-06)

**What:** All error responses must use `{"error": "message", "field": "name"}` format.

**Current state:**
- Global error handler returns `{"error": str(e)}` -- no `field` key
- Some endpoints have ad-hoc validation (image upload checks) with `{"error": "No file uploaded"}` -- no `field` key
- No validation on JSON endpoints at all

**Approach:** Standardize all error responses:

```python
def error_response(message, field=None, status=400):
    """Return a consistent JSON error response."""
    body = {"error": message}
    if field is not None:
        body["field"] = field
    return jsonify(body), status

# Update global error handler:
@app.errorhandler(Exception)
def handle_error(e):
    code = getattr(e, "code", 500)
    logger.error("Request error: %s", e)
    return jsonify({"error": str(e)}), code
```

The `field` key is included when the error is about a specific missing/invalid field. For general errors (413, 500), only `error` is present.

**Confidence:** HIGH -- straightforward formatting change.

### Anti-Patterns to Avoid

- **Creating a separate `validators.py` module for Phase 2:** This phase only needs simple `_require_fields()` checks. A full validators module with decorator patterns is better deferred to Phase 3 when auth decorators justify a standalone module. Adding a module now that gets significantly reworked in Phase 3 is wasted effort.

- **Adding try/finally to `text()` method:** `text()` calls `self.p.set(align="left", bold=False)` which RESETS state to defaults. If this call fails, the state was already dirty from a previous call. Adding try/finally here would try to reset AFTER a failed reset -- pointless and potentially masking the real error.

- **Using `set_with_default()` in try/finally blocks:** python-escpos 3.1 has `set_with_default()` which sends ALL attributes with defaults. Using this in `finally` blocks would send many more bytes than needed. Use the specific `set()` parameters instead.

- **Deep-copying config on every request:** Only the portrait pipeline mutates config. Deep-copying `_config` in every endpoint handler is wasteful. Fix the mutation at the source.

- **Adding validation to `/print/image`, `/portrait/capture`, `/portrait/transform`:** These are multipart file upload endpoints, not JSON. They already have basic file-presence validation. The requirement (REL-01) is about "required JSON fields" -- file upload validation is a different concern and is already handled.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request size limiting | Check `Content-Length` header manually | `app.config["MAX_CONTENT_LENGTH"]` | Flask/Werkzeug enforces at the stream level, handles chunked transfers, returns proper 413. One line of config vs. a fragile middleware. |
| Printer state reset | Send raw `b"\x1b\x40"` bytes | `printer.hw("INIT")` | python-escpos wraps this properly. Using the public API survives library updates. |
| JSON error responses | Custom exception classes + middleware | Flask `jsonify()` + global `errorhandler` | Already exists in the codebase. Just standardize the format. |
| Signal handling | Custom daemon framework | Python `signal.signal()` | stdlib solution, 5 lines. |

**Key insight:** Every requirement in this phase has a direct, well-known solution. The risk is not "how do we do this" but "do we do it completely" (missing a Formatter method, missing an endpoint, etc.).

## Common Pitfalls

### Pitfall 1: ESC@ Wipes In-Progress Print State

**What goes wrong:** Sending ESC@ (`hw("INIT")`) at the wrong time (e.g., mid-template) wipes all printer state including partial output in the print buffer. Text already sent but not yet printed could be lost.
**Why it happens:** ESC@ is a full hardware reset -- it clears the print buffer AND resets all text formatting.
**How to avoid:** Send ESC@ ONLY at the START of `with_retry()`, before calling the template function. Never inside a template.
**Warning signs:** First line of a print is missing or printed in default style while the rest is formatted.

### Pitfall 2: Missing Endpoint Validation

**What goes wrong:** Adding validation to 5 of 6 endpoints but missing one. The missed endpoint still returns 500 on bad input.
**Why it happens:** Mechanical error -- there are 6 JSON endpoints and 3 file upload endpoints.
**How to avoid:** Systematic audit. The 6 JSON endpoints that need validation are:
1. `/print/receipt` -- needs `items` (list)
2. `/print/message` -- needs `text` (string)
3. `/print/label` -- needs `heading` (string)
4. `/print/list` -- needs `title` (string), `rows` (list)
5. `/print/dictionary` -- needs `word` (string), `definition` (string)
6. `/print/markdown` -- needs `text` (string)
**Warning signs:** Send `curl -X POST <url> -d '{}'` to each endpoint. Any that returns 500 instead of 400 is missing validation.

### Pitfall 3: try/finally on Formatter.left_right_bold Calls left_right

**What goes wrong:** `left_right_bold()` sets bold, calls `left_right()`, then resets bold. But `left_right()` is another Formatter method. If `left_right()` itself throws, the `bold=False` reset in `left_right_bold` must still fire.
**Why it happens:** Nested Formatter calls create nested state management.
**How to avoid:** The try/finally in `left_right_bold()` wraps the ENTIRE body including the `left_right()` call:
```python
def left_right_bold(self, left, right):
    self.p.set(bold=True)
    try:
        self.left_right(left, right)
    finally:
        self.p.set(bold=False)
```
This is correct because `left_right()` does not change any state -- it just calls `self.p.text()`.
**Warning signs:** Bold text persists after a `left_right_bold()` call that threw an exception.

### Pitfall 4: SIGTERM Handler Deadlocks on Print Lock

**What goes wrong:** The SIGTERM signal arrives while a print job holds `_print_lock`. The signal handler tries to close the printer, which may try to send data through the USB interface that's currently in use by the print job. This can deadlock or cause a USB error.
**Why it happens:** Signal handlers interrupt the current thread. If the main thread holds the lock and the signal handler runs in the same thread, the lock is re-entrant (Python threading locks are NOT re-entrant by default).
**How to avoid:** Do NOT acquire `_print_lock` in the signal handler. Just close the printer and mDNS directly. The ongoing print job will fail, but the process is exiting anyway. USB `close()` is safe to call even during an active transfer -- it will abort the current transfer.
**Warning signs:** Server hangs on `systemctl stop` instead of shutting down cleanly.

### Pitfall 5: get_json(force=True) Returns Non-Dict

**What goes wrong:** A client sends a valid JSON body that is not an object -- e.g., `"hello"`, `[1,2,3]`, or `42`. `get_json(force=True)` successfully parses these, but they're not dicts. Calling `data["text"]` on a string or list produces a confusing `TypeError` or unexpected behavior.
**Why it happens:** JSON allows any value at the top level, not just objects. `force=True` skips Content-Type checking, not schema checking.
**How to avoid:** The `_require_fields()` helper must check `isinstance(data, dict)` before checking for specific fields.
**Warning signs:** `TypeError: string indices must be integers` in error logs.

## Code Examples

### Complete _require_fields() Helper

```python
# Source: hand-rolled for this project's needs
def _require_fields(data, *fields):
    """Validate JSON body has required fields.
    Returns (data, None) on success, or (None, (error_msg, field_name)) on failure.
    """
    if data is None:
        return None, ("Invalid or missing JSON body", None)
    if not isinstance(data, dict):
        return None, ("Request body must be a JSON object", None)
    for field in fields:
        if field not in data:
            return None, (f"Missing required field '{field}'", field)
    return data, None
```

### Complete with_retry() with ESC@ Init

```python
# Source: adapted from current print_server.py with ESC@ addition
def with_retry(fn):
    """Run a print function with mutex lock, ESC@ init, and reconnect on failure."""
    with _print_lock:
        try:
            fmt = get_formatter()
            fmt.p.hw("INIT")  # ESC@ -- reset printer to defaults
            fn(fmt)
        except Exception as e:
            logger.warning("Print failed (%s), reconnecting...", e)
            try:
                fmt = reconnect()
                fmt.p.hw("INIT")
                fn(fmt)
            except Exception as e2:
                logger.error("Retry also failed: %s", e2)
                raise
```

### Complete SIGTERM Handler

```python
import signal

def graceful_shutdown(signum, frame):
    """Clean up mDNS and printer connection on SIGTERM/SIGINT."""
    logger.info("Received signal %s, shutting down...", signum)
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

# In main(), before app.run():
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)
```

### Complete Formatter.title() with try/finally

```python
def title(self, text):
    """Large centered bold text."""
    self.p.set(align="center", bold=True, double_height=True, double_width=True)
    try:
        self.p.text(f"{text}\n")
    finally:
        self.p.set(align="left", bold=False, double_height=False, double_width=False)
```

### Validated Endpoint Example

```python
@app.route("/print/message", methods=["POST"])
def print_message():
    data = request.get_json(force=True, silent=True)
    data, err = _require_fields(data, "text")
    if err:
        return jsonify({"error": err[0], "field": err[1]}), 400
    with_retry(lambda fmt: templates.simple_message(fmt, data["text"], data.get("title")))
    return jsonify({"status": "ok", "template": "message"})
```

### Required Fields Per Endpoint

| Endpoint | Required Fields | Optional Fields |
|----------|----------------|-----------------|
| `/print/receipt` | `items` (list of objects, each with `name` and `price`) | `payment_method`, `receipt_id` |
| `/print/message` | `text` | `title` |
| `/print/label` | `heading` | `lines` |
| `/print/list` | `title`, `rows` | -- |
| `/print/dictionary` | `word`, `definition` | `citations`, `qr_url` |
| `/print/markdown` | `text` | `show_date`, `style` |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `atexit` for daemon cleanup | `signal.signal(SIGTERM)` | Always been the correct way | `atexit` is for interactive scripts, not daemons |
| Flask error handler catch-all | Flask error handler + per-endpoint validation | Standard since Flask 1.0+ | Validation prevents bad input from reaching business logic |
| No request size limits | `MAX_CONTENT_LENGTH` | Available since Flask 0.5 | One-line protection against OOM |
| python-escpos `set()` with selective params | python-escpos 3.1 added `set_with_default()` | python-escpos 3.0 | `set_with_default()` resets ALL attributes; `set()` only changes what you pass |

**Deprecated/outdated:**
- `get_json(force=True)` without `silent=True` raises `BadRequest` on parse failure, which gets caught by the global error handler. Using `silent=True` gives the validation function control over the error format.

## Open Questions

1. **Does Flask's dev server pass SIGTERM to our handler?**
   - What we know: Flask/Werkzeug 3.x uses `threading.Event` for shutdown. The signal handler should fire before Werkzeug's internal handling.
   - What's unclear: Whether Werkzeug intercepts SIGTERM and runs its own shutdown before or after our handler.
   - Recommendation: Implement the signal handler. Test on the Pi with `systemctl stop pos-printer`. If it doesn't fire, add `atexit` as a fallback. The STATE.md already flags this as a known concern.

2. **Should the global error handler include `"field": null` or omit `"field"` for non-field errors?**
   - What we know: The success criteria says format is `{"error": "message", "field": "name"}`.
   - What's unclear: Whether `field` should always be present (with `null` for non-field errors) or only present when relevant.
   - Recommendation: Only include `field` when it's a specific field error. General errors (413, 500) just have `{"error": "message"}`. This is more natural for JSON consumers (`if "field" in response`).

3. **Should `receipt` validation check individual item objects?**
   - What we know: Receipt items need `name` and `price`. Currently no validation.
   - What's unclear: Whether to do deep validation (check each item has `name` and `price`) or shallow (check `items` is a list).
   - Recommendation: Deep validation -- check `items` is a non-empty list, and each item has `name` (string) and `price` (number). This catches the most common errors with clear messages like `"items[0] missing 'price'"`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 7.0 (in requirements.txt) |
| Config file | none -- see Wave 0 |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REL-01 | Missing fields return 400 with field name | integration (Flask test client) | `python -m pytest tests/test_server.py::test_missing_fields_return_400 -x` | No -- Wave 0 |
| REL-02 | Request > 10MB returns 413 | integration (Flask test client) | `python -m pytest tests/test_server.py::test_oversized_request_returns_413 -x` | No -- Wave 0 |
| REL-03 | Formatter state reset after exception | unit (Dummy printer) | `python -m pytest tests/test_formatter.py::test_state_reset_on_exception -x` | No -- Wave 0 |
| REL-04 | ESC@ sent at start of print job | unit (Dummy printer output inspection) | `python -m pytest tests/test_server.py::test_init_command_sent -x` | No -- Wave 0 |
| REL-05 | SIGTERM triggers cleanup | manual-only | Requires `systemctl stop` on Pi | N/A -- manual |
| QUAL-04 | No raw ESC/POS in print_server.py | unit (grep/static check) | `python -m pytest tests/test_server.py::test_no_raw_escpos -x` | No -- Wave 0 |
| QUAL-05 | Config not mutated by portrait pipeline | unit | `python -m pytest tests/test_server.py::test_config_not_mutated -x` | No -- Wave 0 |
| QUAL-06 | Error responses use consistent JSON format | integration (Flask test client) | `python -m pytest tests/test_server.py::test_error_format_consistent -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/` directory -- may not exist (Phase 4 creates the full suite; but Phase 2 needs basic smoke tests)
- [ ] `tests/test_server.py` -- Flask test client tests for validation and error format
- [ ] `tests/test_formatter.py` -- Formatter state reset tests using Dummy printer
- [ ] `tests/conftest.py` -- shared fixtures (Flask test app with dummy printer, sample config)
- [ ] Note: Phase 4 (Test Suite) is the designated testing phase. Phase 2 should verify its work with `--dummy` mode and manual `curl` tests. Formal pytest tests can be deferred to Phase 4, but basic smoke tests in this phase would increase confidence.

## Sources

### Primary (HIGH confidence)
- **Codebase direct inspection** -- all findings verified by reading source:
  - `print_server.py` -- all 6 JSON endpoints use `get_json(force=True)` with no validation (lines 99-203)
  - `printer_core.py:53-183` -- all Formatter methods confirmed lacking try/finally
  - `print_server.py:183-186` -- raw ESC/POS byte commands (`_raw()` calls)
  - `portrait_pipeline.py:395-398` -- config mutation via `setdefault()[key] = value`
  - `print_server.py:305-310` -- error handler returns inconsistent format
  - `print_server.py:335-336` -- mDNS cleanup via `atexit` only
- **python-escpos 3.1 source** -- `hw("INIT")` confirmed at `escpos/escpos.py:1174-1184`, `HW_INIT = ESC + b"@"` at `constants.py:42`
- **Flask 3.1.2 source** -- `MAX_CONTENT_LENGTH` default `None` at `app.py:198`, enforced via Werkzeug `get_input_stream()` at `wrappers/request.py:352`
- **Werkzeug 3.1.3 source** -- `RequestEntityTooLarge` raised at `wsgi.py:172-173` when `content_length > max_content_length`
- **python-escpos `set()` method** -- confirmed at `escpos/escpos.py:900-986`: `None` params are skipped (only set what you pass)

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` -- pitfalls 1, 2, 5, 6, 7 directly relevant to Phase 2 requirements
- `.planning/research/ARCHITECTURE.md` -- patterns 1, 3, 6, 7 directly relevant
- `.planning/STATE.md` -- "SIGTERM handling with Flask dev server has known quirks" flagged as concern

### Tertiary (LOW confidence)
- Flask dev server SIGTERM behavior -- documented in various GitHub issues but not officially guaranteed. Needs on-device testing.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new deps, all solutions use existing Flask/python-escpos features
- Architecture: HIGH -- all patterns verified against actual source code of Flask 3.1.2, Werkzeug 3.1.3, python-escpos 3.1
- Pitfalls: HIGH -- directly observed in codebase, all 10 Formatter methods audited, all 6 JSON endpoints audited
- SIGTERM handling: MEDIUM -- signal handler pattern is standard, but Flask dev server behavior needs on-device testing

**Research date:** 2026-03-08
**Valid until:** Indefinite -- this research is about the current codebase state and installed library versions, not external trends
