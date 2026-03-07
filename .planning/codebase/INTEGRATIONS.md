# External Integrations

**Analysis Date:** 2026-03-07

## APIs & External Services

**AI / LLM (Portrait Pipeline):**
- OpenRouter API - Photo selection (best portrait picker) and style transfer key forwarding
  - SDK/Client: `requests` library, direct HTTP POST to `https://openrouter.ai/api/v1/chat/completions`
  - Auth: `OPENROUTER_API_KEY` env var (name configurable via `config.yaml` key `portrait.openrouter_api_key_env`)
  - Model: `google/gemini-3.1-flash-image-preview` (configurable via `portrait.selection_model`)
  - Usage: `portrait_pipeline.py:select_best_photo()` sends base64-encoded images with a vision prompt asking the model to pick the best portrait
  - Timeout: 60 seconds

**n8n Workflow Automation:**
- n8n webhook - Style transfer (portrait-to-statue transformation)
  - Endpoint: `https://n8n.baufer.beauty/webhook/portrait-statue` (configurable via `portrait.n8n_webhook_url`)
  - Protocol: HTTP POST with JSON body `{"image": "<base64>", "prompt": "<style_prompt>"}`
  - Auth: `X-OpenRouter-Key` header passes the OpenRouter API key to n8n for downstream model calls
  - Response: JSON with `{"image": "<base64_png>"}` or `{"error": "..."}`
  - Implementation: `portrait_pipeline.py:transform_to_statue()`
  - Timeout: 180 seconds (image generation is slow)

## Data Storage

**Databases:**
- None. No database of any kind.

**File Storage:**
- Local filesystem only
- Font files stored in `fonts/` directory
- No persistent data storage; all print jobs are fire-and-forget
- Preview images saved to working directory when using `--dummy` mode

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- None. The HTTP server has no authentication.
- All endpoints are open -- any device on the network can POST print jobs.
- CORS is fully permissive (flask-cors with default `CORS(app)` allows all origins).

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, no error reporting service.

**Logs:**
- `print()` statements to stdout only
- Log prefix convention: `[OK]`, `[DUMMY]`, `[INFO]`, `[WARN]`, `[PORTRAIT]`
- No structured logging, no log files, no log rotation

## CI/CD & Deployment

**Hosting:**
- Self-hosted on Raspberry Pi 3 (Debian Bookworm, aarch64)
- Connected via USB to ESC/POS thermal printer
- WiFi on eduroam (ETH Zurich, `10.5.x.x` IP range)

**CI Pipeline:**
- None. No automated testing, no CI/CD.

**Deployment:**
- Manual: `git pull` + `pip install -r requirements.txt` on the Pi
- systemd service for auto-start (`print_server.py`)

## Environment Configuration

**Required env vars:**
- `OPENROUTER_API_KEY` - Only required for portrait pipeline features. All other features work without any env vars.

**Optional config:**
- `config.yaml` - All runtime configuration. No secrets in this file (API keys are referenced by env var name, not value).

## Hardware Integration

**USB Thermal Printer:**
- Protocol: ESC/POS via `python-escpos` library
- Connection: USB (vendor `0x1fc9`, product `0x2016`) or TCP network
- Implementation: `printer_core.py:connect()` creates `Usb()`, `Network()`, or `Dummy()` printer instance
- Paper: 80mm thermal (48 chars / 576px @ 203 DPI)
- Requires root on Linux (or udev rule) for USB access

**Bonjour/mDNS Service Discovery:**
- Library: `zeroconf` 0.146.0
- Service type: `_http._tcp.local.`
- Service name: `POS Thermal Printer._http._tcp.local.`
- Purpose: Allows iPads on the same network to auto-discover the print server
- Implementation: `print_server.py:register_mdns()`
- Graceful fallback: logs warning and continues if registration fails

## Webhooks & Callbacks

**Incoming (this server receives):**
- `POST /print/receipt` - Print receipt from JSON
- `POST /print/message` - Print text message
- `POST /print/label` - Print label
- `POST /print/list` - Print two-column list
- `POST /print/dictionary` - Print dictionary art entry
- `POST /print/image` - Print dithered image (multipart/form-data)
- `POST /print/markdown` - Print rendered markdown
- `POST /portrait/capture` - Full portrait pipeline (multipart/form-data, multiple files)
- `POST /portrait/transform` - Style transfer only, returns PNG
- `GET /health` - Health check
- `GET /` - Web UI (`templates/index.html`)

**Outgoing (this server sends):**
- `POST https://openrouter.ai/api/v1/chat/completions` - Vision model for photo selection
- `POST https://n8n.baufer.beauty/webhook/portrait-statue` - n8n workflow for style transfer

## Face Detection (Local ML)

**MediaPipe FaceMesh:**
- Library: `mediapipe` (imported lazily, not in `requirements.txt`)
- Purpose: Detect facial landmarks for computing zoom crop regions in portrait pipeline
- Implementation: `portrait_pipeline.py:detect_face_landmarks()`
- Runs locally, no network calls
- Returns 10 key landmark points (eyes, nose, chin, forehead)

---

*Integration audit: 2026-03-07*
