# Phase 3: Access Control and Observability - Research

**Researched:** 2026-03-09
**Domain:** Flask API key middleware, printer status querying, server observability
**Confidence:** HIGH

## Summary

This phase adds two independent capabilities to the print server: (1) optional API key authentication on print endpoints via the `X-Print-Key` header, and (2) an enhanced `/health` endpoint that reports actual printer connection status, server uptime, and last successful print timestamp.

Both features are straightforward to implement using Flask's built-in `before_request` hook and Python's `time` module. No new dependencies are required. The API key feature reads from `config.yaml` and is backwards-compatible -- when no key is configured, authentication is disabled entirely. The health endpoint enhancement requires careful handling of `python-escpos`'s status query methods, which raise `NotImplementedError` on the Dummy printer and can timeout on real hardware.

**Primary recommendation:** Use `@app.before_request` with an allowlist of exempt endpoints (health, index, static) for auth, and wrap `printer.is_online()` in a try/except for status probing. Track uptime and last-print-time as module-level variables in `print_server.py`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | Server checks X-Print-Key header against key in config.yaml on all print endpoints | Flask `before_request` hook with `request.headers.get("X-Print-Key")` comparison against `_config["server"]["api_key"]` |
| AUTH-02 | /health and / (web UI) endpoints are accessible without API key | Exempt endpoint allowlist checked via `request.endpoint` in `before_request` |
| AUTH-03 | If no API key is configured in config.yaml, auth is disabled (backwards compatible) | Check `_config.get("server", {}).get("api_key")` -- if falsy, skip auth entirely |
| OBS-01 | /health endpoint reports printer connection status (connected/disconnected) | `printer.is_online()` wrapped in try/except; Dummy raises `NotImplementedError`, treat as "unknown" or "dummy" |
| OBS-02 | /health endpoint reports server uptime and last successful print timestamp | Module-level `_server_start_time = time.time()` set in `main()`, `_last_print_time` updated in `with_retry()` on success |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | 3.1.x | `before_request` hook for auth middleware | Already in use, built-in mechanism |
| python-escpos | 3.1 | `is_online()` method for printer status | Already in use, has status query API |
| time (stdlib) | -- | Uptime and timestamp tracking | Zero dependencies |

### Supporting
No new libraries needed. Everything is built with existing dependencies.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `before_request` | Custom decorator on each route | More verbose, easy to forget on new endpoints, `before_request` is the Flask-standard approach |
| `flask-httpauth` | Adds dependency | Overkill for single static API key, our case is ~10 lines |
| `hmac.compare_digest` | Plain `==` | `compare_digest` prevents timing attacks; use it even though LAN-only |

## Architecture Patterns

### Auth Implementation Pattern

The `before_request` hook runs before every request. It checks if the current endpoint is in the exempt list. If not, it compares the `X-Print-Key` header against the configured key.

```python
# Source: Flask official docs + project conventions
import hmac

# Endpoints that do NOT require authentication
_PUBLIC_ENDPOINTS = frozenset({"health", "index", "static"})

@app.before_request
def check_api_key():
    """Require X-Print-Key header on print endpoints when api_key is configured."""
    api_key = _config.get("server", {}).get("api_key")
    if not api_key:
        return  # No key configured = auth disabled (AUTH-03)
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return  # Public endpoints skip auth (AUTH-02)
    provided = request.headers.get("X-Print-Key", "")
    if not hmac.compare_digest(provided, api_key):
        return error_response("Invalid or missing API key", status=401)
```

Key design points:
- `hmac.compare_digest` prevents timing side-channel (stdlib, zero cost)
- `frozenset` lookup is O(1) for the exempt check
- Returning `None` from `before_request` lets the request proceed
- Returning a Response tuple aborts the request with that response
- Uses the existing `error_response()` helper for consistent JSON format

### Health Endpoint Enhancement Pattern

```python
# Source: python-escpos docs + project conventions
_server_start_time = None  # Set in main()
_last_print_time = None    # Updated in with_retry() on success

@app.route("/health", methods=["GET"])
def health():
    now = time.time()
    status_data = {
        "status": "running",
        "dummy": _dummy,
        "uptime_seconds": round(now - _server_start_time, 1) if _server_start_time else 0,
        "last_print": _last_print_time,  # ISO string or null
    }
    # Printer connection status
    try:
        status_data["printer"] = "connected" if _printer.is_online() else "disconnected"
    except NotImplementedError:
        status_data["printer"] = "dummy"
    except Exception:
        status_data["printer"] = "disconnected"
    return jsonify(status_data)
```

### Last Print Timestamp Tracking

Update `_last_print_time` inside `with_retry()` after a successful print:

```python
from datetime import datetime, timezone

def with_retry(fn):
    global _last_print_time
    with _print_lock:
        try:
            fmt = get_formatter()
            fmt.p.hw("INIT")
            fn(fmt)
            _last_print_time = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            logger.warning("Print failed (%s), reconnecting...", e)
            try:
                fmt = reconnect()
                fmt.p.hw("INIT")
                fn(fmt)
                _last_print_time = datetime.now(timezone.utc).isoformat()
            except Exception as e2:
                logger.error("Retry also failed: %s", e2)
                raise
```

### Config.yaml Addition

```yaml
server:
  host: "0.0.0.0"
  port: 9100
  # api_key: "your-secret-key-here"  # Uncomment to enable auth
```

The key is optional. When absent or empty string, auth is disabled (AUTH-03 backwards compatibility). This means `config.yaml` does NOT need to change for existing deployments.

### Anti-Patterns to Avoid
- **Checking auth in each route function:** Easy to forget, violates DRY. Use `before_request` instead.
- **Using plain `==` for key comparison:** Vulnerable to timing attacks. Use `hmac.compare_digest`.
- **Calling `is_online()` on every health check without timeout protection:** USB queries can hang if the printer is in a bad state. Wrap in try/except with a reasonable approach.
- **Storing timestamps as epoch floats:** ISO 8601 strings are human-readable in JSON responses.
- **Adding api_key to `validate_config` required keys:** That would break backwards compatibility (AUTH-03).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timing-safe comparison | Custom string comparison | `hmac.compare_digest` (stdlib) | Constant-time comparison prevents side-channel attacks |
| ISO timestamp formatting | Manual string formatting | `datetime.now(timezone.utc).isoformat()` | Handles timezone, microseconds correctly |
| Request lifecycle hooks | Custom decorator wrapping each route | `Flask.before_request` | Built-in, guaranteed to run, catches new routes automatically |

## Common Pitfalls

### Pitfall 1: Dummy Printer Status Raises NotImplementedError
**What goes wrong:** Calling `_printer.is_online()` on the `Dummy` printer class throws `NotImplementedError`, crashing the health endpoint.
**Why it happens:** `Dummy` class does not implement `_raw()` or `_read()` which `query_status()` depends on.
**How to avoid:** Always wrap `is_online()` in try/except. Return `"dummy"` for `NotImplementedError`, `"disconnected"` for other exceptions.
**Confidence:** HIGH -- verified by running `Dummy().is_online()` locally.

### Pitfall 2: Forgetting to Exempt New Public Endpoints
**What goes wrong:** Adding a new public route later (e.g., `/status`, `/docs`) without adding it to `_PUBLIC_ENDPOINTS` causes 401 for unauthenticated users.
**How to avoid:** Use a frozenset constant at the top of the file with a clear comment. Document in CLAUDE.md that new public endpoints need to be added to the set.
**Warning signs:** New endpoint returns 401 when tested without a key.

### Pitfall 3: USB Status Query Hangs
**What goes wrong:** `is_online()` sends DLE EOT over USB and reads a response. If the printer is in an error state or mid-print, the read can hang or timeout.
**Why it happens:** USB reads are blocking and some printers don't respond to status queries during paper feed.
**How to avoid:** The try/except already handles this. Do NOT hold `_print_lock` during health checks -- the lock is only for print operations. If `is_online()` hangs, it only blocks the health response, not print jobs.
**Confidence:** MEDIUM -- known from python-escpos issues, printer-model dependent.

### Pitfall 4: Thread Safety of Global Timestamps
**What goes wrong:** `_last_print_time` is written inside `_print_lock` (from `with_retry`) and read from `health()` without the lock.
**Why it happens:** Python's GIL makes simple reference assignment atomic for CPython, so reading a string reference without a lock is safe. But this is a CPython implementation detail.
**How to avoid:** Since Flask dev server is single-threaded and `_print_lock` serializes all writes, this is safe in practice. The read of `_last_print_time` is a single reference read which is atomic under CPython's GIL. No additional locking needed.
**Confidence:** HIGH -- Flask dev server, single printer, GIL protects reference reads.

### Pitfall 5: Stress Test Needs Updating
**What goes wrong:** The existing `stress_test.sh` expects all print endpoints to return 200 without any headers. After adding auth, those tests will fail if `api_key` is configured.
**How to avoid:** This is fine because AUTH-03 ensures backwards compatibility -- if no key is configured, auth is off. The stress test runs against the default config. Document that when api_key is set, stress_test.sh needs `-H "X-Print-Key: ..."` added.
**Confidence:** HIGH -- reviewed stress_test.sh source.

## Code Examples

### Complete before_request Auth Hook
```python
# Source: Flask docs + hmac stdlib
import hmac

_PUBLIC_ENDPOINTS = frozenset({"health", "index", "static"})

@app.before_request
def check_api_key():
    api_key = _config.get("server", {}).get("api_key")
    if not api_key:
        return  # Auth disabled
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return  # Public route
    provided = request.headers.get("X-Print-Key", "")
    if not hmac.compare_digest(provided, api_key):
        return error_response("Invalid or missing API key", status=401)
```

### Complete Enhanced Health Endpoint
```python
@app.route("/health", methods=["GET"])
def health():
    now = time.time()
    result = {
        "status": "running",
        "dummy": _dummy,
        "uptime_seconds": round(now - _server_start_time, 1) if _server_start_time else 0,
        "last_print": _last_print_time,
    }
    try:
        result["printer"] = "connected" if _printer.is_online() else "disconnected"
    except NotImplementedError:
        result["printer"] = "dummy"
    except Exception:
        result["printer"] = "disconnected"
    return jsonify(result)
```

### Test Pattern for Auth (Phase 4 preview)
```python
# For the planner's awareness -- Phase 4 (TEST-04) will test auth
def test_request_without_key_returns_401(client_with_auth):
    resp = client_with_auth.post("/print/message", json={"text": "hi"})
    assert resp.status_code == 401

def test_request_with_correct_key_returns_200(client_with_auth):
    resp = client_with_auth.post(
        "/print/message",
        json={"text": "hi"},
        headers={"X-Print-Key": "test-secret"},
    )
    assert resp.status_code == 200

def test_health_no_key_returns_200(client_with_auth):
    resp = client_with_auth.get("/health")
    assert resp.status_code == 200
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Route-level decorators for auth | `before_request` hooks | Flask 0.7+ (stable since 2011) | Centralized auth, impossible to forget |
| `==` for secret comparison | `hmac.compare_digest` | Python 3.3+ | Timing-attack resistant |
| `datetime.utcnow()` | `datetime.now(timezone.utc)` | Python 3.12 deprecated utcnow() | Timezone-aware, future-proof |

## Open Questions

1. **Should `is_online()` be called on every `/health` request?**
   - What we know: USB status queries are fast (~50ms) when the printer responds, but can hang if the printer is in error state.
   - What's unclear: Whether frequent status queries interfere with print jobs on this specific printer model.
   - Recommendation: Call it on every request. The health endpoint is rarely hit, and it's not holding `_print_lock` so it won't block prints. If it hangs, only that one HTTP response is delayed.

2. **Should the api_key support environment variable override?**
   - What we know: The portrait pipeline already uses `openrouter_api_key_env` pattern for env var indirection.
   - What's unclear: Whether the user wants env var support or config-only.
   - Recommendation: Keep it simple -- config.yaml only. The Pi deployment uses direct config. Env var support can be added later if needed (not in v1 requirements).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (uses defaults) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | Print request without X-Print-Key returns 401 | integration | `python -m pytest tests/test_server.py -x -k "auth"` | No -- Wave 0 |
| AUTH-02 | /health and / respond without API key | integration | `python -m pytest tests/test_server.py -x -k "public"` | No -- Wave 0 |
| AUTH-03 | No api_key configured = auth disabled | integration | `python -m pytest tests/test_server.py -x -k "no_key"` | No -- Wave 0 |
| OBS-01 | /health reports printer connection status | integration | `python -m pytest tests/test_server.py -x -k "health_status"` | No -- Wave 0 |
| OBS-02 | /health reports uptime and last print timestamp | integration | `python -m pytest tests/test_server.py -x -k "health_uptime"` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_server.py` -- add auth and health test classes (file exists but needs new test classes)
- [ ] `tests/conftest.py` -- add `client_with_auth` fixture (app fixture with `api_key` in config)

## Sources

### Primary (HIGH confidence)
- Flask `before_request` docs -- verified `request.endpoint` values and return semantics locally
- python-escpos 3.1 source -- verified `is_online()`, `paper_status()`, `query_status()` methods and `NotImplementedError` on Dummy
- Local verification -- `Dummy().is_online()` raises `NotImplementedError` (confirmed)
- Local verification -- `request.endpoint` returns function name as string (confirmed)

### Secondary (MEDIUM confidence)
- [python-escpos methods documentation](https://python-escpos.readthedocs.io/en/latest/user/methods.html) -- `is_online()`, `paper_status()`, `query_status()` API
- [python-escpos issue #143](https://github.com/python-escpos/python-escpos/issues/143) -- DLE EOT status command behavior and limitations
- [Flask API key authentication tutorial](https://blog.teclado.com/api-key-authentication-with-flask/) -- `before_request` pattern

### Tertiary (LOW confidence)
- None -- all findings verified against source code or local execution

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all patterns verified locally
- Architecture: HIGH -- `before_request` and `hmac.compare_digest` are standard Flask/Python patterns; tested in local Python
- Pitfalls: HIGH for Dummy/NotImplementedError (verified), MEDIUM for USB hang behavior (printer-model dependent)

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable domain, no fast-moving dependencies)
