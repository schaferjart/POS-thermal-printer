# Technology Stack: Hardening

**Project:** POS Thermal Print Server
**Researched:** 2026-03-08
**Mode:** Ecosystem (hardening an existing Flask server on Raspberry Pi)

## Approach

This is a hardening milestone, not a greenfield project. The existing stack (Flask 3.1.3, Pillow 12.1.1, python-escpos 3.1, PyYAML 6.0.3) stays. This document covers **what to add** for input validation, authentication, rate limiting, testing, and graceful shutdown -- and what explicitly NOT to add.

The Pi runs Debian Trixie with Python 3.13. All recommended libraries have aarch64 wheels and support Python >= 3.10.

## Recommended Additions

### Input Validation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pydantic | 2.12.5 | Request body validation with type-safe models | Rust-backed core (fast validation even on Pi), 1.7MB aarch64 wheel, Python type hints as schemas -- no separate schema language. Already the industry standard for Python API validation. Flask-Pydantic (0.14.0) provides a `@validate` decorator for seamless integration. | HIGH |
| Flask-Pydantic | 0.14.0 | Flask decorator for pydantic validation | Turns pydantic models into Flask route decorators with automatic 400 responses on validation failure. Tiny dependency (just Flask + pydantic). | MEDIUM |

**Rationale for pydantic over alternatives:**
- **vs. marshmallow:** Marshmallow is schema-first with its own field DSL. Pydantic uses plain Python type hints -- less boilerplate, better IDE support. Pydantic v2's Rust core is faster than marshmallow for simple validation.
- **vs. jsonschema / flask-expects-json:** jsonschema requires writing JSON Schema dicts, which are verbose and error-prone for simple "require these keys with these types" checks. Pydantic models are more readable and provide both validation and documentation.
- **vs. hand-rolled `validate_keys()` helper:** The CONCERNS.md suggests this approach. It works for 3-4 endpoints, but pydantic is equally simple and gives you type coercion, optional fields with defaults, and nested object validation for free. A `validate_keys()` helper would need to be extended every time a new field type appears.
- **Memory concern:** pydantic-core is 1.7MB on aarch64 and runtime overhead is negligible for the ~10 request schemas this server needs. Well within the 400MB systemd budget.

**Example of what the validation code would look like:**
```python
from pydantic import BaseModel
from flask_pydantic import validate

class MessageRequest(BaseModel):
    text: str
    title: str = "NOTICE"

@app.route("/print/message", methods=["POST"])
@validate()
def print_message(body: MessageRequest):
    # body.text and body.title are guaranteed to exist and be strings
    ...
```

### Authentication

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Custom decorator (no library) | -- | API key check via `X-Print-Key` header | This is a single-owner appliance on a home network. A full auth library (Flask-Login, Flask-JWT-Extended, flask-api-key) is massive overkill. A 15-line `@require_api_key` decorator that checks a header against a value from config.yaml is the right solution. | HIGH |

**Why NOT use a library:**
- **flask-api-key:** Unmaintained (last release 2022), requires SQLAlchemy for key storage. We need to check one static string.
- **Flask-JWT-Extended / PyJWT:** JWT is for stateless auth across services with token rotation. This server has one client type (devices on the network) and one key. JWT adds complexity with zero benefit.
- **Flask-HTTPAuth:** Reasonable library, but still heavier than needed. The `@require_api_key` pattern is ~15 lines of code with zero dependencies.

**Implementation pattern:**
```python
import functools
from flask import request, jsonify

def require_api_key(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Print-Key")
        if key != _config.get("server", {}).get("api_key"):
            return jsonify({"error": "Invalid or missing API key"}), 401
        return f(*args, **kwargs)
    return decorated
```

Key stored in `config.yaml` (not committed -- add to `.gitignore` or use env var). Web UI endpoint exempt from key check (serves static HTML).

### Rate Limiting

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Flask-Limiter | 4.1.1 | Per-endpoint rate limiting | The standard Flask rate-limiting library. Mature (10+ years), actively maintained, supports in-memory storage backend -- no Redis needed. Decorates routes with rate strings like `"10 per minute"`. | HIGH |

**Storage backend: `memory://`**

Flask-Limiter's docs warn that in-memory storage is "only for testing/development." This warning is about multi-process deployments where each worker has its own counter. It does NOT apply here because:
1. Flask dev server is single-process, single-thread
2. Even if upgraded to gunicorn with `--workers 1`, it's still one process
3. Rate limits reset on server restart -- acceptable for an appliance that rarely restarts

Redis/memcached would add a service dependency, memory usage, and operational complexity for zero benefit on a single-process print server.

**Rate limit recommendations:**
- Global default: `30 per minute` (prevents runaway scripts)
- `/print/image` and `/portrait/*`: `5 per minute` (heavy processing + paper waste)
- `/` (web UI): exempt (just serves HTML)
- `/health`: exempt

### Request Size Limits

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Flask built-in (`MAX_CONTENT_LENGTH`) | -- | Cap upload size | Flask has this built in. Set `app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024` (10MB). Returns 413 automatically for oversized requests. No library needed. | HIGH |

10MB is generous for thermal printing (576px wide images are tiny) but prevents multi-GB uploads from exhausting the Pi's 1GB RAM. The 400MB systemd memory cap is a second line of defense.

### Testing

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pytest | 9.0.2 | Test runner | The Python testing standard. Zero contest. | HIGH |
| pytest-cov | 7.0.0 | Coverage reporting | Identifies untested code paths. Integrates with pytest via `--cov` flag. | HIGH |

**Why NOT pytest-image-snapshot for image testing:**
The CONCERNS.md flags missing tests for `md_renderer.py` and `image_printer.py`. The temptation is golden-image regression tests. **Do not do this yet.** Reasons:
1. Thermal print output is visually judged -- "correct" is subjective
2. Golden images are brittle: font rendering varies across macOS vs Pi, Pillow versions, and even fontconfig settings
3. The high-value tests are for **parsing logic** (does `_parse_md` produce correct AST?) and **validation** (does the server reject bad input?), not pixel-perfect rendering
4. If golden image tests are needed later, `pytest-image-snapshot` (0.4.5) is the right choice -- it uses Pillow for comparison and supports tolerance thresholds

**What to test first (priority order):**
1. `md_renderer.py` -- `_parse_md()` function: input markdown string -> parsed block list. Pure data in, data out. Easy to test, high value (the fragile regex parsing).
2. Input validation: each endpoint rejects missing required fields with 400, accepts valid payloads.
3. `image_printer.py` -- dithering mode dispatch, parameter validation. Not pixel output.
4. `printer_core.py` -- `Formatter` methods with `Dummy` printer: verify ESC/POS command sequences.

**Test file structure:**
```
tests/
    conftest.py          # fixtures: Flask test client, dummy printer, sample config
    test_md_parser.py    # _parse_md unit tests
    test_validation.py   # endpoint input validation
    test_image_printer.py # mode dispatch, parameter handling
    test_formatter.py    # Formatter with Dummy printer
```

### Graceful Shutdown

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python `signal` module (stdlib) | -- | SIGTERM handler for clean shutdown | Register `signal.signal(signal.SIGTERM, handler)` to close printer connection and deregister mDNS before exit. The current `atexit` approach doesn't fire reliably on SIGTERM from systemd. No library needed. | MEDIUM |

**Why MEDIUM confidence:** Flask's dev server has quirks with signal handling. The handler needs to: (1) deregister Zeroconf mDNS, (2) close the USB printer connection, (3) call `sys.exit(0)`. This may need testing on the actual Pi with `systemctl stop pos-printer` to verify it fires correctly. If Flask's dev server swallows SIGTERM, the fallback is `atexit` + setting `KillMode=mixed` in the systemd unit.

## Alternatives Considered and Rejected

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Validation | pydantic 2.12.5 | marshmallow 4.0.0 | Own field DSL vs. native type hints. More boilerplate for same result. |
| Validation | pydantic 2.12.5 | Hand-rolled `validate_keys()` | Works initially but doesn't scale. Pydantic gives type coercion, defaults, nested validation for free. |
| Validation | pydantic 2.12.5 | flask-expects-json + jsonschema | JSON Schema dicts are verbose. Pydantic models are more readable and Pythonic. |
| Auth | Custom decorator | Flask-JWT-Extended | JWT is for multi-service token rotation. One static API key needs one `if` statement. |
| Auth | Custom decorator | flask-api-key | Unmaintained, requires SQLAlchemy. We store one key in config.yaml. |
| Auth | Custom decorator | Flask-HTTPAuth | Reasonable but adds a dependency for 15 lines of code. |
| Rate limiting | Flask-Limiter (memory://) | Flask-Limiter (Redis) | Redis adds a service, memory, and ops burden. Single-process server makes in-memory sufficient. |
| Rate limiting | Flask-Limiter | Custom middleware | Flask-Limiter handles edge cases (sliding windows, header injection, exemptions) that hand-rolled code misses. |
| Testing | pytest | unittest | pytest is less boilerplate, better fixtures, better output. Industry standard. |
| Testing | Plain pytest | pytest-image-snapshot | Golden image tests are brittle across platforms. Parse/validate tests have higher ROI. |
| WSGI server | Flask dev server | gunicorn | PROJECT.md explicitly marks this out of scope. Single printer, single user, low traffic. Flask dev server is adequate. |

## What NOT to Install

| Technology | Why Not |
|------------|---------|
| gunicorn | Out of scope per PROJECT.md. Single printer, low traffic. Flask dev server is adequate. |
| Redis / memcached | No multi-process coordination needed. Adds operational complexity on Pi. |
| SQLAlchemy / any ORM | No database. Config is in YAML. API key is a string. |
| Flask-Login / Flask-Security | User session management for multi-user apps. This is a single-owner API. |
| celery / any task queue | Print jobs are synchronous and sequential by nature (one USB printer). |
| mypy / type checking | Valuable in general, but the codebase has no type annotations. Adding mypy to an untyped codebase produces thousands of errors. Not a hardening priority. |
| black / ruff / linting | Good practice but not a hardening concern. Could be a future milestone. |
| docker | Pi runs bare metal with systemd. Docker adds memory overhead (significant on 1GB Pi 3) and complexity. |

## Installation

```bash
# Hardening dependencies (add to requirements.txt)
pip install pydantic==2.12.5 Flask-Pydantic==0.14.0 Flask-Limiter==4.1.1

# Dev/testing dependencies (add to requirements-dev.txt, new file)
pip install pytest==9.0.2 pytest-cov==7.0.0
```

**Note:** Create a separate `requirements-dev.txt` for test dependencies. The Pi doesn't need pytest installed -- tests run on the dev machine (macOS) and in CI.

## Dependency Impact Assessment

| Package | Install Size (aarch64) | Runtime Memory | Transitive Deps |
|---------|----------------------|----------------|------------------|
| pydantic + pydantic-core | ~3MB | Negligible for ~10 models | annotated-types, typing-extensions |
| Flask-Pydantic | <100KB | Negligible | None (just Flask + pydantic) |
| Flask-Limiter | <200KB | ~1-2MB for in-memory counters | limits, ordered-set, deprecated, packaging |
| pytest (dev only) | ~3MB | N/A (not on Pi) | iniconfig, pluggy, packaging |
| pytest-cov (dev only) | <500KB | N/A (not on Pi) | coverage |

**Total production impact:** ~5MB disk, ~2-3MB runtime memory. Well within Pi 3 constraints (1GB RAM, 400MB systemd limit).

## Version Compatibility Matrix

| Package | Requires Python | Pi Python (3.13) | aarch64 Wheel |
|---------|----------------|-------------------|---------------|
| pydantic 2.12.5 | >= 3.9 | OK | Yes (manylinux) |
| Flask-Pydantic 0.14.0 | >= 3.7 | OK | Pure Python |
| Flask-Limiter 4.1.1 | >= 3.10 | OK | Pure Python |
| pytest 9.0.2 | >= 3.10 | OK | Pure Python |
| pytest-cov 7.0.0 | >= 3.9 | OK | Pure Python |

## Sources

- [pydantic PyPI](https://pypi.org/project/pydantic/) -- version 2.12.5, aarch64 wheel verified
- [pydantic-core PyPI](https://pypi.org/project/pydantic_core/) -- 1.7MB aarch64 wheel
- [Flask-Pydantic PyPI](https://pypi.org/project/Flask-Pydantic/) -- version 0.14.0
- [Flask-Limiter docs](https://flask-limiter.readthedocs.io/) -- version 4.1.1, memory:// storage
- [Flask-Limiter GitHub discussion #373](https://github.com/alisaifee/flask-limiter/discussions/373) -- in-memory storage in production context
- [Flask docs - file uploads](https://flask.palletsprojects.com/en/stable/patterns/fileuploads/) -- MAX_CONTENT_LENGTH
- [pytest PyPI](https://pypi.org/project/pytest/) -- version 9.0.2
- [pytest-cov PyPI](https://pypi.org/project/pytest-cov/) -- version 7.0.0
- [pytest-image-snapshot PyPI](https://pypi.org/project/pytest-image-snapshot/) -- version 0.4.5 (noted but not recommended yet)
- [Debian Trixie python3 package](https://packages.debian.org/trixie/python3) -- Python 3.13
- [pydantic v2 memory allocation issue #8652](https://github.com/pydantic/pydantic/issues/8652) -- memory footprint analysis
- [Flask API key authentication tutorial](https://blog.teclado.com/api-key-authentication-with-flask/) -- custom decorator pattern
- [Signal handling for graceful shutdown](https://johal.in/signal-handling-in-python-custom-handlers-for-graceful-shutdowns/) -- Python signal + SIGTERM patterns

---

*Stack research: 2026-03-08*
