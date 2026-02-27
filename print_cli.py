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
import sys
from printer_core import load_config, connect, Formatter
import templates


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

    args = parser.parse_args()
    config = load_config(args.config)

    cmds = {
        "test": cmd_test,
        "message": cmd_message,
        "receipt": cmd_receipt,
        "label": cmd_label,
    }
    cmds[args.command](args, config)


if __name__ == "__main__":
    main()
