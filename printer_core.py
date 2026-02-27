"""
Core printer module — handles connection and text formatting for ESC/POS thermal printers.
"""

import textwrap
import yaml
from escpos.printer import Usb, Dummy


def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def connect(config=None, dummy=False):
    """Connect to the printer. Use dummy=True for testing without hardware."""
    if config is None:
        config = load_config()
    if dummy:
        return Dummy()
    pc = config["printer"]
    return Usb(pc["vendor_id"], pc["product_id"])


class Formatter:
    """High-level formatting helpers built on top of python-escpos."""

    def __init__(self, printer, width=48):
        self.p = printer
        self.w = width

    # --- Text helpers ---

    def title(self, text):
        """Large centered bold text."""
        self.p.set(align="center", bold=True, double_height=True, double_width=True)
        self.p.text(f"{text}\n")
        self.p.set(align="left", bold=False, double_height=False, double_width=False)

    def subtitle(self, text):
        """Centered bold text, normal size."""
        self.p.set(align="center", bold=True)
        self.p.text(f"{text}\n")
        self.p.set(align="left", bold=False)

    def center(self, text):
        """Centered normal text."""
        self.p.set(align="center")
        self.p.text(f"{text}\n")
        self.p.set(align="left")

    def text(self, text):
        """Left-aligned normal text."""
        self.p.set(align="left", bold=False)
        self.p.text(f"{text}\n")

    def bold(self, text):
        """Left-aligned bold text."""
        self.p.set(bold=True)
        self.p.text(f"{text}\n")
        self.p.set(bold=False)

    def wrap(self, text, indent=0):
        """Word-wrapped left-aligned text that respects paper width."""
        prefix = " " * indent
        for line in textwrap.fill(text, width=self.w - indent).split("\n"):
            self.p.text(f"{prefix}{line}\n")

    def italic_text(self, text):
        """Underlined text (thermal printers have no italic — underline is the convention)."""
        self.p.set(underline=1)
        self.p.text(f"{text}\n")
        self.p.set(underline=0)

    def small(self, text):
        """Smaller text using Font B."""
        self.p.set(font="b")
        self.p.text(f"{text}\n")
        self.p.set(font="a")

    def right(self, text):
        """Right-aligned text."""
        self.p.set(align="right")
        self.p.text(f"{text}\n")
        self.p.set(align="left")

    def line(self, char="-"):
        """Print a horizontal separator line."""
        self.p.text(char * self.w + "\n")

    def double_line(self):
        self.line("=")

    def blank(self, n=1):
        """Print n blank lines."""
        self.p.text("\n" * n)

    def left_right(self, left, right):
        """Print left-aligned and right-aligned text on the same line."""
        spaces = self.w - len(left) - len(right)
        if spaces < 1:
            spaces = 1
        self.p.text(f"{left}{' ' * spaces}{right}\n")

    def left_right_bold(self, left, right):
        """Same as left_right but bold."""
        self.p.set(bold=True)
        self.left_right(left, right)
        self.p.set(bold=False)

    def columns(self, cols, widths=None, aligns=None):
        """
        Print a row with multiple columns.
        cols: list of strings
        widths: list of ints (char widths per column), auto-distributed if None
        aligns: list of 'l'/'r'/'c' per column, defaults to 'l'
        """
        n = len(cols)
        if widths is None:
            base = self.w // n
            widths = [base] * n
            widths[-1] = self.w - base * (n - 1)
        if aligns is None:
            aligns = ["l"] * n

        parts = []
        for text, w, a in zip(cols, widths, aligns):
            text = str(text)[:w]
            if a == "r":
                parts.append(text.rjust(w))
            elif a == "c":
                parts.append(text.center(w))
            else:
                parts.append(text.ljust(w))
        self.p.text("".join(parts) + "\n")

    # --- Structural helpers ---

    def qr(self, data, size=4):
        self.p.set(align="center")
        self.p.qr(data, size=size)
        self.p.set(align="left")

    def barcode(self, data, bc_type="CODE128"):
        self.p.set(align="center")
        self.p.barcode(data, bc_type)
        self.p.set(align="left")

    def cut(self):
        self.p.cut()

    def feed(self, n=3):
        """Feed n lines before cutting (ensures text clears the cutter)."""
        self.p.text("\n" * n)
