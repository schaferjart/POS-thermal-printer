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
print.sh           Wrapper script (no venv activation needed)
print_cli.py       CLI tool
print_server.py    HTTP server for automated print jobs
printer_core.py    Printer connection + text formatting helpers
templates.py       Print templates (receipt, dictionary, markdown, etc.)
md_renderer.py     Markdown → image renderer
image_printer.py   Image dithering engine (floyd, bayer, halftone + blur)
image_slicer.py    Vertical/horizontal strip slicing for poster prints
config.yaml        Printer config + font style definitions
fonts/             Font files
```

## Raspberry Pi

Same setup works on Raspberry Pi. Add a udev rule for USB permissions:

```bash
# Find your printer's IDs with lsusb
sudo tee /etc/udev/rules.d/99-escpos.rules <<< \
  'SUBSYSTEM=="usb", ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="2016", MODE="0666"'
sudo udevadm control --reload
```
