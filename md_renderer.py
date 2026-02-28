"""
Markdown-to-image renderer for thermal printing.

Parses a subset of markdown and renders it as a 1-bit image
using configurable fonts (same settings as the dictionary template).

Supported syntax:
    # Heading 1        → bold, large (word size)
    ## Heading 2       → bold, body size
    **bold text**      → bold inline
    *italic text*      → underlined inline
    - list item        → indented with dash
    > blockquote       → indented block
    ---                → dotted separator
    regular text       → thin body font
    blank line         → vertical gap
"""

import os
import re
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_FONT_THIN = os.path.join(_FONTS_DIR, "Burra-Thin.ttf")
_FONT_BOLD = os.path.join(_FONTS_DIR, "Burra-Bold.ttf")


def _resolve_font_path(path):
    if os.path.isabs(path):
        return path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), path)


def _load_font(path, size, index=0):
    """Load a font, supporting both .ttf and .ttc (collection) files."""
    resolved = _resolve_font_path(path)
    return ImageFont.truetype(resolved, size=size, index=index)


# Inline pattern: matches **bold** and *italic* spans
_INLINE_RE = re.compile(r"(\*\*(.+?)\*\*|\*(.+?)\*)")


def _parse_inline(text):
    """
    Parse inline markdown into segments.
    Returns list of (text, style) where style is 'bold', 'italic', or 'normal'.
    """
    segments = []
    last = 0
    for m in _INLINE_RE.finditer(text):
        # Text before this match
        if m.start() > last:
            segments.append((text[last:m.start()], "normal"))
        if m.group(2) is not None:
            segments.append((m.group(2), "bold"))
        elif m.group(3) is not None:
            segments.append((m.group(3), "italic"))
        last = m.end()
    if last < len(text):
        segments.append((text[last:], "normal"))
    return segments


def _parse_md(text):
    """
    Parse markdown text into a list of blocks.
    Each block is a dict with 'type' and content fields.
    """
    blocks = []
    for line in text.split("\n"):
        stripped = line.strip()

        if not stripped:
            blocks.append({"type": "blank"})
        elif stripped.startswith("## "):
            blocks.append({"type": "h2", "text": stripped[3:]})
        elif stripped.startswith("# "):
            blocks.append({"type": "h1", "text": stripped[2:]})
        elif re.match(r"^-{3,}$", stripped):
            blocks.append({"type": "separator"})
        elif stripped.startswith("- "):
            blocks.append({"type": "list", "text": stripped[2:]})
        elif stripped.startswith("> "):
            blocks.append({"type": "quote", "text": stripped[2:]})
        else:
            blocks.append({"type": "paragraph", "text": stripped})

    return blocks


def render_markdown(md_text: str, config: dict = None, show_date: bool = True, style: str = "dictionary"):
    """
    Render markdown text to a PIL Image for thermal printing.
    style: config section to use for fonts/layout ('dictionary', 'helvetica', etc.)
    Returns a PIL Image.
    """
    cfg = (config or {}).get(style, {})

    paper_px = cfg.get("paper_px", 576)
    margin = cfg.get("margin", 20)
    line_spacing = cfg.get("line_spacing", 1.4)
    gap_after_word = cfg.get("gap_after_word", 30)

    sz_h1 = cfg.get("size_word", 32)
    sz_body = cfg.get("size_body", 20)
    sz_h2 = sz_body
    sz_cite = cfg.get("size_cite", 18)
    sz_date = cfg.get("size_date", 16)

    usable = paper_px - margin * 2

    # Load fonts (with .ttc index support)
    font_h1 = _load_font(cfg.get("font_word", _FONT_BOLD), sz_h1, cfg.get("font_word_index", 0))
    font_h2 = _load_font(cfg.get("font_word", _FONT_BOLD), sz_h2, cfg.get("font_word_index", 0))
    font_body = _load_font(cfg.get("font_body", _FONT_THIN), sz_body, cfg.get("font_body_index", 0))
    font_bold = _load_font(cfg.get("font_bold", cfg.get("font_word", _FONT_BOLD)), sz_body, cfg.get("font_bold_index", cfg.get("font_word_index", 0)))
    font_cite = _load_font(cfg.get("font_cite", _FONT_THIN), sz_cite, cfg.get("font_cite_index", 0))
    font_date = _load_font(cfg.get("font_date", _FONT_THIN), sz_date, cfg.get("font_date_index", 0))

    scratch = ImageDraw.Draw(Image.new("1", (1, 1)))

    def text_width(text, font):
        return scratch.textbbox((0, 0), text, font=font)[2]

    def wrap_text(text, font, max_w):
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if text_width(test, font) > max_w and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)
        return lines or [""]

    def wrap_segments(segments, fonts, max_w):
        """
        Word-wrap a list of (text, style) segments, returning rows.
        Each row is a list of (text, style) segments that fit within max_w.
        """
        # Flatten segments into words with styles
        words = []
        for text, style in segments:
            for w in text.split():
                words.append((w, style))

        rows = []
        current_row = []
        current_w = 0
        for word, style in words:
            font = fonts[style]
            ww = text_width(word + " ", font)
            if current_w + ww > max_w and current_row:
                rows.append(current_row)
                current_row = []
                current_w = 0
            current_row.append((word + " ", style))
            current_w += ww
        if current_row:
            rows.append(current_row)
        return rows or [[("", "normal")]]

    # Style -> font mapping
    style_fonts = {
        "normal": font_body,
        "bold": font_bold,
        "italic": font_body,  # drawn with underline
    }

    blocks = _parse_md(md_text)

    # --- Two-pass: measure then draw ---
    # Build a list of draw operations: (y, type, data)
    ops = []
    y = margin

    for block in blocks:
        btype = block["type"]

        if btype == "blank":
            y += int(sz_body * 0.6)

        elif btype == "h1":
            for line in wrap_text(block["text"], font_h1, usable):
                ops.append((y, "text", line, font_h1, margin))
                y += int(sz_h1 * line_spacing)
            y += gap_after_word

        elif btype == "h2":
            for line in wrap_text(block["text"], font_h2, usable):
                ops.append((y, "text", line, font_h2, margin))
                y += int(sz_h2 * line_spacing)
            y += int(sz_body * 0.3)

        elif btype == "separator":
            ops.append((y, "separator", None, font_date, margin))
            y += int(sz_date * line_spacing)

        elif btype == "list":
            segments = _parse_inline(block["text"])
            indent = margin + 20
            # Draw dash with body font
            dash_w = text_width("- ", font_body)
            rows = wrap_segments(segments, style_fonts, usable - 20 - dash_w)
            for i, row in enumerate(rows):
                if i == 0:
                    ops.append((y, "text", "- ", font_body, indent - dash_w))
                ops.append((y, "segments", row, style_fonts, indent))
                y += int(sz_body * line_spacing)

        elif btype == "quote":
            segments = _parse_inline(block["text"])
            indent = margin + 24
            rows = wrap_segments(segments, style_fonts, usable - 24)
            for row in rows:
                # Draw a thin bar for the quote
                ops.append((y, "quote_bar", None, None, margin + 8))
                ops.append((y, "segments", row, style_fonts, indent))
                y += int(sz_body * line_spacing)
            y += int(sz_body * 0.2)

        elif btype == "paragraph":
            segments = _parse_inline(block["text"])
            rows = wrap_segments(segments, style_fonts, usable)
            for row in rows:
                ops.append((y, "segments", row, style_fonts, margin))
                y += int(sz_body * line_spacing)

    # Date at bottom
    if show_date:
        y += 10
        ops.append((y, "separator", None, font_date, margin))
        y += int(sz_date * line_spacing) + 2
        now = datetime.now().strftime("%Y-%m-%d  %H:%M")
        ops.append((y, "text", now, font_date, margin))
        y += int(sz_date * line_spacing)

    total_h = y + margin

    # --- Draw ---
    img = Image.new("1", (paper_px, total_h), 1)
    draw = ImageDraw.Draw(img)

    for op in ops:
        oy = op[0]
        kind = op[1]

        if kind == "text":
            text, font, x = op[2], op[3], op[4]
            draw.text((x, oy), text, font=font, fill=0)

        elif kind == "segments":
            row, fonts_map, x = op[2], op[3], op[4]
            cx = x
            for seg_text, style in row:
                font = fonts_map[style]
                draw.text((cx, oy), seg_text, font=font, fill=0)
                w = text_width(seg_text, font)
                # Underline for italic
                if style == "italic":
                    uh = oy + sz_body + 2
                    draw.line([(cx, uh), (cx + w - 4, uh)], fill=0, width=1)
                cx += w

        elif kind == "separator":
            font = op[3]
            x = op[4]
            dot_w = text_width(". ", font) or 8
            dots = ". " * (usable // dot_w)
            draw.text((x, oy), dots.strip(), font=font, fill=0)

        elif kind == "quote_bar":
            x = op[4]
            draw.line([(x, oy), (x, oy + sz_body)], fill=0, width=2)

    return img
