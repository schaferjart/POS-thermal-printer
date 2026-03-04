# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Markdown-to-thermal-print system for ESC/POS receipt printers. Renders text as images with custom fonts for full typographic control on 80mm thermal paper. Written in Python 3.11, no build system — pure venv + pip.

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

There are no automated tests or linting configured.

## Architecture

**Dual interface → templates → rendering → printer**

- `print_cli.py` — CLI entry point (argparse). Each subcommand (`test`, `message`, `receipt`, `label`, `dictionary`, `image`, `slice`, `md`) calls a handler that connects to the printer and invokes a template.
- `print_server.py` — Flask HTTP server. Endpoints (`/print/receipt`, `/print/markdown`, etc.) wrap the same template functions.
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

## Raspberry Pi deployment

The system runs on a Pi 3 (Debian Bookworm, aarch64) connected to eduroam WiFi. The Pi serves as a network print server — any device on the same network can POST to `http://<pi-ip>:9100/print/*`.

**Key gotchas discovered during setup:**
- Pi 3 with Bookworm: `wpa_supplicant` systemd service starts but doesn't attach to wlan0. Must be started manually: `sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf`
- If the Pi was previously an AP (hostapd): disable hostapd, remove `nohook wpa_supplicant` and `static ip_address` from `/etc/dhcpcd.conf`, and clear stale DHCP leases (`sudo rm /var/lib/dhcpcd/*.lease`)
- eduroam (ETH Zurich) uses PEAP/MSCHAPv2 with identity `user@student-net.ethz.ch`
- DNS may not resolve after eduroam connects — write `nameserver 8.8.8.8` to `/etc/resolv.conf` and lock with `sudo chattr +i /etc/resolv.conf`
- USB printer requires root: run `sudo ./venv/bin/python3 print_server.py` or add a udev rule
- Pi IP on eduroam is in the `10.5.x.x` range (check with `ip addr show wlan0`)
