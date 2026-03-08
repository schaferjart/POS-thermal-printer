"""
HTTP print server — receives JSON print jobs and sends them to the thermal printer.

Usage:
    python print_server.py                  # start with real printer
    python print_server.py --dummy          # start in test mode (no printer needed)

Send jobs via HTTP POST:

    curl -X POST http://localhost:9100/print/receipt \
        -H "Content-Type: application/json" \
        -d '{"items":[{"name":"Coffee","qty":2,"price":5.0}]}'

    curl -X POST http://localhost:9100/print/message \
        -H "Content-Type: application/json" \
        -d '{"text":"Hello world!","title":"NOTICE"}'

    curl -X POST http://localhost:9100/print/label \
        -H "Content-Type: application/json" \
        -d '{"heading":"FRAGILE","lines":["Handle with care","This side up"]}'

    curl -X POST http://localhost:9100/print/list \
        -H "Content-Type: application/json" \
        -d '{"title":"Price List","rows":[["Coffee","3.50"],["Tea","2.80"]]}'

    curl -X POST http://localhost:9100/print/dictionary \
        -H "Content-Type: application/json" \
        -d '{"word":"Ephemeral","definition":"Lasting for a very short time.","citations":["All fame is ephemeral."]}'
"""

import io
import os
import sys
import time
import hmac
import signal
import socket
import atexit
import argparse
import tempfile
import threading
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from zeroconf import ServiceInfo, Zeroconf
from printer_core import load_config, connect, Formatter, validate_config
import templates
from image_printer import process_image
try:
    from portrait_pipeline import run_pipeline, transform_to_statue
    _has_portrait = True
except ImportError:
    _has_portrait = False

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

# Globals set at startup
_config = None
_printer = None
_dummy = False
_zeroconf = None
_print_lock = threading.Lock()
_server_start_time = None
_last_print_time = None

_PUBLIC_ENDPOINTS = frozenset({"health", "index", "static"})

logger = logging.getLogger(__name__)


def get_formatter():
    global _printer
    width = _config.get("printer", {}).get("paper_width", 48)
    return Formatter(_printer, width)


def reconnect():
    """Reconnect to the printer after a failed print."""
    global _printer
    try:
        _printer.close()
    except Exception:
        pass
    time.sleep(0.5)
    _printer = connect(_config, dummy=_dummy)
    width = _config.get("printer", {}).get("paper_width", 48)
    return Formatter(_printer, width)


def _require_fields(data, *fields):
    """Validate JSON body has required fields.
    Returns (data, None) on success, or (None, (error_msg, field_name)) on failure."""
    if data is None:
        return None, ("Invalid or missing JSON body", None)
    if not isinstance(data, dict):
        return None, ("Request body must be a JSON object", None)
    for field in fields:
        if field not in data:
            return None, (f"Missing required field '{field}'", field)
    return data, None


def error_response(message, field=None, status=400):
    """Return a consistent JSON error response."""
    body = {"error": message}
    if field is not None:
        body["field"] = field
    return jsonify(body), status


@app.before_request
def check_api_key():
    """Reject requests without a valid API key when api_key is configured."""
    api_key = _config.get("server", {}).get("api_key")
    if not api_key:
        return
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    provided = request.headers.get("X-Print-Key", "")
    if not hmac.compare_digest(provided, api_key):
        return error_response("Invalid or missing API key", status=401)


def with_retry(fn):
    """Run a print function with mutex lock and reconnect on failure."""
    global _last_print_time
    with _print_lock:
        try:
            fmt = get_formatter()
            fmt.p.hw("INIT")  # ESC@ reset printer state
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


@app.route("/print/receipt", methods=["POST"])
def print_receipt():
    data = request.get_json(force=True, silent=True)
    data, err = _require_fields(data, "items")
    if err:
        return error_response(err[0], err[1])
    with_retry(lambda fmt: templates.receipt(fmt, data, _config))
    return jsonify({"status": "ok", "template": "receipt"})


@app.route("/print/message", methods=["POST"])
def print_message():
    data = request.get_json(force=True, silent=True)
    data, err = _require_fields(data, "text")
    if err:
        return error_response(err[0], err[1])
    with_retry(lambda fmt: templates.simple_message(fmt, data["text"], data.get("title")))
    return jsonify({"status": "ok", "template": "message"})


@app.route("/print/label", methods=["POST"])
def print_label():
    data = request.get_json(force=True, silent=True)
    data, err = _require_fields(data, "heading")
    if err:
        return error_response(err[0], err[1])
    with_retry(lambda fmt: templates.label(fmt, data["heading"], data.get("lines", [])))
    return jsonify({"status": "ok", "template": "label"})


@app.route("/print/list", methods=["POST"])
def print_list():
    data = request.get_json(force=True, silent=True)
    data, err = _require_fields(data, "title", "rows")
    if err:
        return error_response(err[0], err[1])
    rows = [tuple(r) for r in data["rows"]]
    with_retry(lambda fmt: templates.two_column_list(fmt, data["title"], rows))
    return jsonify({"status": "ok", "template": "list"})


@app.route("/print/dictionary", methods=["POST"])
def print_dictionary():
    data = request.get_json(force=True, silent=True)
    data, err = _require_fields(data, "word", "definition")
    if err:
        return error_response(err[0], err[1])
    with_retry(lambda fmt: templates.dictionary_entry(fmt, data, _config))
    return jsonify({"status": "ok", "template": "dictionary"})


@app.route("/print/image", methods=["POST"])
def print_image():
    """
    Print an image with halftone/dithering.

    Accepts multipart/form-data with:
        file: image file (required)
        mode: halftone | floyd | bayer (optional)
        dot_size: int (optional)
        contrast: float (optional)
        brightness: float (optional)
        sharpness: float (optional)
        blur: float (optional)
    """
    if "file" not in request.files:
        return error_response("No file uploaded", "file")
    uploaded = request.files["file"]
    if not uploaded.filename:
        return error_response("Empty filename", "file")

    suffix = os.path.splitext(uploaded.filename)[1] or ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        uploaded.save(tmp)
        tmp.close()

        mode = request.form.get("mode")
        dot_size = request.form.get("dot_size")
        contrast = request.form.get("contrast")
        brightness = request.form.get("brightness")
        sharpness = request.form.get("sharpness")
        blur = request.form.get("blur")

        img = process_image(
            tmp.name, _config,
            mode=mode,
            dot_size=int(dot_size) if dot_size else None,
            contrast=float(contrast) if contrast else None,
            brightness=float(brightness) if brightness else None,
            sharpness=float(sharpness) if sharpness else None,
            blur=float(blur) if blur else None,
        )

        mode_name = {"floyd": "FLOYD-STEINBERG", "halftone": "HALFTONE", "bayer": "BAYER 8x8"}.get(mode or "floyd", mode or "floyd")
        blur_val = blur
        label = f"{mode_name} + BLUR {blur_val}" if blur_val else mode_name

        def do_print(fmt):
            fmt.font_b_text(label)
            fmt.blank()
            fmt.p.image(img)
            fmt.feed()
            fmt.cut()

        with_retry(do_print)

        return jsonify({"status": "ok", "template": "image", "mode": mode or "floyd"})
    finally:
        os.unlink(tmp.name)


@app.route("/print/markdown", methods=["POST"])
def print_markdown():
    data = request.get_json(force=True, silent=True)
    data, err = _require_fields(data, "text")
    if err:
        return error_response(err[0], err[1])
    with_retry(lambda fmt: templates.markdown(fmt, data["text"], _config, show_date=data.get("show_date", True), style=data.get("style", "dictionary")))
    return jsonify({"status": "ok", "template": "markdown"})


@app.route("/portrait/capture", methods=["POST"])
def portrait_capture():
    if not _has_portrait:
        return jsonify({"error": "Portrait pipeline unavailable — install numpy and mediapipe"}), 501
    """
    Receive one or more photos, run the full portrait pipeline
    (select best → style transfer → print at multiple zoom levels).

    Accepts multipart/form-data with one or more 'file' fields.
    """
    files = request.files.getlist("file")
    if not files:
        return error_response("No files uploaded", "file")

    tmp_paths = []
    try:
        for uploaded in files:
            if not uploaded.filename:
                continue
            suffix = os.path.splitext(uploaded.filename)[1] or ".jpg"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            uploaded.save(tmp)
            tmp.close()
            tmp_paths.append(tmp.name)

        if not tmp_paths:
            return error_response("No valid files", "file")

        skip_selection = request.form.get("skip_selection", "").lower() in ("1", "true")
        blur = request.form.get("blur")
        mode = request.form.get("mode")

        selected, _ = run_pipeline(
            tmp_paths, _config, _printer,
            dummy=_dummy,
            skip_selection=skip_selection,
            blur=float(blur) if blur else None,
            dither_mode=mode,
        )

        return jsonify({
            "status": "ok",
            "template": "portrait",
            "photos_received": len(tmp_paths),
            "selected": os.path.basename(selected),
        })
    finally:
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass


@app.route("/portrait/transform", methods=["POST"])
def portrait_transform():
    if not _has_portrait:
        return jsonify({"error": "Portrait pipeline unavailable — install numpy and mediapipe"}), 501
    """
    Transform a single image to Roman statue aesthetic (no printing).
    Returns the transformed image as PNG.

    Accepts multipart/form-data with a 'file' field.
    """
    if "file" not in request.files:
        return error_response("No file uploaded", "file")
    uploaded = request.files["file"]
    if not uploaded.filename:
        return error_response("Empty filename", "file")

    suffix = os.path.splitext(uploaded.filename)[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        uploaded.save(tmp)
        tmp.close()

        img = transform_to_statue(tmp.name, _config)

        # Return as PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        from flask import send_file
        return send_file(buf, mimetype="image/png", download_name="portrait_statue.png")
    finally:
        os.unlink(tmp.name)


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


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.errorhandler(Exception)
def handle_error(e):
    """Return JSON error responses instead of HTML."""
    code = getattr(e, "code", 500)
    logger.error("Request error: %s", e)
    return jsonify({"error": str(e)}), code


def register_mdns(port):
    """Register the print server as a Bonjour/mDNS service for iPad discovery."""
    global _zeroconf
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        info = ServiceInfo(
            "_http._tcp.local.",
            f"POS Thermal Printer._http._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=port,
            properties={"path": "/", "type": "thermal-printer"},
            server=f"{hostname}.local.",
        )
        _zeroconf = Zeroconf()
        _zeroconf.register_service(info, allow_name_change=True)
        print(f"[INFO] Bonjour: registered '{info.name}' on {local_ip}:{port}")

        def cleanup():
            print("[INFO] Bonjour: unregistering service")
            _zeroconf.unregister_service(info)
            _zeroconf.close()

        atexit.register(cleanup)
    except Exception as e:
        print(f"[WARN] Bonjour registration failed: {e} — server will still work via IP")


def graceful_shutdown(signum, frame):
    """Clean up mDNS and printer connection on SIGTERM/SIGINT."""
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


def main():
    global _config, _printer, _dummy, _server_start_time

    parser = argparse.ArgumentParser(description="Thermal printer HTTP server")
    parser.add_argument("--dummy", action="store_true", help="Run without real printer")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    args = parser.parse_args()

    _config = load_config(args.config)
    validate_config(_config)  # fail fast if config incomplete
    _server_start_time = time.time()
    _dummy = args.dummy

    if _dummy:
        print("[INFO] Running in DUMMY mode — no printer connected")
    else:
        print("[INFO] Connecting to printer...")

    _printer = connect(_config, dummy=_dummy)
    print("[INFO] Printer ready")

    srv = _config.get("server", {})
    host = srv.get("host", "0.0.0.0")
    port = srv.get("port", 9100)

    register_mdns(port)

    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    print(f"[INFO] Server listening on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
