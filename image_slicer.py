"""
Slice an image into N strips (vertical or horizontal), each resized to paper width.
Vertical strips: side-by-side for wider-than-paper output.
Horizontal strips: stacked for taller segmented prints.
"""

from PIL import Image
from helpers import open_image


def slice_vertical(path: str, n: int, paper_px: int = 576) -> list[Image.Image]:
    """
    Split image into *n* vertical strips (left to right).
    Each strip is resized so its width = paper_px.
    """
    img = open_image(path)
    w, h = img.size
    strip_w = w // n
    strips = []

    for i in range(n):
        x0 = i * strip_w
        x1 = w if i == n - 1 else (i + 1) * strip_w
        strip = img.crop((x0, 0, x1, h))
        sw, sh = strip.size
        ratio = paper_px / sw
        strip = strip.resize((paper_px, int(sh * ratio)), Image.LANCZOS)
        strips.append(strip)

    return strips


def slice_horizontal(path: str, n: int, paper_px: int = 576) -> list[Image.Image]:
    """
    Split image into *n* horizontal strips (top to bottom).
    Each strip is resized so its width = paper_px.
    """
    img = open_image(path)
    w, h = img.size
    # First resize to paper width
    ratio = paper_px / w
    img = img.resize((paper_px, int(h * ratio)), Image.LANCZOS)
    w, h = img.size
    strip_h = h // n
    strips = []

    for i in range(n):
        y0 = i * strip_h
        y1 = h if i == n - 1 else (i + 1) * strip_h
        strip = img.crop((0, y0, w, y1))
        strips.append(strip)

    return strips


# Backward compat
slice_image = slice_vertical
