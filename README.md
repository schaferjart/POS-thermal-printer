# POS Thermal Printer

Markdown-to-thermal-print system for ESC/POS receipt printers. Renders text as images with custom fonts, so you get full typographic control on cheap thermal paper.

Built for the BORN4SHIP V330M (Xprinter XP-V330M, 80mm) but works with any ESC/POS printer over USB.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

macOS also needs libusb: `brew install libusb`

## Quick Start

```bash
# Print a markdown file
./print.sh md --file myfile.md

# Pick a font style
./print.sh md --file myfile.md --style helvetica
./print.sh md --file myfile.md --style acidic

# Print a test page
./print.sh test

# Print a simple message
./print.sh message "Hello World" --title "NOTICE"
```

## Image Printing

Print photos and graphics with three dither modes:

| Mode | Look | Best for |
|---|---|---|
| `floyd` (default) | Smooth, organic | Photos, portraits, detailed artwork |
| `bayer` | Crosshatch grid | Stylized/retro look, pairs well with blur |
| `halftone` | Dot grid (newspaper) | Bold graphics, high-contrast images |

```bash
# Print an image (Floyd-Steinberg, default)
./print.sh image photo.jpg

# Bayer dithering with gaussian blur
./print.sh image photo.jpg --mode bayer --blur 10

# Halftone with custom dot size
./print.sh image photo.jpg --mode halftone --dot 4

# Adjust contrast/brightness/sharpness
./print.sh image photo.jpg --contrast 1.5 --brightness 1.1 --sharpness 1.4
```

### Strip Printing

Slice an image into strips for wider or taller prints — tape them together for posters:

```bash
# 4 vertical strips (left to right) — tape side by side
./print.sh slice photo.jpg 4 --direction vertical --mode bayer --blur 10

# 3 horizontal strips (top to bottom)
./print.sh slice photo.jpg 3 --direction horizontal --mode floyd
```

### Image HTTP Endpoint

```bash
curl -X POST http://localhost:9100/print/image \
  -F "file=@photo.jpg" -F "mode=bayer" -F "blur=10"
```

## Portrait Pipeline

AI-powered portrait-to-sculpture pipeline. Takes a photo, transforms it into a translucent wax bust aesthetic via Gemini Flash Image (through n8n), then crops at 4 face-landmark zoom levels with bayer dithering.

Requires `OPENROUTER_API_KEY` env var and an active n8n workflow.

```bash
# Quick run (dummy mode, saves previews)
export OPENROUTER_API_KEY="your-key-here"
./run_portrait.sh photo.jpg

# Full CLI with options
./print.sh portrait photo.jpg --skip-selection
./print.sh portrait photo1.jpg photo2.jpg photo3.jpg   # AI picks best
./print.sh portrait photo.jpg --skip-transform          # print original with dithering
./print.sh portrait photo.jpg --blur 15 --mode floyd

# Dummy mode — save previews without printing
./print.sh --dummy portrait photo.jpg --skip-selection
```

Output (4 zoom levels, computed from mediapipe face landmarks):
- `zoom_0` — shoulders to hairline (full portrait)
- `zoom_1` — chin to forehead, outer-eye width
- `zoom_2` — inter-pupillary width, nose-bridge height
- `zoom_3` — narrow vertical strip through face center

The style prompt lives in `config.yaml` under `portrait.style_prompt` — edit it directly and re-run.

### Portrait HTTP Endpoints

```bash
# Full pipeline (upload photos, transform + print)
curl -X POST http://localhost:9100/portrait/capture \
  -F "file=@photo.jpg"

# Transform only (returns PNG, no printing)
curl -X POST http://localhost:9100/portrait/transform \
  -F "file=@photo.jpg" --output statue.png
```

## Font Styles

Three built-in styles, configured in `config.yaml`:

| Style | Font | Character |
|---|---|---|
| `dictionary` (default) | Burra Thin/Bold | Geometric, all-caps art font |
| `helvetica` | Helvetica Neue Light/Bold | Clean, minimal, classic |
| `acidic` | Acidic | Big, raw, hard-wraps mid-word |

## Markdown Support

```
# Heading 1          → bold, large
## Heading 2         → bold, body size
**bold**             → bold inline
*italic*             → underlined inline
~~strikethrough~~    → line through text
`code`               → inverted box
- list item          → indented with dash
> blockquote         → indented with bar
---                  → dotted separator
```

Indentation from the source `.md` file is preserved as visual indent on paper.

## HTTP Server

For automated workflows — any program can send print jobs over HTTP:

```bash
./print.sh                          # or: python print_server.py
```

```bash
# Print markdown
curl -X POST http://localhost:9100/print/markdown \
  -H "Content-Type: application/json" \
  -d '{"text": "# Hello\n\nWorld", "style": "helvetica"}'

# Print a receipt
curl -X POST http://localhost:9100/print/receipt \
  -H "Content-Type: application/json" \
  -d '{"items":[{"name":"Coffee","qty":2,"price":5.0}]}'

# Print a dictionary entry
curl -X POST http://localhost:9100/print/dictionary \
  -H "Content-Type: application/json" \
  -d '{"word":"Ephemeral","definition":"Lasting for a very short time."}'
```

## Adding a Font Style

Add a section to `config.yaml`:

```yaml
mystyle:
  font_word: "fonts/MyFont-Bold.ttf"
  font_body: "fonts/MyFont-Regular.ttf"
  font_bold: "fonts/MyFont-Bold.ttf"
  font_cite: "fonts/MyFont-Light.ttf"
  font_date: "fonts/MyFont-Light.ttf"
  size_word: 32
  size_body: 20
  size_cite: 18
  size_date: 16
  line_spacing: 1.4
  gap_after_word: 30
  gap_before_cite: 20
  margin: 20
  paper_px: 576
  # hard_wrap: true    # uncomment for character-level line breaks
```

For `.ttc` collection files (like system fonts), add `_index` fields:

```yaml
  font_body: "/System/Library/Fonts/HelveticaNeue.ttc"
  font_body_index: 7    # Light weight
```

Then use it: `./print.sh md --file text.md --style mystyle`

## Files

```
print.sh              Wrapper script (no venv activation needed)
print_cli.py          CLI tool
print_server.py       HTTP server for automated print jobs
printer_core.py       Printer connection + text formatting helpers
templates.py          Print templates (receipt, dictionary, markdown, etc.)
md_renderer.py        Markdown → image renderer
image_printer.py      Image dithering engine (floyd, bayer, halftone + blur)
image_slicer.py       Vertical/horizontal strip slicing for poster prints
portrait_pipeline.py  Portrait-to-statue pipeline (n8n + mediapipe)
run_portrait.sh       Quick-run script for portrait pipeline
config.yaml           Printer config + font style definitions + portrait prompt
fonts/                Font files
```

## Raspberry Pi Deployment

Tested on Raspberry Pi 3 with Debian Bookworm. The Pi runs the print server headlessly on the network — any device on the same WiFi can send print jobs.

### Initial Setup

```bash
# Install system dependencies
sudo apt update && sudo apt install -y python3-venv python3-pip git libusb-1.0-0-dev

# Clone and set up
git clone https://github.com/schaferjart/POS-thermal-printer.git
cd POS-thermal-printer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### USB Permissions

The printer needs root access by default. Either run with sudo:

```bash
sudo ./venv/bin/python3 print_server.py
```

Or add a udev rule for unprivileged access:

```bash
sudo tee /etc/udev/rules.d/99-escpos.rules <<< \
  'SUBSYSTEM=="usb", ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="2016", MODE="0666"'
sudo udevadm control --reload
# Unplug and replug the printer
```

### WiFi: Connecting to eduroam (WPA2-Enterprise)

The Pi 3's built-in WiFi works with eduroam but needs manual wpa_supplicant configuration since it uses WPA2-Enterprise (PEAP/MSCHAPv2).

**1. Disable any access point mode** (if previously configured):

```bash
sudo systemctl stop hostapd
sudo systemctl disable hostapd
```

**2. Remove any static IP on wlan0** — check `/etc/dhcpcd.conf` for lines like `interface wlan0`, `static ip_address=...`, or `nohook wpa_supplicant` and delete them.

**3. Configure wpa_supplicant** (`sudo nano /etc/wpa_supplicant/wpa_supplicant.conf`):

```
ctrl_interface=DIR=/var/run/wpa_supplicant
update_config=1
country=CH

network={
    ssid="eduroam"
    key_mgmt=WPA-EAP
    eap=PEAP
    phase2="auth=MSCHAPV2"
    identity="user@student-net.ethz.ch"
    password="your_password"
    priority=20
}

network={
    ssid="HomeWiFi"
    psk="home_password"
    key_mgmt=WPA-PSK
    priority=5
}
```

Multiple network blocks are supported — the Pi connects to whichever is available, preferring higher priority values.

**4. Start wpa_supplicant manually** (the systemd service doesn't attach to wlan0 by default on Bookworm):

```bash
sudo killall wpa_supplicant
sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf
sudo dhcpcd wlan0
```

**5. Fix DNS** (eduroam may not set nameservers correctly):

```bash
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
sudo chattr +i /etc/resolv.conf   # lock so dhcpcd can't overwrite
```

### Auto-Start on Boot

Create a systemd service so the print server starts automatically when the Pi powers on:

```bash
sudo nano /etc/systemd/system/pos-printer.service
```

```ini
[Unit]
Description=POS Thermal Print Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/stoffel/POS-thermal-printer
ExecStartPre=/bin/bash -c 'killall wpa_supplicant 2>/dev/null; wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf; dhcpcd wlan0; sleep 5'
ExecStart=/home/stoffel/POS-thermal-printer/venv/bin/python3 print_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pos-printer.service
sudo systemctl start pos-printer.service
```

The Pi will now connect to WiFi and start the print server on every boot. Check status with `sudo systemctl status pos-printer.service`.

### Hostname Discovery (mDNS)

So you don't need to look up the Pi's IP every time:

```bash
sudo apt install -y avahi-daemon
sudo systemctl enable avahi-daemon
```

Now reach the Pi at `raspberrypi.local` from any device on the same network:

```bash
curl http://raspberrypi.local:9100/health
```

### Finding the Pi on the Network

mDNS (`raspberrypi.local`) works on home networks but **not on eduroam** (blocks multicast). To find the Pi on eduroam, scan for its MAC address (Pi 3 MACs start with `b8:27`):

```bash
arp -a | grep -i "b8:27"
```

### Sending Print Jobs Over the Network

Once the server is running, any device on the same network can print:

```bash
# From any machine on the network
curl -X POST http://<pi-ip>:9100/print/markdown \
  -H "Content-Type: application/json" \
  -d '{"text": "# Hello\n\nPrinted from the network!", "show_date": false}'

# Health check
curl http://<pi-ip>:9100/health
```
