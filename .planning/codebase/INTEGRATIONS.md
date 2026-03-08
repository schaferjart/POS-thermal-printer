# External Integrations

**Analysis Date:** 2026-03-08

## APIs & External Services

**AI / LLM (Portrait Pipeline):**
- OpenRouter API - Photo selection (picks best portrait from multiple candidates)
  - SDK/Client: `requests` HTTP library (direct REST calls)
  - Endpoint: `https://openrouter.ai/api/v1/chat/completions`
  - Auth: Bearer token via `OPENROUTER_API_KEY` env var
  - Model: `google/gemini-3.1-flash-image-preview` (configurable in `config.yaml` at `portrait.selection_model`)
  - Implementation: `portrait_pipeline.py` function `select_best_photo()` (lines 28-83)
  - Sends base64-encoded images as multimodal content, receives a single number response

- n8n Webhook - Style transfer (portrait to sculptural wax aesthetic)
  - SDK/Client: `requests` HTTP library (direct REST calls)
  - Endpoint: configurable via `config.yaml` at `portrait.n8n_webhook_url`
  - Current value: `https://n8n.baufer.beauty/webhook/portrait-statue`
  - Auth: API key passed via `X-OpenRouter-Key` header (same `OPENROUTER_API_KEY`)
  - Implementation: `portrait_pipeline.py` function `transform_to_statue()` (lines 88-145)
  - Sends: JSON with `image` (base64 PNG) and `prompt` (from config)
  - Receives: JSON with `image` (base64 transformed result)
  - Timeout: 180 seconds (style transfer is slow)

## Data Storage

**Databases:**
- None - No database used. All data is passed in via JSON payloads or files.

**File Storage:**
- Local filesystem only
  - `config.yaml` - Application configuration
  - `fonts/` - Font files for text rendering
  - `templates/` - Flask HTML templates
  - Temporary files via `tempfile.NamedTemporaryFile` for uploaded images (cleaned up after use)
  - Preview PNGs saved to disk in dummy mode (`preview_*.png`, `portrait_*.png`)

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- None - No authentication on HTTP endpoints. The server is designed for trusted local network use only.
- API keys for external services stored in environment variables (never in config files).

## Monitoring & Observability

**Error Tracking:**
- None - No external error tracking service

**Logs:**
- Python `logging` module in `print_server.py` (logger per module)
- `print()` statements for status messages throughout the codebase
- systemd journal on Pi (`journalctl -u pos-printer -f`)
- macOS: `/tmp/pos-printer.log` (via launchd stdout/stderr redirect)

## CI/CD & Deployment

**Hosting:**
- Self-hosted on Raspberry Pi 3 (Debian Trixie, aarch64)
- Local network only - no cloud hosting, no public endpoints
- IP: `192.168.1.65` (home WiFi DHCP)

**CI Pipeline:**
- None - No CI/CD pipeline configured
- Manual deployment via `git pull origin main && sudo systemctl restart pos-printer`
- `setup.sh` handles initial provisioning (system deps, venv, systemd service)

**Repository:**
- GitHub: `https://github.com/schaferjart/POS-thermal-printer.git`

## Network Discovery

**mDNS/Bonjour:**
- Zeroconf service registration for automatic discovery by iPads/devices on local network
- Service type: `_http._tcp.local.`
- Service name: `POS Thermal Printer._http._tcp.local.`
- Implementation: `print_server.py` function `register_mdns()` (lines 313-338)
- Properties advertised: `path=/`, `type=thermal-printer`
- Cleanup: auto-unregistered via `atexit` hook

## USB Hardware

**Thermal Printer:**
- Connection: USB (primary) or Network (configurable)
- USB IDs: vendor `0x1fc9`, product `0x2016`
- Protocol: ESC/POS via `python-escpos` library
- Access: requires udev rule on Linux, `libusb` on macOS
- Thread safety: `threading.Lock()` (`_print_lock`) serializes all USB access in server mode
- Reconnection: `with_retry()` wrapper attempts reconnect on print failure

## Environment Configuration

**Required env vars (portrait pipeline only):**
- `OPENROUTER_API_KEY` - API key for OpenRouter (used for both photo selection and n8n webhook auth)

**No env vars required for basic printing** - all config in `config.yaml`.

**Secrets location:**
- `.env` files (gitignored)
- Environment variables on the Pi (set in shell or systemd override)

## Webhooks & Callbacks

**Incoming (this server receives):**
- `POST /print/receipt` - Print a receipt from JSON
- `POST /print/message` - Print a text message
- `POST /print/label` - Print a label
- `POST /print/list` - Print a two-column list
- `POST /print/dictionary` - Print a dictionary art entry
- `POST /print/image` - Print an image (multipart/form-data)
- `POST /print/markdown` - Print markdown text
- `POST /portrait/capture` - Full portrait pipeline (multipart/form-data, multiple files)
- `POST /portrait/transform` - Style transfer only, returns PNG
- `GET /health` - Health check
- `GET /` - Web UI (`templates/index.html`)

**Outgoing (this server sends):**
- `POST https://openrouter.ai/api/v1/chat/completions` - AI photo selection
- `POST https://n8n.baufer.beauty/webhook/portrait-statue` - Style transfer via n8n

---

*Integration audit: 2026-03-08*
