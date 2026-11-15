#!/usr/bin/env python3
"""The printer service.

- Serves the print page and a small local API on :9100.
- Lets go of port 80 while comitup's WiFi-setup hotspot is up, and prints
  a slip when the WiFi changes (see "network").
- Pulls jobs from the cloud (printer.claim_jobs) every few seconds.
- Never opens USB: every print is rendered to ESC/POS bytes with
  python-escpos and handed to CUPS with `lp -d <queue> -o raw`.

Env overrides (for running on a Mac): PRINTER_STATE_DIR, PRINTER_DRY_RUN=1
(writes PNG previews to <state>/out instead of calling lp), PRINTER_NO_CLOUD=1.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import qrcode
import yaml
from escpos.printer import Dummy
from flask import Flask, jsonify, request, send_file
from PIL import Image, ImageFont
from werkzeug.serving import make_server

import jobs

HERE = Path(__file__).resolve().parent
CFG = yaml.safe_load((HERE / "config.yaml").read_text())
QUEUE = CFG["cups_queue"]
AIRPRINT = "Thermal printer 80mm"        # the name phones and Macs show
PAPER = CFG.get("paper_px", 576)
STATE = Path(os.environ.get("PRINTER_STATE_DIR", CFG["state_dir"]))
FONTS = STATE / "fonts"            # uploaded fonts; survive updates
CFG["_fonts_dir"] = str(FONTS)
DRY = bool(os.environ.get("PRINTER_DRY_RUN"))
# The cloud lives outside the repo: /etc/printer/printer.env -> systemd env.
CLOUD_URL = os.environ.get("PRINTER_CLOUD_URL", "").rstrip("/")
CLOUD_KEY = os.environ.get("PRINTER_CLOUD_KEY", "")
CLOUD = bool(CLOUD_URL and CLOUD_KEY) and not os.environ.get("PRINTER_NO_CLOUD")

log = logging.getLogger("printerd")
_print_lock = threading.Lock()   # one print at a time: page and cloud share the paper
status = {"cloud": "starting", "paired": None, "last_poll": None, "last_error": None,
          "printed": 0, "failed": 0}


# ── output: ESC/POS bytes -> CUPS ─────────────────────────────────

def fit(img: Image.Image) -> Image.Image:
    """Scale anything wider than the paper down to paper width."""
    if img.width > PAPER:
        img = img.convert("L").resize((PAPER, round(img.height * PAPER / img.width)), Image.LANCZOS)
    return img if img.mode == "1" else img.convert("1")


def escpos_bytes(images: list[Image.Image], gap_lines: int = 2) -> bytes:
    """One or more images, then feed and a single cut."""
    p = Dummy()
    p.hw("INIT")
    for i, img in enumerate(images):
        if i:
            p.text("\n" * gap_lines)
        p.image(fit(img))
    p.text("\n" * 3)
    p.cut()
    return p.output


def lp(data: bytes, title: str) -> None:
    if DRY:
        return
    r = subprocess.run(["lp", "-d", QUEUE, "-o", "raw", "-t", title],
                       input=data, capture_output=True, timeout=30)
    if r.returncode:
        raise RuntimeError(f"lp failed: {r.stderr.decode(errors='replace').strip()}")


def wait_idle(timeout: float = 180) -> None:
    """Wait until CUPS has sent everything in the queue to the printer."""
    if DRY:
        return
    end = time.time() + timeout
    while time.time() < end:
        r = subprocess.run(["lpstat", "-o", QUEUE], capture_output=True, text=True)
        if not r.stdout.strip():
            return
        time.sleep(0.5)


def _dry_save(images, title):
    out = STATE / "out"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    for i, img in enumerate(images):
        fit(img).save(out / f"{stamp}-{title}-{i}.png")


def print_plan(plan: jobs.Plan, title: str) -> None:
    """Print each image with its own cut, pausing between them if asked."""
    with _print_lock:
        for i, img in enumerate(plan.images):
            if i and plan.pause:
                wait_idle()
                time.sleep(plan.pause)
            if DRY:
                _dry_save([img], f"{title}-{i}")
            lp(escpos_bytes([img]), f"{title}-{i + 1}")


def queue_state() -> dict:
    try:
        p = subprocess.run(["lpstat", "-p", QUEUE], capture_output=True, text=True, timeout=5)
        o = subprocess.run(["lpstat", "-o", QUEUE], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"queue": QUEUE, "ok": False, "state": f"lpstat unavailable: {e}"}
    state = (p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr).strip() else ""
    return {"queue": QUEUE, "ok": p.returncode == 0 and "disabled" not in state,
            "state": state, "pending_jobs": len(o.stdout.strip().splitlines())}


# ── identity ──────────────────────────────────────────────────────

def hostname() -> str:
    """The local network name: `print` -> http://print.local (avahi makes it
    print-2 etc. if several printers share a WiFi)."""
    return socket.gethostname().split(".")[0].lower()


def device_name() -> str:
    """The printer's identity in the cloud: printer-<last 4 of the Pi serial>,
    unique even when every printer is called `print` on its own WiFi."""
    try:
        serial = Path("/sys/firmware/devicetree/base/serial-number").read_text().strip("\x00\n ")
        return f"printer-{serial[-4:].lower()}"
    except OSError:
        return hostname()                     # not a Pi (development)


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))      # no packet is sent; just picks the route
            return s.getsockname()[0]
    except OSError:
        return "?"


PORTS = CFG.get("ports", [80, 9100])        # first one serves the page


def _port_suffix() -> str:
    return "" if PORTS[0] == 80 else f":{PORTS[0]}"


def page_url() -> str:
    return f"http://{hostname()}.local{_port_suffix()}"


def page_qr_url() -> str:
    # The IP, not the .local name: every phone camera can open it.
    return f"http://{local_ip()}{_port_suffix()}"


def slip(markdown_text: str, title: str, qr_data: str = "", caption: str = "") -> None:
    """A status slip: the text, then a QR code (by default: open the print page)."""
    qr_data = qr_data or page_qr_url()
    caption = caption or f"Scan to open the print page\n\n{page_qr_url()}"
    text = jobs.render(CFG, "markdown", {"body": markdown_text, "style": "helvetica",
                                         "show_date": False}).images[0]
    qr = qrcode.make(qr_data, box_size=7, border=3).get_image().convert("1")
    url = jobs.render(CFG, "markdown", {"body": caption,
                                        "style": "helvetica", "show_date": False}).images[0]
    out = Image.new("1", (PAPER, text.height + qr.height + url.height), 1)
    out.paste(text, (0, 0))
    out.paste(qr, ((PAPER - qr.width) // 2, text.height))
    out.paste(url, (0, text.height + qr.height))
    print_plan(jobs.Plan([out]), title)


def test_page() -> None:
    slip(f"# Test print\n\n**{device_name()}**\n\n"
         f"Print page: {page_url()}\n\nAirPrint: {AIRPRINT} @ {hostname()}\n\n"
         f"IP: {local_ip()}\n\n---\n\nIf you can read this, the printer works.", "test")


# ── network: WiFi or own hotspot (comitup) ────────────────────────
# comitup (install.sh) joins a known WiFi, or opens the hotspot <device_name()>
# with its WiFi picker (comitup-web) on port 80. While the hotspot is up,
# printerd lets go of its page port so comitup-web can have it. A
# NetworkManager dispatcher script POSTs /network on every WiFi change; we
# then look at what wlan0 really does, and print a slip when that differs
# from the last one announced (kept in <state>/network.json, so a reboot on
# the same WiFi prints nothing).

def network() -> dict:
    """{"mode": "wifi"|"hotspot", "ssid": ...}, or {"mode": "offline"}.
    Asks the kernel (`iw dev`), not NetworkManager: NM's D-Bus API refuses
    printerd's DynamicUser (no nss-systemd on Pi OS Lite)."""
    try:
        out = subprocess.run(["iw", "dev"], capture_output=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {"mode": "offline"}
    for block in out.split(b"Interface ")[1:]:
        ssid = re.search(rb"^\s*ssid (.*)$", block, re.M)
        typ = re.search(rb"^\s*type (\S+)", block, re.M)
        if ssid and typ and typ[1] in (b"AP", b"managed"):
            # iw writes bytes it can't print (and the backslash) as \xNN
            raw = re.sub(rb"\\x([0-9a-f]{2})", lambda m: bytes([int(m[1], 16)]), ssid[1])
            return {"mode": "hotspot" if typ[1] == b"AP" else "wifi",
                    "ssid": raw.decode("utf-8", "replace")}
    return {"mode": "offline"}


def network_slip(net: dict) -> None:
    if net["mode"] == "hotspot":
        ap = net["ssid"]
        slip(f"# WiFi setup\n\n**{device_name()}** found no WiFi it knows, so it opened "
             f"its own WiFi: **{ap}**\n\n"
             f"1. On your phone, join the WiFi **{ap}** (or scan the code below).\n\n"
             f"2. A page opens (if not, open http://10.41.0.1). Pick your WiFi and enter "
             f"its password.\n\n"
             f"3. The printer joins it and prints \"Connected\".",
             "hotspot", qr_data=f"WIFI:T:nopass;S:{ap};;", caption=f"Scan to join {ap}")
    else:
        slip(f"# Connected\n\n**{device_name()}** is on the WiFi **{net['ssid']}**\n\n"
             f"Print page: {page_url()}\n\nAirPrint: {AIRPRINT} @ {hostname()}", "network")


def _net_file() -> Path:
    return STATE / "network.json"


_net_lock = threading.Lock()
_page_wanted = threading.Event()     # serve the page port? (not while the hotspot is up)


def network_sync() -> None:
    with _net_lock:
        net = network()
        if net["mode"] == "hotspot":
            _page_wanted.clear()
        else:
            _page_wanted.set()
        if net["mode"] == "offline":
            return
        try:
            last = json.loads(_net_file().read_text())
        except (OSError, ValueError):
            last = None
        if net == last:
            return
        log.info("network: %s", net)
        try:
            network_slip(net)
        except Exception as e:                # not saved: the next change tries again
            log.error("network slip failed: %s", e)
            return
        STATE.mkdir(parents=True, exist_ok=True)
        _net_file().write_text(json.dumps(net))


# ── cloud ─────────────────────────────────────────────────────────

class UnknownDevice(Exception):
    pass


def rpc(fn: str, **args):
    req = urllib.request.Request(
        f"{CLOUD_URL}/rest/v1/rpc/{fn}", data=json.dumps(args).encode(), method="POST",
        headers={"apikey": CLOUD_KEY, "Content-Profile": "printer",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if "unknown_device" in body:
            raise UnknownDevice(body)
        raise RuntimeError(f"{fn}: HTTP {e.code} {body[:300]}")


def _device_file() -> Path:
    return STATE / "device.json"


def load_device() -> dict:
    f = _device_file()
    if f.exists():
        return json.loads(f.read_text())
    d = rpc("register_device", name=device_name())
    d["name"] = device_name()
    save_device(d)
    log.info("registered as %s, pairing code %s", d["name"], d["pairing_code"])
    return d


def save_device(d: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    f = _device_file()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    os.chmod(tmp, 0o600)
    tmp.replace(f)


def run_job(job: dict) -> str | None:
    """Print one cloud job. Returns the error text, or None if printed."""
    try:
        plan = jobs.render(CFG, job["template"], job.get("payload") or {})
        print_plan(plan, f"job{job['id']}")
        status["printed"] += 1
        return None
    except Exception as e:                       # report it, don't retry forever
        status["failed"] += 1
        log.warning("job %s (%s) failed: %s", job.get("id"), job.get("template"), e)
        return f"{type(e).__name__}: {e}"[:2000]


def cloud_tick(dev: dict) -> dict:
    r = rpc("claim_jobs", device_token=dev["token"], max_jobs=5)
    status.update(paired=r["active"], last_poll=datetime.now().isoformat(timespec="seconds"),
                  last_error=None, cloud="ok")
    if not r["active"] and not dev.get("pairing_slip"):
        slip(f"# Pair me\n\n**{dev['name']}**\n\nPairing code:\n\n# {dev['pairing_code']}\n\n"
             f"---\n\nSend this code to the owner to activate printing from the cloud.\n\n"
             f"Print page: {page_url()}", "pairing")
        dev["pairing_slip"] = True
        save_device(dev)
    if r["active"] and not dev.get("paired_slip"):
        slip(f"# Ready\n\n**{dev['name']}** is paired.\n\n"
             f"Print page: {page_url()}\n\nAirPrint: {AIRPRINT} @ {hostname()}", "ready")
        dev["paired_slip"] = True
        save_device(dev)
    for job in sorted(r["jobs"], key=lambda j: j["id"]):
        err = run_job(job)
        rpc("finish_job", device_token=dev["token"], job_id=job["id"], error=err)
    global _dev
    _dev = dev if r["active"] else None
    if _dev and time.time() - _fonts_synced > FONT_SYNC_SECONDS:
        sync_fonts()
    return dev


# ── fonts shared through the cloud ────────────────────────────────
# Fonts uploaded on any paired printer live in printer.fonts and are copied
# to every paired printer. FONTS/.cloud.json remembers which local files came
# from the cloud, so a font deleted elsewhere disappears here too. Fonts
# uploaded while unpaired stay on this printer only.

FONT_SYNC_SECONDS = 600
_dev: dict | None = None            # set while paired
_fonts_synced = 0.0


def _manifest() -> dict:
    try:
        return json.loads((FONTS / ".cloud.json").read_text())
    except (OSError, ValueError):
        return {}


def _save_manifest(m: dict) -> None:
    FONTS.mkdir(parents=True, exist_ok=True)
    (FONTS / ".cloud.json").write_text(json.dumps(m))


def sync_fonts() -> None:
    global _fonts_synced
    _fonts_synced = time.time()
    if not _dev:
        return
    cloud = {f["name"]: f["sha256"] for f in rpc("list_fonts", device_token=_dev["token"])}
    m = _manifest()
    FONTS.mkdir(parents=True, exist_ok=True)
    for name, sha in cloud.items():
        if m.get(name) == sha and (FONTS / name).exists():
            continue
        data = base64.b64decode(rpc("get_font", device_token=_dev["token"], name=name))
        try:
            ImageFont.truetype(io.BytesIO(data), 20)
        except Exception:
            log.warning("cloud font %s is not a readable font, skipped", name)
            continue
        (FONTS / name).write_bytes(data)
        m[name] = sha
        log.info("font %s synced from cloud", name)
    for name in [n for n in m if n not in cloud]:
        (FONTS / name).unlink(missing_ok=True)
        del m[name]
        log.info("font %s removed (deleted in cloud)", name)
    if m != _manifest():                 # only on change: spare the SD card
        _save_manifest(m)


def cloud_loop() -> None:
    dev = None
    while True:
        try:
            dev = dev or load_device()
            dev = cloud_tick(dev)
        except UnknownDevice:
            log.warning("device unknown to the cloud, registering again")
            _device_file().unlink(missing_ok=True)
            dev = None
        except Exception as e:
            status.update(cloud="error", last_error=str(e)[:300])
            log.warning("cloud: %s", e)
        time.sleep(CFG.get("poll_seconds", 10))


# ── local HTTP ────────────────────────────────────────────────────

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


def _local(template: str):
    payload = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    f = request.files.get("file")
    data = f.read() if f and f.filename else None
    try:
        plan = jobs.render(CFG, template, payload, data)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    # Printing (with pauses between strips) can take a while: answer now.
    threading.Thread(target=_print_logged, args=(plan, f"page-{template}"), daemon=True).start()
    return jsonify(status="ok", prints=len(plan.images))


def _print_logged(plan, title):
    try:
        print_plan(plan, title)
    except Exception as e:
        log.error("local print %s failed: %s", title, e)


@app.get("/")
def index():
    return send_file(HERE / "index.html")


@app.get("/health")
def health():
    return jsonify(device=device_name(), page=page_url(), ip=local_ip(),
                   cups=queue_state(), **status)


@app.post("/print/markdown")
def print_markdown():
    return _local("markdown")


@app.post("/print/image")
def print_image():
    return _local("image")


@app.post("/print/slices")
def print_slices():
    return _local("slices")


@app.post("/network")
def network_changed():
    """Called by the NetworkManager dispatcher script; local callers only."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify(error="local only"), 403
    threading.Thread(target=network_sync, daemon=True).start()
    return jsonify(status="ok")


@app.post("/print/test")
def print_test():
    test_page()
    return jsonify(status="ok")


@app.get("/fonts")
def fonts_list():
    return jsonify(styles=list(jobs.STYLES), uploaded=jobs.uploaded_fonts(CFG))


@app.post("/fonts")
def fonts_upload():
    f = request.files.get("file")
    name = os.path.basename((f.filename if f else "") or "").replace(" ", "-")
    if not name.lower().endswith(jobs.FONT_EXTS) or not re.fullmatch(r"[\w.-]{1,80}", name):
        return jsonify(error="send a .ttf, .otf or .ttc file with a plain file name"), 400
    data = f.read()
    try:
        ImageFont.truetype(io.BytesIO(data), 20)      # is it really a font?
    except Exception:
        return jsonify(error="that file is not a font PIL can read"), 400
    FONTS.mkdir(parents=True, exist_ok=True)
    (FONTS / name).write_bytes(data)
    if not _dev:
        return jsonify(status="ok", font=name, shared=False)
    try:
        r = rpc("upload_font", device_token=_dev["token"], name=name,
                data=base64.b64encode(data).decode())
        m = _manifest(); m[name] = r["sha256"]; _save_manifest(m)
        return jsonify(status="ok", font=name, shared=True)
    except Exception as e:
        log.warning("font %s not shared: %s", name, e)
        return jsonify(status="ok", font=name, shared=False, warning=f"saved here only: {e}")


@app.delete("/fonts/<name>")
def fonts_delete(name):
    if name not in jobs.uploaded_fonts(CFG):
        return jsonify(error="no such font"), 404
    m = _manifest()
    if name in m and _dev:
        try:
            rpc("delete_font", device_token=_dev["token"], name=name)
        except Exception as e:
            return jsonify(error=f"could not delete it in the cloud: {e}"), 502
        del m[name]; _save_manifest(m)
    (FONTS / name).unlink()
    return jsonify(status="ok")


# Same contract as meinungeheuer's pos-server, so old senders keep working:
# /print takes one pre-rendered image as form field "file", /print/batch
# takes several as "files" and cuts once at the end.
@app.post("/print")
def print_raw():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="No file uploaded"), 400
    img = Image.open(io.BytesIO(f.read()))
    with _print_lock:
        lp(escpos_bytes([img]), "print")
        if DRY:
            _dry_save([img], "print")
    return jsonify(status="ok")


@app.post("/print/batch")
def print_batch():
    imgs = [Image.open(io.BytesIO(f.read())) for f in request.files.getlist("files") if f.filename]
    if not imgs:
        return jsonify(error="No files uploaded"), 400
    with _print_lock:
        lp(escpos_bytes(imgs), "batch")
        if DRY:
            _dry_save(imgs, "batch")
    return jsonify(status="ok", printed=len(imgs))


def main():
    # force: python-escpos already called basicConfig() on import, which hid our INFO lines
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", force=True)
    if CLOUD:
        threading.Thread(target=cloud_loop, daemon=True).start()
    else:
        status["cloud"] = "off (no /etc/printer/printer.env)"
    for port in PORTS[1:]:              # e.g. 9100 for old /print senders (always on)
        srv = make_server("0.0.0.0", port, app, threaded=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    network_sync()                      # before taking port 80: are we the hotspot?
    page_server_loop()


def page_server_loop() -> None:
    """Serve the page port (80) unless the hotspot is up, then comitup-web
    needs it. Retries while someone else still holds it."""
    srv, warned = None, False
    while True:
        if _page_wanted.is_set() and not srv:
            try:
                srv = make_server("0.0.0.0", PORTS[0], app, threaded=True)
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                log.info("page on port %s", PORTS[0]); warned = False
            except (OSError, SystemExit) as e:    # werkzeug exits when the port is taken
                srv = None
                if not warned:
                    log.warning("port %s busy (%s), retrying", PORTS[0], e); warned = True
        elif not _page_wanted.is_set() and srv:
            srv.shutdown(); srv.server_close(); srv = None
            log.info("hotspot up: port %s left to comitup-web", PORTS[0])
        time.sleep(2)


if __name__ == "__main__":
    main()
