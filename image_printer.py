"""
Image-to-thermal-print — resizes any image to paper width, converts to
1-bit black & white using selectable dithering, and sends it to the printer.

Three dither modes:
    halftone  — custom dot grid (classic newspaper look)
    floyd     — Floyd-Steinberg error diffusion (smooth, photographic)
    bayer     — 8x8 Bayer matrix threshold (crosshatch pattern)
"""

import math
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from helpers import open_image


# 8x8 Bayer threshold map (values 0–63, we compare against 0–255 scaled)
_BAYER_8x8 = [
    [ 0, 48, 12, 60,  3, 51, 15, 63],
    [32, 16, 44, 28, 35, 19, 47, 31],
    [ 8, 56,  4, 52, 11, 59,  7, 55],
    [40, 24, 36, 20, 43, 27, 39, 23],
    [ 2, 50, 14, 62,  1, 49, 13, 61],
    [34, 18, 46, 30, 33, 17, 45, 29],
    [10, 58,  6, 54,  9, 57,  5, 53],
    [42, 26, 38, 22, 41, 25, 37, 21],
]


def _prepare(img: Image.Image, paper_px: int,
             contrast: float, brightness: float, sharpness: float) -> Image.Image:
    """Resize to paper width, convert to greyscale, apply enhancements."""
    w, h = img.size
    ratio = paper_px / w
    new_h = int(h * ratio)
    img = img.resize((paper_px, new_h), Image.LANCZOS)

    img = img.convert("L")
    img = ImageOps.autocontrast(img)

    if sharpness != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)

    return img


def _apply_blur(grey: Image.Image, blur: float) -> Image.Image:
    """Apply Gaussian blur to greyscale image before dithering."""
    if blur > 0:
        return grey.filter(ImageFilter.GaussianBlur(radius=blur))
    return grey


# ── Halftone (custom dot grid) ───────────────────────────────────────

def _dither_halftone(grey: Image.Image, dot_size: int = 6) -> Image.Image:
    """
    Divide the greyscale image into cells of dot_size x dot_size.
    For each cell, measure average brightness and draw a filled circle
    whose radius is proportional to darkness.
    """
    w, h = grey.size
    pixels = grey.load()

    out = Image.new("1", (w, h), 1)  # white
    draw = ImageDraw.Draw(out)

    cols = w // dot_size
    rows = h // dot_size
    max_r = dot_size / 2.0

    for row in range(rows):
        y0 = row * dot_size
        for col in range(cols):
            x0 = col * dot_size
            # Average brightness of this cell
            total = 0
            count = 0
            for dy in range(dot_size):
                for dx in range(dot_size):
                    total += pixels[x0 + dx, y0 + dy]
                    count += 1
            avg = total / count / 255.0  # 0=black, 1=white
            darkness = 1.0 - avg
            if darkness < 0.04:
                continue
            r = max_r * math.sqrt(darkness)  # sqrt for perceptual scaling
            cx = x0 + dot_size / 2.0
            cy = y0 + dot_size / 2.0
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)

    return out


# ── Floyd-Steinberg error diffusion ──────────────────────────────────

def _dither_floyd(grey: Image.Image) -> Image.Image:
    """Floyd-Steinberg error diffusion dithering using Pillow's built-in."""
    return grey.convert("1")  # Pillow uses Floyd-Steinberg by default


# ── Bayer (ordered dithering) ─────────────────────────────────────────

def _dither_bayer(grey: Image.Image) -> Image.Image:
    """Bayer matrix ordered dithering — pixel-by-pixel threshold."""
    w, h = grey.size
    src = grey.load()
    out = Image.new("1", (w, h), 1)
    dst = out.load()
    n = 8

    for y in range(h):
        row = _BAYER_8x8[y % n]
        for x in range(w):
            threshold = row[x % n] * 4
            dst[x, y] = 1 if src[x, y] > threshold else 0

    return out


# ── Public API ────────────────────────────────────────────────────────

_MODES = {
    "halftone": _dither_halftone,
    "floyd": _dither_floyd,
    "bayer": _dither_bayer,
}


def process_image(path: str, config: dict = None,
                  mode: str = None, dot_size: int = None,
                  contrast: float = None, brightness: float = None,
                  sharpness: float = None, blur: float = None) -> Image.Image:
    """
    Open *path*, resize, enhance, dither, and return a 1-bit PIL Image
    ready for the thermal printer.

    CLI/server args override config values; config values override defaults.
    """
    cfg = (config or {}).get("halftone", {})

    paper_px = cfg.get("paper_px", 576)
    mode = mode or cfg.get("mode", "floyd")
    dot_size = dot_size or cfg.get("dot_size", 6)
    contrast = contrast if contrast is not None else cfg.get("contrast", 1.3)
    brightness = brightness if brightness is not None else cfg.get("brightness", 1.0)
    sharpness = sharpness if sharpness is not None else cfg.get("sharpness", 1.2)
    blur = blur if blur is not None else cfg.get("blur", 0)

    img = open_image(path)

    grey = _prepare(img, paper_px, contrast, brightness, sharpness)
    grey = _apply_blur(grey, blur)

    if mode not in _MODES:
        raise ValueError(f"Unknown dither mode '{mode}'. Choose from: {', '.join(_MODES)}")

    if mode == "halftone":
        return _dither_halftone(grey, dot_size=dot_size)
    return _MODES[mode](grey)
