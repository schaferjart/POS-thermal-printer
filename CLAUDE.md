# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Markdown-to-thermal-print system for ESC/POS receipt printers. Renders text as images with custom fonts for full typographic control on 80mm thermal paper. Written in Python, no build system — pure venv + pip.

## Setup & Running

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
# macOS also needs: brew install libusb
```

**CLI** (primary interface):
```bash
./print.sh <command> [args]       # wrapper that activates venv
python print_cli.py <command>     # direct
```

**HTTP server** (port 9100):
```bash
python print_server.py
```

**Testing without hardware** — all commands accept `--dummy`:
```bash
./print.sh test --dummy
./print.sh image photo.jpg --dummy   # saves preview_<mode>.png
```

**Stress testing:**
```bash
./stress_test.sh [host:port]      # default: 192.168.1.65:9100
```

There are no unit tests or linting configured.

## Architecture

**Dual interface → templates → rendering → printer**

- `print_cli.py` — CLI entry point (argparse). Each subcommand (`test`, `message`, `receipt`, `label`, `dictionary`, `image`, `slice`, `md`) calls a handler that connects to the printer and invokes a template.
- `print_server.py` — Flask HTTP server. Endpoints (`/print/receipt`, `/print/markdown`, etc.) wrap the same template functions. Thread-safe print lock serializes USB access. `with_retry()` handles reconnection on failure. JSON error responses via global error handler.
- `templates.py` — Print layout functions. Each takes a `Formatter`, data dict, and config. Templates: `receipt`, `simple_message`, `label`, `two_column_list`, `dictionary_entry`, `markdown`.
- `printer_core.py` — `connect()` creates USB or Dummy printer. `Formatter` class wraps ESC/POS commands for text formatting, layout, barcodes, and cut/feed.
- `md_renderer.py` — Parses a markdown subset and renders to a 1-bit PIL Image. Supports `#`/`##` headings, `**bold**`, `*italic*` (rendered as underline), `~~strikethrough~~`, `` `code` `` (inverted), lists, blockquotes, `---` separators. Font styles are loaded from `config.yaml`.
- `image_printer.py` — Dithering pipeline: `_prepare()` → `_apply_blur()` → dithering (Floyd-Steinberg, Bayer 8x8, or halftone dots). Returns 1-bit image for ESC/POS.
- `image_slicer.py` — Splits images into vertical or horizontal strips for poster-size prints across multiple receipts.
- `config.yaml` — All configuration: USB IDs, paper width (48 chars / 576px), server settings, template defaults, and font style definitions.

## Key patterns

- **Image-based text rendering**: Markdown and dictionary templates render to PIL Images first, then print as raster image. This bypasses ESC/POS font limitations.
- **Font styles in config.yaml**: Three styles (`dictionary`, `helvetica`, `acidic`) define font paths, sizes, spacing, margins. `.ttc` collections use `font_*_index` for face selection. Add new styles by copying a block and pointing to new font files.
- **New template**: Add function in `templates.py`, add CLI subcommand in `print_cli.py`, add endpoint in `print_server.py`.
- **New dithering mode**: Add to `_MODES` dict in `image_printer.py`.

## CLI commands

`test` | `message "text" [--title T]` | `receipt --file order.json` | `label heading [lines...]` | `dictionary word definition [--citations] [--qr url]` | `image path [--mode halftone|floyd|bayer] [--blur N] [--contrast N]` | `slice path N [--direction vertical|horizontal]` | `md "text" [--file path.md] [--style dictionary|helvetica|acidic] [--no-date]`

- `stress_test.sh` — Bash stress test suite: tests all endpoints, malformed input, edge cases, rapid fire, concurrent requests, large payloads.

## Raspberry Pi deployment

The system runs on a Pi 3 (Debian Trixie, aarch64, fresh flash 2026-03-08). The Pi serves as a network print server — any device on the same network can POST to `http://<pi-ip>:9100/print/*`. User: `stoffel`, project dir: `/home/stoffel/POS-thermal-printer`.

**Quick deploy** (fresh Pi):
```bash
sudo apt-get update && sudo apt-get install -y python3-pip python3-venv libusb-1.0-0-dev git
git clone https://github.com/schaferjart/POS-thermal-printer.git ~/POS-thermal-printer
cd ~/POS-thermal-printer
./setup.sh
```

**Update existing Pi:**
```bash
cd ~/POS-thermal-printer && git pull origin main && sudo systemctl restart pos-printer
```

**Service management:**
```bash
sudo systemctl status pos-printer    # check status
sudo systemctl restart pos-printer   # restart
journalctl -u pos-printer -f         # live logs
```

**Key gotchas discovered during setup:**
- `usblp` kernel module grabs the USB printer before python-escpos can. `setup.sh` blacklists it automatically (`/etc/modprobe.d/no-usblp.conf`). Manual fix: `sudo rmmod usblp`
- systemd service has restart limits (3 per 60s), memory cap (400MB), task limit (100) to prevent crash-loop resource exhaustion
- Portrait pipeline (`numpy`, `mediapipe`) is optional — server starts fine without them via lazy imports
- `helvetica` font style references macOS-only paths (`/System/Library/Fonts/HelveticaNeue.ttc`) — use `dictionary` or `acidic` styles on Pi
- Pi 3 with Bookworm/Trixie: `wpa_supplicant` systemd service starts but may not attach to wlan0. Must be started manually: `sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf`
- eduroam (ETH Zurich) uses PEAP/MSCHAPv2 with identity `user@student-net.ethz.ch`. Pi IP on eduroam is in the `10.5.x.x` range
- DNS may not resolve after eduroam connects — write `nameserver 8.8.8.8` to `/etc/resolv.conf` and lock with `sudo chattr +i /etc/resolv.conf`
- Home WiFi: Pi gets IP via DHCP (currently `192.168.1.65`)
