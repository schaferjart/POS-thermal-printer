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

import sys
import socket
import atexit
import argparse
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from zeroconf import ServiceInfo, Zeroconf
from printer_core import load_config, connect, Formatter
import templates

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
    # Reconnect if printer was closed or errored
    try:
        return Formatter(_printer, width)
    except Exception:
        _printer = connect(_config, dummy=_dummy)
        return Formatter(_printer, width)


@app.route("/print/receipt", methods=["POST"])
def print_receipt():
    data = request.get_json(force=True)
    fmt = get_formatter()
    templates.receipt(fmt, data, _config)
    return jsonify({"status": "ok", "template": "receipt"})


@app.route("/print/message", methods=["POST"])
def print_message():
    data = request.get_json(force=True)
    fmt = get_formatter()
    templates.simple_message(fmt, data["text"], data.get("title"))
    return jsonify({"status": "ok", "template": "message"})


@app.route("/print/label", methods=["POST"])
def print_label():
    data = request.get_json(force=True)
    fmt = get_formatter()
    templates.label(fmt, data["heading"], data.get("lines", []))
    return jsonify({"status": "ok", "template": "label"})


@app.route("/print/list", methods=["POST"])
def print_list():
    data = request.get_json(force=True)
    fmt = get_formatter()
    rows = [tuple(r) for r in data["rows"]]
    templates.two_column_list(fmt, data["title"], rows)
    return jsonify({"status": "ok", "template": "list"})


@app.route("/print/dictionary", methods=["POST"])
def print_dictionary():
    data = request.get_json(force=True)
    fmt = get_formatter()
    templates.dictionary_entry(fmt, data, _config)
    return jsonify({"status": "ok", "template": "dictionary"})


@app.route("/print/markdown", methods=["POST"])
def print_markdown():
    data = request.get_json(force=True)
    fmt = get_formatter()
    templates.markdown(fmt, data["text"], _config, show_date=data.get("show_date", True), style=data.get("style", "dictionary"))
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
    _zeroconf.register_service(info)
    print(f"[INFO] Bonjour: registered 'POS Thermal Printer' on {local_ip}:{port}")

    def cleanup():
        print("[INFO] Bonjour: unregistering service")
        _zeroconf.unregister_service(info)
        _zeroconf.close()

    atexit.register(cleanup)


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
