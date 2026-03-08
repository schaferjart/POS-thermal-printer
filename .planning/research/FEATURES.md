# Feature Landscape

**Domain:** Hardened appliance-style HTTP print server
**Researched:** 2026-03-08

## Table Stakes

Features the server needs or it remains unreliable. Missing any of these means the server can be crashed, abused, or left in a broken state by routine use.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Input validation on all endpoints | Missing keys cause 500 KeyError with Python traceback; callers get no useful feedback. Every endpoint except `/print/image` has this bug. | Low | Simple validation helper: `validate_keys(data, ["text"])` returns 400 with clear message. ~30 lines of code. |
| Request size limits | A single large image upload can exhaust Pi's 400MB memory limit and crash the service. No `MAX_CONTENT_LENGTH` is set. | Low | One line: `app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024`. Flask raises 413 automatically. |
| Graceful shutdown (SIGTERM handling) | systemd sends SIGTERM on restart/stop. Current server relies on `atexit` for mDNS cleanup, which Flask's dev server may not trigger. Printer connection is never closed. Stale mDNS registrations persist. | Medium | Register `signal.signal(signal.SIGTERM, handler)` to close printer, deregister mDNS, then `sys.exit(0)`. |
| Formatter state reset safety | Every Formatter method sets printer state (bold, align, font) then resets it at the end. An exception between set and reset leaves the printer in a dirty state for all subsequent prints. | Low | Wrap state changes in `try/finally` blocks. ~15 methods each need a 2-line change. |
| Richer health check | Current `/health` returns `{"status": "running"}` but says nothing about whether the printer is actually reachable. A health check that lies is worse than none. | Low-Med | Attempt a no-op printer query (or track last successful print timestamp). Return `{"status": "ok", "printer": "connected", "uptime": N, "last_print": timestamp}`. |
| Content-Type enforcement | `request.get_json(force=True)` parses any POST body as JSON regardless of headers. Accepts garbage that happens to parse as JSON. | Low | Remove `force=True`, check Content-Type, return 415 for non-JSON. |
| Error response consistency | Global error handler returns `{"error": str(e)}` but exceptions like KeyError produce unhelpful messages ("'text'"). Some errors leak Python internals. | Low | Catch specific exceptions before they hit the global handler. Return structured errors: `{"error": "Missing required field: text", "field": "text"}`. |

## Differentiators

Features that make the server robust and pleasant to operate, but the server technically works without them.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| API key authentication | Prevents accidental prints from other devices on shared networks. The mDNS broadcast actively advertises the server, so any device discovers it. | Low | Check `X-Print-Key` header against a key in `config.yaml`. Skip for `/health` and `/`. ~20 lines as a `@app.before_request` hook. |
| Rate limiting | Prevents paper waste from runaway clients or accidental loops. Without it, a `while true; do curl ...; done` drains an entire roll. | Low-Med | Two approaches: (1) flask-limiter with in-memory storage (adds a dependency, ~5 lines config), or (2) hand-rolled decorator with a dict of timestamps (~30 lines, no dependency). For a single-worker Pi server, in-memory is fine. Recommend hand-rolled to avoid dependency. 10 req/min per IP is reasonable. |
| systemd watchdog integration | systemd can auto-restart the service if the Python process hangs (not just crashes). Current restart limits only handle crashes. Hangs require manual intervention. | Medium | Use `sdnotify` library to send `WATCHDOG=1` heartbeats. Add `WatchdogSec=30` and `Type=notify` to the service file. A background thread pings the watchdog every 15s. |
| Structured logging | Current mix of `print("[TAG]...")` and `logging.getLogger()` makes log parsing impossible. `journalctl` output is a mess. | Low-Med | Switch all output to Python `logging` module with consistent format: `%(asctime)s %(levelname)s %(message)s`. Add request logging (method, path, status, duration). |
| Print job acknowledgment with details | Currently returns `{"status": "ok"}` with no detail. Callers can't distinguish "printed successfully" from "sent to printer buffer." | Low | Include job metadata in response: `{"status": "ok", "template": "markdown", "duration_ms": 342}`. Timer around `with_retry()`. |
| Printer status in health endpoint | Report paper-out, cover-open, or other printer status bits if the hardware supports it. Most ESC/POS printers support DLE EOT status queries. | Medium | python-escpos may support status queries. Needs hardware testing. Degrade gracefully if printer doesn't support status. |
| Temp file cleanup on startup | If process was killed between temp file creation and cleanup, orphan files persist. Low risk but accumulates on long-running appliance. | Low | On startup, clean `/tmp/tmp*.{jpg,png,jpeg}` files older than 1 hour. |
| Request ID / correlation | When debugging "why did my print fail?", matching server logs to client requests is currently impossible. | Low | Generate a UUID per request, include in response and log lines. `@app.before_request` hook. |
| Config validation on startup | Currently, a typo in `config.yaml` (e.g., missing `printer` section) causes a runtime crash on first print, not at startup. | Low | Validate required config keys at startup. Fail fast with clear message: "config.yaml missing 'printer.vendor_id'". |
| USB reconnect backoff | Current reconnect is immediate retry, then fail. If the printer is physically disconnected for 30 seconds (paper change, cable bump), every request during that window fails permanently. | Medium | Exponential backoff with max retry window (e.g., 3 attempts over 10 seconds). Mark printer as "offline" in health endpoint during reconnect window. |

## Anti-Features

Features to explicitly NOT build. These add complexity without value for a single-owner, single-printer, low-traffic appliance.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| HTTPS / TLS termination | This is a LAN-only appliance behind a home router. TLS adds certificate management complexity (renewal, trust chain) for zero security gain on a trusted network. No sensitive data in transit -- it's print content. | Keep HTTP. If security is needed later, put nginx in front. |
| Production WSGI server (gunicorn) | Flask dev server is single-threaded, which is correct for a single USB printer that can only handle one job at a time. gunicorn adds worker management complexity for no throughput gain. The `_print_lock` already serializes. | Keep Flask dev server. The thread lock is the real bottleneck, not the HTTP server. |
| Print queue / job management | A job queue (Redis, SQLite, etc.) adds state management, failure recovery, and queue-draining logic. The printer processes jobs in ~2-5 seconds. Sequential blocking is the correct behavior for a single printer. | Keep synchronous `with_retry()` pattern. Callers block until print completes or fails. |
| User accounts / multi-tenancy | Single owner, single printer. User management adds authentication flows, session management, database. Massively over-engineered. | Single API key in config.yaml is sufficient. |
| Web-based admin dashboard | Monitoring dashboards need frontend frameworks, WebSocket updates, persistent metrics storage. For one printer on a home network, `journalctl -u pos-printer -f` and `/health` endpoint are sufficient. | Enhance `/health` endpoint with useful fields. Use journalctl for debugging. |
| Automatic firmware/software updates | Auto-update on an embedded device risks bricking it mid-print. The "update" flow is `git pull && systemctl restart`. | Keep manual `git pull` update workflow. Document it clearly. |
| Request retry queue / dead letter | If a print fails after retry, the job is lost. Adding persistence (SQLite, filesystem) to retry later adds failure modes (corrupt DB, disk full) that are worse than the original problem. | Return error to caller. Caller can retry. |
| Multi-printer support | Architecture assumes single USB printer. Multi-printer needs device discovery, routing, per-printer locks, and status tracking. Different project. | Keep single printer assumption throughout. |
| Webhook callbacks / async notification | Async notification patterns (webhooks, SSE, WebSocket) add complexity for a system where print jobs take 2-5 seconds. Synchronous response is fine. | Return result synchronously in HTTP response. |

## Feature Dependencies

```
Request size limits -----> (none, standalone)
Input validation --------> (none, standalone)
Content-Type enforcement -> Input validation (same validation layer)
Error response consistency -> Input validation (structured error format)

Graceful shutdown -------> (none, standalone)
Formatter state safety --> (none, standalone)

API key auth ------------> Config validation (key must be in config)
Rate limiting -----------> (none, but benefits from request ID for debugging)
Request ID / correlation -> Structured logging (IDs useless without good logs)
Structured logging ------> (none, standalone)

Health check enrichment --> Printer status queries (extends health data)
systemd watchdog --------> Health check enrichment (watchdog checks same things)
USB reconnect backoff ---> Health check enrichment (report offline state)

Config validation -------> (none, standalone, should be first)
```

## MVP Recommendation (Table Stakes Phase)

Prioritize these -- they fix actual bugs and prevent crashes:

1. **Config validation on startup** -- fail fast, not on first request
2. **Input validation on all endpoints** -- stops 500 errors from bad input
3. **Request size limits** -- one line, prevents OOM kills
4. **Content-Type enforcement** -- part of the validation layer
5. **Error response consistency** -- callers get useful feedback
6. **Formatter state reset safety** -- prevents cascading print corruption
7. **Graceful shutdown** -- clean systemd lifecycle

Defer to second phase:
- **API key auth**: Needed but not a crash bug
- **Rate limiting**: Useful but the server works without it
- **Structured logging**: Important for debugging but not a reliability fix
- **systemd watchdog**: Insurance policy, not a fix
- **Health check enrichment**: Nice to have, current basic check is adequate short-term

Defer indefinitely (build only if pain is felt):
- **Printer status queries**: Hardware-dependent, may not work
- **USB reconnect backoff**: Current single-retry is adequate for most disconnection scenarios
- **Request ID / correlation**: Only valuable after structured logging is in place

## Sources

- [Flask Security Best Practices 2025](https://hub.corgea.com/articles/flask-security-best-practices-2025)
- [Flask Uploading Files Documentation](https://flask.palletsprojects.com/en/stable/patterns/fileuploads/) -- MAX_CONTENT_LENGTH
- [Health Endpoint Monitoring Pattern (Azure)](https://learn.microsoft.com/en-us/azure/architecture/patterns/health-endpoint-monitoring)
- [Health Check API Pattern (microservices.io)](https://microservices.io/patterns/observability/health-check-api.html)
- [Implementing Health Checks (AWS)](https://aws.amazon.com/builders-library/implementing-health-checks/)
- [Flask-Limiter Documentation](https://flask-limiter.readthedocs.io/en/stable/)
- [In-Memory Rate Limiter for Flask](https://blog.devgenius.io/rate-limiter-for-flask-backend-application-83002451bc48)
- [systemd WatchdogSec with Python](https://blog.stigok.com/2020/01/26/sd-notify-systemd-watchdog-python-3.html)
- [sdnotify (pure Python sd_notify)](https://github.com/bb4242/sdnotify)
- [Flask Security Considerations (official docs)](https://flask.palletsprojects.com/en/stable/web-security/)
- [Network Printer Security Best Practices (UC Berkeley)](https://security.berkeley.edu/education-awareness/network-printer-security-best-practices)
- [MAX_CONTENT_LENGTH issue discussion](https://github.com/pallets/flask/issues/1200)
