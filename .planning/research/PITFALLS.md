# Domain Pitfalls

**Domain:** Thermal print server appliance (Flask + ESC/POS on Raspberry Pi)
**Researched:** 2026-03-08

## Critical Pitfalls

Mistakes that cause service outages, data loss, or require rewrites.

### Pitfall 1: USB Printer State Becomes Permanently Wedged After Exception

**What goes wrong:** An exception occurs mid-print (e.g., out of paper, USB hiccup) while the ESC/POS printer is in a non-default state (bold on, alignment changed, double-width active). The Formatter methods in `printer_core.py` set state at the beginning and reset at the end -- but no `try/finally` guards exist. When the exception fires between set and reset, the printer hardware retains that state for all subsequent prints. Bold text, wrong alignment, or double-sized characters persist until the printer is power-cycled or an explicit reset command is sent.

**Why it happens:** Every Formatter method follows a set-do-reset pattern without exception safety. The `with_retry` wrapper in `print_server.py` catches the error and reconnects, but reconnecting creates a new `Usb` object -- it does not send an ESC/POS initialize command (`ESC @` / `\x1b\x40`) to the printer hardware. The printer's internal state machine is independent of the USB connection state.

**Consequences:** All prints after the failure render incorrectly (wrong font size, alignment, bold). Users see garbled output and don't know why. The problem survives reconnection and only a power cycle or explicit `ESC @` command fixes it.

**Prevention:**
1. Add `try/finally` guards to every Formatter method that changes printer state.
2. Send `ESC @` (initialize printer) at the start of every print job in `with_retry`, not just on reconnect. This is the ESC/POS "reset to defaults" command.
3. Alternatively, wrap state changes in a context manager: `with fmt.state(bold=True, align="center"):`.

**Detection:** Print output suddenly changes style (everything bold, everything centered, double-size) after a failed print job. Check `journalctl -u pos-printer` for preceding error logs.

**Confidence:** HIGH -- directly observed in codebase (`printer_core.py` lines 39-160, no `finally` blocks).

---

### Pitfall 2: No Request Size Limits Enables Memory Exhaustion on Pi

**What goes wrong:** The Flask server has no `MAX_CONTENT_LENGTH` configured. A client (malicious or accidental) uploads a 500MB image to `/print/image` or sends a 100MB JSON body to `/print/markdown`. Flask reads the entire body into memory. On a Pi 3 with 1GB RAM and a 400MB systemd `MemoryMax`, this triggers an OOM kill. The service restarts, but if requests keep coming, the restart limits (3 per 60s) are hit and the service stays down.

**Why it happens:** Flask's `MAX_CONTENT_LENGTH` is not set by default. The `request.get_json(force=True)` call reads the entire request body regardless of Content-Type header. File uploads via `request.files` are similarly unbounded. The systemd `MemoryMax=400M` is a backstop, not a prevention -- by the time it triggers, the service is already crashing.

**Consequences:** Service goes down. On shared networks without auth, anyone can trigger this. Three rapid OOM kills in 60 seconds exhausts the restart budget, leaving the printer offline until manual intervention.

**Prevention:**
1. Set `app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024` (16MB is generous for thermal printing -- even large images compress well under this). Flask/Werkzeug will return 413 automatically.
2. For JSON endpoints specifically, validate `request.content_length` before calling `get_json()`.
3. The systemd `MemoryMax=400M` is already a good last-resort safety net -- keep it.

**Detection:** Service crashes with `Killed` in journalctl (OOM killer). Or service enters "start-limit-hit" state and won't restart.

**Confidence:** HIGH -- `MAX_CONTENT_LENGTH` is confirmed unset in codebase; Flask issue #1200 confirms the behavior.

---

### Pitfall 3: SD Card Corruption From Excessive Writes on Pi

**What goes wrong:** The Pi's SD card wears out or corrupts from continuous log writes. Flask logs every request. systemd journal writes continuously. The default ext4 filesystem updates access times on every file read. Over months of uptime, these writes accumulate. A power loss during a write can corrupt the filesystem, bricking the Pi until the SD card is reflashed.

**Why it happens:** SD cards have limited write endurance (consumer cards: ~3,000-10,000 write cycles per cell). The Pi has no battery backup, so a power loss causes unclean shutdown. Default Raspbian/Debian mounts with `relatime` and writes journal logs to the SD card. Flask's stdout logging (via systemd `StandardOutput=journal`) generates writes for every HTTP request.

**Consequences:** SD card failure requires reflashing the entire OS and redeploying. Log files can fill the card causing the service to fail. A 2025 study measured ~3% annual flash failure rate under non-ideal conditions for devices like Pi.

**Prevention:**
1. Mount with `noatime,nodiratime` in `/etc/fstab` to eliminate access-time writes.
2. Move `/var/log` to tmpfs: add `tmpfs /var/log tmpfs defaults,noatime,nosuid,nodev,noexec,size=50M 0 0` to `/etc/fstab`.
3. Limit journald disk usage: set `SystemMaxUse=20M` in `/etc/systemd/journald.conf`.
4. Set `commit=600` mount option to batch filesystem metadata writes (flush every 10 minutes instead of every 5 seconds).
5. Use a high-endurance SD card (Samsung PRO Endurance, SanDisk High Endurance).

**Detection:** Filesystem errors in `dmesg`. Read-only remount by kernel. Service fails to write temp files. Corrupted files after power loss.

**Confidence:** HIGH -- well-documented Pi failure mode; multiple sources (Hackaday, dzombak.com, Pi Forums).

---

### Pitfall 4: `usblp` Kernel Module Steals Printer on Reboot

**What goes wrong:** After a kernel update or fresh boot, the `usblp` kernel module loads before the blacklist takes effect, or a kernel update re-enables it. The module claims the USB printer's interface, making it unavailable to python-escpos via libusb. The print server starts but every print fails with "Resource busy" or "USBNotFoundError."

**Why it happens:** The setup.sh correctly creates `/etc/modprobe.d/no-usblp.conf` with `blacklist usblp`, but: (a) kernel updates can reset modprobe configuration, (b) `initramfs` may load the module before the blacklist is processed if `update-initramfs` isn't run after blacklisting, (c) the `rmmod usblp` in setup.sh only unloads it for the current session.

**Consequences:** Print server appears healthy (HTTP endpoints respond, health check passes) but all print jobs fail. This is particularly insidious because the failure only manifests on actual print attempts, not at startup.

**Prevention:**
1. Run `sudo update-initramfs -u` after creating the blacklist (already partially handled but worth making explicit in setup.sh).
2. Add a startup check in `print_server.py`: before connecting, verify `usblp` is not loaded (`lsmod | grep usblp`) and log a clear error if it is.
3. Add the printer check to the `/health` endpoint -- attempt a no-op printer communication, not just return "running."
4. Pin the kernel version on the Pi to avoid surprise kernel updates overwriting modprobe config.

**Detection:** Print jobs return 500 errors with "Resource busy" in the log. `lsmod | grep usblp` shows the module loaded. `ls /dev/usb/lp*` shows the kernel driver has claimed the device.

**Confidence:** HIGH -- already documented in CLAUDE.md and MEMORY.md as a discovered lesson; confirmed in pyusb issues #76, #391.

---

### Pitfall 5: Graceful Shutdown Fails, Leaving Stale mDNS and Dirty USB

**What goes wrong:** When systemd sends SIGTERM to stop the service (during restart, deployment, or shutdown), the Flask dev server does not reliably trigger `atexit` handlers. The Zeroconf mDNS registration persists as a stale entry on the network. The USB printer connection is never explicitly closed, leaving the USB interface claimed. On restart, the new process may get "Resource busy" because the old process's USB claim wasn't released.

**Why it happens:** Flask's built-in dev server (Werkzeug) has known issues with signal handling. The `atexit` module only fires on clean Python interpreter exit, not on all signal types. SIGTERM may kill the process before `atexit` callbacks execute. The `KillMode=mixed` in the systemd service sends SIGTERM to the main process and SIGKILL to remaining processes after `TimeoutStopSec=15`, but if Flask doesn't handle SIGTERM, the cleanup never runs.

**Consequences:** Stale mDNS entries cause client confusion (device advertised but not responding). USB "Resource busy" on restart requires manual intervention or the 0.5s sleep in `reconnect()` may not be enough. Systemd's `RestartSec=10` partially mitigates this by giving the USB interface time to release.

**Prevention:**
1. Register a `signal.signal(signal.SIGTERM, handler)` in `main()` that explicitly closes the printer and unregisters mDNS before calling `sys.exit(0)`.
2. In the SIGTERM handler, release the USB interface: `_printer.close()` then `_zeroconf.unregister_service()` then `_zeroconf.close()`.
3. Do NOT rely on `atexit` for critical cleanup in a systemd-managed service.
4. Add `ExecStopPost=/bin/sleep 1` to the systemd service file if USB release timing is still an issue after implementing signal handling.

**Detection:** After `systemctl restart pos-printer`, check if mDNS still shows the old entry (`dns-sd -B _http._tcp`). Check logs for "Resource busy" errors on startup.

**Confidence:** HIGH -- Flask/Werkzeug signal handling issues documented in Flask GitHub issue #385 and related discussions; `atexit` limitation is in Python stdlib docs.

## Moderate Pitfalls

### Pitfall 6: Config Mutation Bug Causes Silent State Leak Between Requests

**What goes wrong:** `run_pipeline()` in `portrait_pipeline.py` mutates the shared module-level `_config` dict via `config.setdefault("portrait", {})["blur"] = blur`. One request's blur value persists for all subsequent requests that don't explicitly set blur. A user sends `blur=20`, and every portrait after that silently uses blur=20 instead of the config default of 10.

**Why it happens:** Python dicts are mutable and `_config` is a module-level global. The `setdefault` + assignment pattern modifies the dict in place. There's no deep copy before mutation.

**Prevention:**
1. Deep-copy the config before passing to `run_pipeline()`: `import copy; local_config = copy.deepcopy(_config)`.
2. Better: pass blur/mode as explicit function parameters instead of modifying the config dict. The function signature already accepts these -- stop writing them back to config.

**Detection:** Print the same portrait with default settings twice. If the second print looks different from the first, config mutation is occurring. Add logging of effective config values at print time.

**Confidence:** HIGH -- directly observed in codebase (`portrait_pipeline.py` lines 399-402), documented in CONCERNS.md.

---

### Pitfall 7: Missing Input Validation Returns 500 Instead of 400

**What goes wrong:** All server endpoints use `request.get_json(force=True)` and immediately index into the result with `data["text"]`, `data["heading"]`, etc. If a key is missing, Python raises `KeyError`, which the global error handler catches and returns as a 500 with the raw exception string. This tells the client nothing useful and makes the server look broken rather than indicating bad input.

**Why it happens:** No validation step exists between parsing the JSON and using it. The `force=True` parameter bypasses Content-Type checking, so any POST body is parsed as JSON regardless of header. If the body isn't valid JSON, `get_json` returns `None`, and `None["text"]` raises `TypeError`.

**Consequences:** Clients get unhelpful error messages. Automated clients (like the portrait pipeline or n8n webhooks) can't distinguish between "I sent bad data" and "the server is broken." Monitoring sees 500 errors and flags false alarms.

**Prevention:**
1. Add a `validate_keys(data, required_keys)` helper that checks for `None` (invalid JSON) and missing keys, returning 400 with a clear message.
2. Apply it as the first line in every endpoint handler.
3. Pattern: `data = request.get_json(force=True); if not data: return jsonify({"error": "Invalid JSON body"}), 400`.

**Detection:** Send a POST with empty body or missing keys to any endpoint. If you get a 500 with a Python traceback, validation is missing.

**Confidence:** HIGH -- directly observed in codebase, all six print endpoints affected.

---

### Pitfall 8: No Authentication Allows Any Network Device to Print

**What goes wrong:** The server binds to `0.0.0.0` and has no authentication. The mDNS registration actively advertises the service on the network. Any device on the same WiFi network can discover and use the printer -- sending arbitrary content, wasting paper, or printing offensive material.

**Why it happens:** The server was built for convenience on a trusted home network. Authentication was deferred. The mDNS broadcast makes the server easy to find, which is a feature for the owner but also for anyone else on the network.

**Consequences:** On shared networks (the Pi is sometimes on ETH Zurich's eduroam), anyone can send print jobs. Paper waste is the mild case; printing offensive content or sending huge payloads to crash the service is the severe case.

**Prevention:**
1. Add a simple API key check via `X-Print-Key` header, validated with a decorator applied to all print endpoints.
2. Store the key in an environment variable or a `.env` file (not in version-controlled `config.yaml`).
3. Exempt the `/health` and `/` endpoints from auth (monitoring and web UI landing page).
4. The web UI should prompt for the key and store it in a cookie or localStorage.

**Detection:** Run `curl -X POST http://<pi-ip>:9100/print/message -d '{"text":"test"}'` from any device on the network. If it prints, auth is missing.

**Confidence:** HIGH -- directly observed in codebase, documented in CONCERNS.md.

---

### Pitfall 9: Thermal Printhead Overheating on Large Raster Images

**What goes wrong:** Printing large images (full-page photos, multiple image slices in sequence, or the portrait pipeline's multi-zoom output) causes the thermal printhead to overheat. The printer either produces smeared/faded output, pauses mid-print, or in extreme cases damages the printhead. The image slicer is particularly dangerous -- it can queue multiple large raster prints back-to-back with no cooldown.

**Why it happens:** Thermal printers generate heat to darken thermal paper. Large raster images require continuous heating across the full 576-pixel width for hundreds of rows. Consumer-grade printers (like the one on this Pi) have thinner printheads that dissipate heat slowly. The ESC/POS protocol has no built-in "wait for cooldown" mechanism visible to the host.

**Consequences:** Degraded print quality (fading halfway through the image). Printer may pause or error. Repeated overheating shortens printhead life. The portrait pipeline printing 4 zoom levels in succession is a worst case.

**Prevention:**
1. Add a configurable delay between sequential large print jobs (e.g., `time.sleep(2)` between portrait zoom levels).
2. For the image slicer, insert a pause between slices.
3. Document maximum recommended continuous print area in the config.
4. If possible, use lower thermal density settings for large images (the printer's energy-per-dot setting).

**Detection:** Print quality degrades (lighter/faded) toward the bottom of large images. Printer pauses mid-print.

**Confidence:** MEDIUM -- general thermal printer knowledge confirmed by manufacturer troubleshooting guides (ZYWELL, Rongta); specific behavior depends on this printer model.

---

### Pitfall 10: Halftone Dithering Pure-Python Pixel Loop Blocks Server

**What goes wrong:** The halftone and Bayer dithering modes iterate every pixel in nested Python loops. For a typical 576x800 pixel image, this processes ~460,000 pixels in pure Python. On the Pi 3's ARM Cortex-A53, this takes several seconds. During this time, the print lock is held and the Flask server blocks all other requests (including `/health` checks).

**Why it happens:** The dithering was written for correctness on a dev machine, not optimized for the Pi's limited CPU. Floyd-Steinberg dithering uses PIL's built-in C implementation and is fast. Halftone and Bayer are custom pure-Python implementations.

**Consequences:** Server appears unresponsive during image processing. Health checks fail. If a monitoring system is watching `/health`, it may falsely report the service as down. Subsequent print requests queue behind the lock.

**Prevention:**
1. Use Floyd-Steinberg as the default mode (already the default -- keep it that way).
2. If halftone/Bayer are needed, offload to NumPy vectorized operations (reshape + threshold for Bayer, reshape + mean + circle draw for halftone).
3. Add a processing timeout to prevent indefinite blocking.
4. Consider processing images outside the print lock -- only acquire the lock for the actual USB send.

**Detection:** Image print requests take > 5 seconds on the Pi. Health endpoint returns timeout during image processing. `journalctl` shows long gaps between "print started" and "print completed" log entries.

**Confidence:** MEDIUM -- performance concern is real (confirmed in CONCERNS.md), but whether it's actually blocking in practice depends on image size and usage patterns.

## Minor Pitfalls

### Pitfall 11: `left_right` Column Alignment Breaks with Non-ASCII Characters

**What goes wrong:** The `left_right()` method in `Formatter` uses `len()` to calculate spacing, which counts Unicode code points, not display columns. CJK characters (which occupy 2 display columns), emojis (2 columns), and combining characters (0 columns) cause misalignment. Column text that should be right-aligned shifts left or right.

**Prevention:** Replace `len()` with a display-width calculation using `unicodedata.east_asian_width()` or the `wcwidth` library. Only needed if multilingual content is a use case.

**Confidence:** HIGH -- directly observed in code.

---

### Pitfall 12: Helvetica Font Style Fails Silently on Pi

**What goes wrong:** The `helvetica` font style references `/System/Library/Fonts/HelveticaNeue.ttc` which only exists on macOS. On the Pi, `_resolve_font_path()` falls back to a default font (or crashes if the fallback also fails), producing unexpected output with no clear error message.

**Prevention:** Add a font availability check at server startup that warns about unavailable font styles in the log. Or remove the `helvetica` style definition on the Pi's config and only keep it on macOS.

**Confidence:** HIGH -- already documented in MEMORY.md as a known issue.

---

### Pitfall 13: Inline Markdown Regex Fails on Nested Patterns

**What goes wrong:** The `_INLINE_RE` regex processes bold, italic, strikethrough, and code in a single pass. Nested patterns like `**bold *italic***` or `*italic with **bold** inside*` produce unexpected matches. The italic pattern `\*(.+?)\*` can match inside `**bold**` delimiters.

**Prevention:** Process inline patterns in a defined priority order (bold before italic) with proper boundary assertions. Or switch to a tokenizer-based approach for inline parsing. Low priority unless complex markdown is being submitted.

**Confidence:** MEDIUM -- regex edge cases are theoretical but documented in CONCERNS.md.

---

### Pitfall 14: Temp Files Persist After Process Kill

**What goes wrong:** Image upload endpoints create temp files with `delete=False` and clean them up in `finally` blocks. If the process is killed with SIGKILL (systemd escalation after `TimeoutStopSec`), `finally` blocks don't execute and temp files persist in `/tmp`.

**Prevention:** Acceptable for a low-traffic print server. The OS's `/tmp` cleanup handles stragglers. If concerned, add a startup routine that cleans old temp files matching the naming pattern.

**Confidence:** HIGH -- code pattern confirmed, but impact is minimal.

---

### Pitfall 15: `_raw()` Private API Usage in python-escpos

**What goes wrong:** The server and Formatter use `printer._raw()` to send raw ESC/POS bytes. This is a private/internal API (underscore prefix) in python-escpos that could change or be removed in a future version without notice.

**Prevention:** Wrap all `_raw()` calls in a single Formatter method (e.g., `Formatter.raw_command(bytes)`) to isolate the private API usage to one location. Pin the python-escpos version in requirements.txt (already done).

**Confidence:** HIGH -- `_raw()` is used in both `print_server.py` and potentially in templates. Pinning mitigates the version risk.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Input validation | Testing only happy path; forgetting `None` from invalid JSON | Test with empty body, missing Content-Type, missing keys, wrong types |
| API authentication | Implementing auth but forgetting to protect file upload endpoints | Apply auth decorator to ALL endpoints including `/print/image`, `/portrait/*` |
| Request size limits | `MAX_CONTENT_LENGTH` not applying to `get_json(force=True)` in older Flask | Verify with actual oversized payload test; check Flask/Werkzeug version |
| Graceful shutdown | Signal handler that does too much work and gets killed by `TimeoutStopSec` | Keep handler minimal: close printer, unregister mDNS, exit. No logging or network calls |
| Formatter state safety | Adding `try/finally` but missing one method; or resetting to wrong defaults | Systematic audit: every method that calls `self.p.set()` needs a `finally` block |
| SD card protection | Moving `/var/log` to tmpfs but losing critical error logs on reboot | Use journald with `Storage=volatile` + `SystemMaxUse=20M` instead of raw tmpfs; or use the copy-on-shutdown approach |
| Code deduplication | Extracting shared functions but breaking import order (circular imports) | Keep utility functions in a new `utils.py` that imports nothing from the project |
| Unit tests | Writing tests that depend on hardware (USB printer) | Use the existing `Dummy` printer from python-escpos; test rendering logic separately from printing |

## Sources

- [Flask MAX_CONTENT_LENGTH issue #1200](https://github.com/pallets/flask/issues/1200) -- JSON payload bypass
- [Flask Security Best Practices 2025](https://hub.corgea.com/articles/flask-security-best-practices-2025) -- general Flask hardening
- [Pi Reliability: Reduce writes to your SD card (dzombak.com)](https://www.dzombak.com/blog/2024/04/pi-reliability-reduce-writes-to-your-sd-card/) -- SD card wear reduction
- [Raspberry Pi and the Story of SD Card Corruption (Hackaday)](https://hackaday.com/2022/03/09/raspberry-pi-and-the-story-of-sd-card-corruption/) -- corruption causes
- [pyusb Resource Busy issue #76](https://github.com/pyusb/pyusb/issues/76) -- kernel driver conflict
- [pyusb Resource Busy issue #391](https://github.com/pyusb/pyusb/issues/391) -- reconnection handling
- [python-escpos: Losing prints on power down, issue #253](https://github.com/python-escpos/python-escpos/issues/253) -- print reliability
- [python-escpos: Device not found after reboot, issue #437](https://github.com/python-escpos/python-escpos/issues/437) -- USB detection
- [Flask SIGTERM handling issue (Google Cloud)](https://github.com/GoogleCloudPlatform/cloud-code-samples/issues/385) -- Flask dev server signal issues
- [ZYWELL: Common Issues with Thermal Printers](https://www.zywell.net/common-lssues-with-thermal-printers-and-their-solutions.html) -- overheating
- [Kitchen printer garbles tickets (whizz-tech)](https://whizz-tech.com/support/printers/kitchen-printer-garbles-tickets/) -- ESC/POS buffer/heat issues
- [Flask-Limiter documentation](https://flask-limiter.readthedocs.io/) -- rate limiting
- [Flask API Key Auth (teclado.com)](https://blog.teclado.com/api-key-authentication-with-flask/) -- simple auth pattern
- Project codebase: `print_server.py`, `printer_core.py`, `portrait_pipeline.py`, `config.yaml`
- Project docs: `.planning/codebase/CONCERNS.md`, `CLAUDE.md`, `MEMORY.md`

---

*Concerns audit: 2026-03-08*
