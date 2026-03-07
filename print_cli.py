#!/usr/bin/env python3
"""
CLI tool for quick printing — use directly without starting the server.

Usage:
    python print_cli.py message "Hello World"
    python print_cli.py message "Important notice" --title "ALERT"
    python print_cli.py receipt --file order.json
    python print_cli.py test
    python print_cli.py test --dummy
"""

import argparse
import json
import os
import sys
from datetime import datetime
from printer_core import load_config, connect, Formatter
import templates
from image_printer import process_image, _prepare, _apply_blur, _dither_floyd, _dither_bayer, _dither_halftone
from image_slicer import slice_vertical, slice_horizontal
try:
    from portrait_pipeline import run_pipeline
    _has_portrait = True
except ImportError:
    _has_portrait = False


def cmd_test(args, config):
    """Print a test page to verify the printer works."""
    p = connect(config, dummy=args.dummy)
    fmt = Formatter(p, config["printer"]["paper_width"])

    fmt.title("PRINTER TEST")
    fmt.blank()
    fmt.center("If you can read this,")
    fmt.center("your printer is working!")
    fmt.double_line()
    fmt.text("Normal text")
    fmt.bold("Bold text")
    fmt.left_right("Left", "Right")
    fmt.line()
    fmt.columns(["Col 1", "Col 2", "Col 3"], aligns=["l", "c", "r"])
    fmt.columns(["Apple", "5", "2.50"], aligns=["l", "c", "r"])
    fmt.columns(["Banana", "3", "1.20"], aligns=["l", "c", "r"])
    fmt.double_line()
    fmt.center("Test complete")
    fmt.feed()
    fmt.cut()

    if args.dummy:
        print("[DUMMY] Test page generated (not printed)")
    else:
        print("[OK] Test page printed")


def cmd_message(args, config):
    """Print a simple text message."""
    p = connect(config, dummy=args.dummy)
    fmt = Formatter(p, config["printer"]["paper_width"])
    templates.simple_message(fmt, args.text, args.title)
    print(f"[OK] Printed message: {args.text[:40]}...")


def cmd_receipt(args, config):
    """Print a receipt from a JSON file."""
    with open(args.file) as f:
        data = json.load(f)
    p = connect(config, dummy=args.dummy)
    fmt = Formatter(p, config["printer"]["paper_width"])
    templates.receipt(fmt, data, config)
    print(f"[OK] Receipt printed ({len(data.get('items', []))} items)")


def cmd_label(args, config):
    """Print a label."""
    p = connect(config, dummy=args.dummy)
    fmt = Formatter(p, config["printer"]["paper_width"])
    templates.label(fmt, args.heading, args.lines)
    print(f"[OK] Label printed: {args.heading}")


def cmd_dictionary(args, config):
    """Print a dictionary entry — word, definition, citations."""
    if args.file:
        with open(args.file) as f:
            data = json.load(f)
    else:
        data = {
            "word": args.word,
            "definition": args.definition,
        }
        if args.citations:
            data["citations"] = args.citations
        if args.qr:
            data["qr_url"] = args.qr
    p = connect(config, dummy=args.dummy)
    fmt = Formatter(p, config["printer"]["paper_width"])
    templates.dictionary_entry(fmt, data, config)
    print(f"[OK] Dictionary entry printed: {data['word']}")


def cmd_image(args, config):
    """Print an image with halftone/dithering."""
    img = process_image(
        args.path, config,
        mode=args.mode, dot_size=args.dot,
        contrast=args.contrast, brightness=args.brightness,
        sharpness=args.sharpness, blur=args.blur,
    )
    if args.dummy:
        out = args.path.rsplit(".", 1)[0] + f"_preview_{args.mode or 'halftone'}.png"
        img.save(out)
        print(f"[DUMMY] Preview saved to {out}")
    else:
        p = connect(config, dummy=False)
        fmt = Formatter(p, config["printer"]["paper_width"])
        label = os.path.basename(args.path)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        fmt.bold(f"{label}  {timestamp}")
        fmt.blank()
        fmt.p.image(img)
        fmt.feed()
        fmt.cut()
        print(f"[OK] Image printed: {args.path}")


def cmd_slice(args, config):
    """Print an image as vertical or horizontal strips with dithering."""
    from PIL import ImageOps, ImageEnhance, ImageFilter

    cfg = config.get("halftone", {})
    mode = args.mode or cfg.get("mode", "floyd")
    blur = args.blur if args.blur is not None else cfg.get("blur", 0)
    contrast = args.contrast if args.contrast is not None else cfg.get("contrast", 1.3)
    brightness = args.brightness if args.brightness is not None else cfg.get("brightness", 1.0)
    sharpness = args.sharpness if args.sharpness is not None else cfg.get("sharpness", 1.2)
    dot_size = args.dot or cfg.get("dot_size", 6)

    dither_fn = {"floyd": _dither_floyd, "bayer": _dither_bayer, "halftone": _dither_halftone}[mode]

    if args.direction == "vertical":
        strips = slice_vertical(args.path, args.strips)
    else:
        strips = slice_horizontal(args.path, args.strips)

    p = connect(config, dummy=args.dummy)
    fmt = Formatter(p, config["printer"]["paper_width"])

    for i, strip in enumerate(strips):
        strip = strip.convert("L")
        strip = ImageOps.autocontrast(strip)
        if sharpness != 1.0:
            strip = ImageEnhance.Sharpness(strip).enhance(sharpness)
        if contrast != 1.0:
            strip = ImageEnhance.Contrast(strip).enhance(contrast)
        if brightness != 1.0:
            strip = ImageEnhance.Brightness(strip).enhance(brightness)
        if blur > 0:
            strip = strip.filter(ImageFilter.GaussianBlur(radius=blur))

        if mode == "halftone":
            dithered = _dither_halftone(strip, dot_size=dot_size)
        else:
            dithered = dither_fn(strip)

        fmt.blank()
        fmt.bold(f"STRIP {i+1}/{args.strips}")
        fmt.blank()
        p.image(dithered)
        fmt.blank()
        fmt.line()

    fmt.feed()
    fmt.cut()
    print(f"[OK] {args.strips} {args.direction} strips printed: {args.path}")


def cmd_portrait(args, config):
    """Run the portrait-to-statue pipeline."""
    if not _has_portrait:
        print("Error: portrait pipeline requires numpy and mediapipe. Install with:")
        print("  pip install numpy mediapipe")
        sys.exit(1)
    p = connect(config, dummy=args.dummy)
    save_dir = os.path.dirname(args.paths[0]) or "."
    run_pipeline(
        args.paths, config, p,
        dummy=args.dummy,
        save_dir=save_dir,
        skip_selection=args.skip_selection,
        skip_transform=args.skip_transform,
        blur=args.blur,
        dither_mode=args.mode,
    )
    if args.dummy:
        print(f"[DUMMY] Portrait previews saved to {save_dir}")
    else:
        print("[OK] Portrait pipeline complete")


def cmd_markdown(args, config):
    """Print a markdown file or inline markdown text."""
    if args.file:
        with open(args.file) as f:
            md_text = f.read()
    else:
        md_text = args.text
    p = connect(config, dummy=args.dummy)
    fmt = Formatter(p, config["printer"]["paper_width"])
    templates.markdown(fmt, md_text, config, show_date=not args.no_date, style=args.style)
    preview = md_text.strip().split("\n")[0][:40]
    print(f"[OK] Markdown printed: {preview}...")


def main():
    parser = argparse.ArgumentParser(description="POS Thermal Printer CLI")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--dummy", action="store_true", help="Run without real printer")
    sub = parser.add_subparsers(dest="command", required=True)

    # test
    sub.add_parser("test", help="Print a test page")

    # message
    p_msg = sub.add_parser("message", help="Print a text message")
    p_msg.add_argument("text", help="Text to print")
    p_msg.add_argument("--title", help="Optional title")

    # receipt
    p_rcpt = sub.add_parser("receipt", help="Print a receipt from JSON file")
    p_rcpt.add_argument("--file", required=True, help="Path to JSON file with receipt data")

    # label
    p_lbl = sub.add_parser("label", help="Print a label")
    p_lbl.add_argument("heading", help="Label heading")
    p_lbl.add_argument("lines", nargs="*", help="Body lines")

    # dictionary
    p_dict = sub.add_parser("dictionary", help="Print a dictionary entry")
    p_dict.add_argument("word", nargs="?", help="The word")
    p_dict.add_argument("definition", nargs="?", help="The definition")
    p_dict.add_argument("--citations", nargs="*", help="Citation strings")
    p_dict.add_argument("--qr", help="QR code URL")
    p_dict.add_argument("--file", help="JSON file with entry data (overrides other args)")

    # image
    p_img = sub.add_parser("image", help="Print an image with halftone/dithering")
    p_img.add_argument("path", help="Path to image file")
    p_img.add_argument("--mode", choices=["halftone", "floyd", "bayer"],
                       help="Dither mode (default: from config)")
    p_img.add_argument("--dot", type=int, help="Halftone dot/cell size in px")
    p_img.add_argument("--contrast", type=float, help="Contrast multiplier")
    p_img.add_argument("--brightness", type=float, help="Brightness multiplier")
    p_img.add_argument("--sharpness", type=float, help="Sharpness multiplier")
    p_img.add_argument("--blur", type=float, help="Gaussian blur radius (0=off)")

    # slice
    p_slc = sub.add_parser("slice", help="Print image as strips (vertical or horizontal)")
    p_slc.add_argument("path", help="Path to image file")
    p_slc.add_argument("strips", type=int, help="Number of strips")
    p_slc.add_argument("--direction", choices=["vertical", "horizontal"], default="vertical",
                       help="Slice direction (default: vertical)")
    p_slc.add_argument("--mode", choices=["halftone", "floyd", "bayer"],
                       help="Dither mode (default: from config)")
    p_slc.add_argument("--dot", type=int, help="Halftone dot/cell size in px")
    p_slc.add_argument("--contrast", type=float, help="Contrast multiplier")
    p_slc.add_argument("--brightness", type=float, help="Brightness multiplier")
    p_slc.add_argument("--sharpness", type=float, help="Sharpness multiplier")
    p_slc.add_argument("--blur", type=float, help="Gaussian blur radius (0=off)")

    # portrait
    p_port = sub.add_parser("portrait", help="Portrait-to-Roman-statue pipeline")
    p_port.add_argument("paths", nargs="+", help="Image file(s)")
    p_port.add_argument("--skip-selection", action="store_true",
                        help="Skip AI photo selection, use first image")
    p_port.add_argument("--skip-transform", action="store_true",
                        help="Skip style transfer (print original with dithering)")
    p_port.add_argument("--blur", type=float, help="Gaussian blur radius (default 10)")
    p_port.add_argument("--mode", choices=["bayer", "floyd", "halftone"],
                        help="Dither mode (default: bayer)")

    # markdown
    p_md = sub.add_parser("md", help="Print markdown text or file")
    p_md.add_argument("text", nargs="?", help="Inline markdown text")
    p_md.add_argument("--file", help="Path to .md file")
    p_md.add_argument("--style", default="dictionary", help="Style template: dictionary, helvetica")
    p_md.add_argument("--no-date", action="store_true", help="Hide date/time footer")

    args = parser.parse_args()
    config = load_config(args.config)

    cmds = {
        "test": cmd_test,
        "message": cmd_message,
        "receipt": cmd_receipt,
        "label": cmd_label,
        "image": cmd_image,
        "slice": cmd_slice,
        "dictionary": cmd_dictionary,
        "portrait": cmd_portrait,
        "md": cmd_markdown,
    }
    cmds[args.command](args, config)


if __name__ == "__main__":
    main()
