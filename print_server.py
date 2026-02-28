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

import os
import sys
import socket
import atexit
import argparse
import tempfile
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from zeroconf import ServiceInfo, Zeroconf
from printer_core import load_config, connect, Formatter
import templates
from image_printer import process_image

app = Flask(__name__)
CORS(app)

# Globals set at startup
_config = None
_printer = None
_dummy = False
_zeroconf = None


def get_formatter():
    global _printer
    width = _config.get("printer", {}).get("paper_width", 48)
    return Formatter(_printer, width)


def reconnect():
    """Reconnect to the printer after a failed print."""
    global _printer
    _printer = connect(_config, dummy=_dummy)
    width = _config.get("printer", {}).get("paper_width", 48)
    return Formatter(_printer, width)


def with_retry(fn):
    """Run a print function, reconnecting once on failure."""
    try:
        fn(get_formatter())
    except Exception:
        fn(reconnect())


@app.route("/print/receipt", methods=["POST"])
def print_receipt():
    data = request.get_json(force=True)
    with_retry(lambda fmt: templates.receipt(fmt, data, _config))
    return jsonify({"status": "ok", "template": "receipt"})


@app.route("/print/message", methods=["POST"])
def print_message():
    data = request.get_json(force=True)
    with_retry(lambda fmt: templates.simple_message(fmt, data["text"], data.get("title")))
    return jsonify({"status": "ok", "template": "message"})


@app.route("/print/label", methods=["POST"])
def print_label():
    data = request.get_json(force=True)
    with_retry(lambda fmt: templates.label(fmt, data["heading"], data.get("lines", [])))
    return jsonify({"status": "ok", "template": "label"})


@app.route("/print/list", methods=["POST"])
def print_list():
    data = request.get_json(force=True)
    rows = [tuple(r) for r in data["rows"]]
    with_retry(lambda fmt: templates.two_column_list(fmt, data["title"], rows))
    return jsonify({"status": "ok", "template": "list"})


@app.route("/print/dictionary", methods=["POST"])
def print_dictionary():
    data = request.get_json(force=True)
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
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "Empty filename"}), 400

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

        img = process_image(
            tmp.name, _config,
            mode=mode,
            dot_size=int(dot_size) if dot_size else None,
            contrast=float(contrast) if contrast else None,
            brightness=float(brightness) if brightness else None,
            sharpness=float(sharpness) if sharpness else None,
        )

        def do_print(fmt):
            fmt.p.image(img)
            fmt.feed()
            fmt.cut()

        with_retry(do_print)

        return jsonify({"status": "ok", "template": "image", "mode": mode or "floyd"})
    finally:
        os.unlink(tmp.name)


@app.route("/print/markdown", methods=["POST"])
def print_markdown():
    data = request.get_json(force=True)
    with_retry(lambda fmt: templates.markdown(fmt, data["text"], _config, show_date=data.get("show_date", True), style=data.get("style", "dictionary")))
    return jsonify({"status": "ok", "template": "markdown"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running", "dummy": _dummy})


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


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


def main():
    global _config, _printer, _dummy

    parser = argparse.ArgumentParser(description="Thermal printer HTTP server")
    parser.add_argument("--dummy", action="store_true", help="Run without real printer")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    args = parser.parse_args()

    _config = load_config(args.config)
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

    print(f"[INFO] Server listening on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
