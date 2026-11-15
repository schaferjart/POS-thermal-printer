"""Print templates: (template, payload) -> Plan.

A Plan is the list of images to print, with a cut after each one, and a
pause between them. The cloud job loop and the print page both go through
render(), so a template behaves the same wherever the job comes from.

Payloads (all fields optional unless marked):
  markdown  body*, style (dictionary|helvetica|acidic or an uploaded font
            file name), heading_font (uploaded font), size, show_date
  image     image_url*, dither (floyd|bayer|halftone), dot_size, contrast,
            brightness, sharpness, blur
  slices    image_url*, count, direction (vertical|horizontal), mode
            (separate|single), gap, padding, pause, caption,
            caption_position (above|below), caption_size, + image options
  showmemo  object_id*, image_url*, title, artist, date, times_before
            (times_before is added by send_print)
The print page sends the image itself instead of image_url.
"""

from __future__ import annotations

import io
import os
import urllib.request
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

import image_printer
import image_slicer
import md_renderer
import showmemo
from helpers import open_image, resolve_font_path

MAX_DOWNLOAD = 20 * 1024 * 1024
STYLES = ("dictionary", "helvetica", "acidic")
FONT_EXTS = (".ttf", ".otf", ".ttc")
CAPTION_FONT = "fonts/LiberationSans-Regular.ttf"


@dataclass
class Plan:
    images: list[Image.Image]
    pause: float = 0.0          # seconds between cuts


# ── payload helpers ───────────────────────────────────────────────

def _num(payload, key, default, cast=float, lo=None, hi=None):
    v = payload.get(key)
    if v is None or v == "":
        return default
    try:
        v = cast(v)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number")
    if lo is not None and v < lo or hi is not None and v > hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return v


def _bool(v, default=True):
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    return str(v).lower() not in ("0", "false", "no", "off")


def fetch(url: str) -> bytes:
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise ValueError("image_url must be an http(s) URL")
    # Some image hosts (MoMA's media server) 403 without a browser User-Agent.
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        data = r.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("image is larger than 20 MB")
    return data


def _image_bytes(payload, data):
    if data is not None:
        return data
    if not payload.get("image_url"):
        raise ValueError("payload needs image_url")
    return fetch(payload["image_url"])


def _dither_opts(payload):
    mode = payload.get("dither") or None
    if mode and mode not in image_printer._MODES:
        raise ValueError(f"dither must be one of {', '.join(image_printer._MODES)}")
    return dict(
        mode=mode,
        dot_size=_num(payload, "dot_size", None, int, 1, 64),
        contrast=_num(payload, "contrast", None, float, 0, 10),
        brightness=_num(payload, "brightness", None, float, 0, 10),
        sharpness=_num(payload, "sharpness", None, float, 0, 10),
        blur=_num(payload, "blur", None, float, 0, 500),
    )


# ── templates ─────────────────────────────────────────────────────

def uploaded_fonts(cfg) -> list[str]:
    d = cfg.get("_fonts_dir")
    if not d or not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.lower().endswith(FONT_EXTS))


def _font_style(cfg, payload, name):
    """A markdown style built from uploaded fonts: `name` for text, optional
    `heading_font` for headings and bold, sizes scaled from `size`."""
    fonts = uploaded_fonts(cfg)
    heading = payload.get("heading_font") or name
    for f in (name, heading):
        if f not in fonts:
            raise ValueError(f"unknown style or font '{f}'")
    body, head = (os.path.join(cfg["_fonts_dir"], f) for f in (name, heading))
    size = _num(payload, "size", 22, int, 6, 400)
    return {"font_word": head, "font_bold": head, "font_body": body,
            "font_cite": body, "font_date": body,
            "size_word": round(size * 1.6), "size_body": size,
            "size_cite": round(size * 0.85), "size_date": round(size * 0.75),
            "line_spacing": 1.4, "gap_after_word": round(size * 1.3),
            "gap_before_cite": size, "margin": 20, "paper_px": cfg.get("paper_px", 576)}


def markdown(cfg, payload, data=None) -> Plan:
    text = payload.get("body") or payload.get("markdown") or payload.get("text")
    if not text or not str(text).strip():
        raise ValueError("markdown needs body")
    style = payload.get("style") or "dictionary"
    if style not in STYLES:
        cfg = {**cfg, style: _font_style(cfg, payload, style)}
    img = md_renderer.render_markdown(str(text), cfg, _bool(payload.get("show_date")), style)
    return Plan([img])


def image(cfg, payload, data=None) -> Plan:
    raw = _image_bytes(payload, data)
    return Plan([image_printer.process_image(io.BytesIO(raw), cfg, **_dither_opts(payload))])


def _caption_block(lines, width, size):
    font = ImageFont.truetype(resolve_font_path(CAPTION_FONT), size)
    line_h, inset = round(size * 1.4), 10
    block = Image.new("1", (width, inset * 2 + line_h * len(lines)), 1)
    d = ImageDraw.Draw(block)
    for i, line in enumerate(lines):
        d.text((width // 2, inset + i * line_h), line, 0, font=font, anchor="ma")
    return block


def _decorate(strips, gap, padding, lines, position, size):
    """Stack strips with gap, pad top/bottom, add the caption (like the old workbench)."""
    width = max(s.width for s in strips)
    cap = _caption_block(lines, width, size) if lines else None
    top = padding + (cap.height if cap and position == "above" else 0)
    body = sum(s.height for s in strips) + gap * (len(strips) - 1)
    bottom = padding + (cap.height if cap and position == "below" else 0)
    out = Image.new("1", (width, top + body + bottom), 1)
    if cap and position == "above":
        out.paste(cap, (0, padding))
    y = top
    for s in strips:
        out.paste(s, (0, y))
        y += s.height + gap
    if cap and position == "below":
        out.paste(cap, (0, top + body))
    return out


def slices(cfg, payload, data=None) -> Plan:
    raw = _image_bytes(payload, data)
    count = _num(payload, "count", 10, int, 1, 100)
    direction = payload.get("direction") or "vertical"
    if direction not in ("vertical", "horizontal"):
        raise ValueError("direction must be vertical or horizontal")
    mode = payload.get("mode") or "separate"
    if mode not in ("separate", "single"):
        raise ValueError("mode must be separate or single")
    if mode == "single" and direction != "horizontal":
        raise ValueError("single print mode is horizontal only")
    gap = _num(payload, "gap", 40, int, 0, 5000)
    padding = _num(payload, "padding", 100, int, 0, 5000)
    pause = _num(payload, "pause", 1.0, float, 0, 600)
    lines = [l for l in str(payload.get("caption") or "").splitlines() if l.strip()]
    position = payload.get("caption_position") or "below"
    size = _num(payload, "caption_size", 14, int, 6, 200)
    paper = cfg.get("paper_px", 576)

    cut = image_slicer.slice_vertical if direction == "vertical" else image_slicer.slice_horizontal
    strips = [image_printer.dither(s, cfg, **_dither_opts(payload))
              for s in cut(io.BytesIO(raw), count, paper)]
    if mode == "single":
        return Plan([_decorate(strips, gap, padding, lines, position, size)])
    return Plan([_decorate([s], 0, padding, lines, position, size) for s in strips], pause)


def showmemo_card(cfg, payload, data=None) -> Plan:
    oid = payload.get("object_id")
    if oid is None or not str(oid).isdigit():
        raise ValueError("showmemo needs a numeric object_id")
    work = {"ObjectID": int(oid), "Title": payload.get("title"),
            "Artist": payload.get("artist"), "Date": payload.get("date")}
    raw = _image_bytes(payload, data)
    sm = cfg.get("showmemo", {})
    # The nth download of a work prints it in n strips (see showmemo.py).
    n = _num(payload, "times_before", 0, int, 0) + 1
    if sm.get("max_pieces"):
        n = min(n, int(sm["max_pieces"]))
    pieces = showmemo.make_pieces(work, raw, showmemo.stamp_text(), n, sm.get("variant", "id"))
    return Plan([card for card, _note in pieces])


TEMPLATES = {"markdown": markdown, "image": image, "slices": slices, "showmemo": showmemo_card}


def render(cfg, template, payload, data=None) -> Plan:
    if template not in TEMPLATES:
        raise ValueError(f"unknown template '{template}'")
    return TEMPLATES[template](cfg, payload or {}, data)
