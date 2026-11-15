"""
Shared utility functions for the POS thermal printer system.

CONSTRAINT: This module imports ONLY stdlib + Pillow. No project imports.
This prevents circular dependencies since multiple project modules import from here.

Functions:
    resolve_font_path  — resolve relative font paths against the project directory
    wrap_text          — word-wrap text to a pixel width using PIL font metrics
    open_image         — open an image file with EXIF transpose and alpha compositing
"""

import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

# ── Constants ──────────────────────────────────────────────────────

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_FONTS_DIR = os.path.join(_PROJECT_DIR, "fonts")

FONT_THIN = os.path.join(_FONTS_DIR, "Burra-Thin.ttf")
FONT_BOLD = os.path.join(_FONTS_DIR, "Burra-Bold.ttf")


# ── Font path resolution ──────────────────────────────────────────

def resolve_font_path(path: str) -> str:
    """Resolve a font path relative to the project root.

    If *path* is already absolute, return it unchanged.
    Otherwise, join it with the project directory.
    """
    if os.path.isabs(path):
        return path
    return os.path.join(_PROJECT_DIR, path)


# ── Word wrapping ─────────────────────────────────────────────────

def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int,
              draw: ImageDraw.ImageDraw = None) -> list[str]:
    """Word-wrap *text* to fit within *max_width* pixels.

    Uses *draw* (or creates a scratch surface) to measure text via textbbox.
    Returns a list of wrapped lines, or ``[""]`` for empty input.
    """
    if draw is None:
        draw = ImageDraw.Draw(Image.new("1", (1, 1)))

    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test

    if current:
        lines.append(current)

    return lines or [""]


# ── Image opening ─────────────────────────────────────────────────

def open_image(path: str) -> Image.Image:
    """Open an image file, apply EXIF transpose, and composite alpha onto white.

    Returns an RGB PIL Image ready for further processing.
    """
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "LA", "PA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg

    return img
