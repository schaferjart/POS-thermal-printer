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
from helpers import resolve_font_path, wrap_text as _helpers_wrap_text, FONT_THIN, FONT_BOLD


def _hard_wrap(text, font, max_w, text_width_fn):
    """Wrap text by character count — cuts mid-word when the line is full."""
    lines = []
    current = ""
    for ch in text:
        test = current + ch
        if text_width_fn(test, font) > max_w and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    return lines or [""]


def _hard_wrap_segments(segments, fonts, max_w, text_width_fn):
    """Hard-wrap styled segments by character, preserving style per character."""
    # Flatten to (char, style) pairs
    chars = []
    for text, style in segments:
        for ch in text:
            chars.append((ch, style))

    rows = []
    current_row = []
    current_w = 0
    for ch, style in chars:
        font = fonts[style]
        cw = text_width_fn(ch, font)
        if current_w + cw > max_w and current_row:
            rows.append(_merge_char_row(current_row))
            current_row = []
            current_w = 0
        current_row.append((ch, style))
        current_w += cw
    if current_row:
        rows.append(_merge_char_row(current_row))
    return rows or [[("", "normal")]]


def _merge_char_row(char_row):
    """Merge consecutive (char, style) pairs with the same style into segments."""
    if not char_row:
        return [("", "normal")]
    merged = []
    current_text = char_row[0][0]
    current_style = char_row[0][1]
    for ch, style in char_row[1:]:
        if style == current_style:
            current_text += ch
        else:
            merged.append((current_text, current_style))
            current_text = ch
            current_style = style
    merged.append((current_text, current_style))
    return merged


def _load_font(path, size, index=0):
    """Load a font, supporting both .ttf and .ttc (collection) files.
    Falls back to Linux system fonts when macOS fonts aren't available."""
    resolved = resolve_font_path(path)
    if os.path.exists(resolved):
        return ImageFont.truetype(resolved, size=size, index=index)

    is_bold = index == 1

    # Fallback: map macOS system fonts to Linux equivalents
    basename = os.path.basename(resolved)
    if basename == "HelveticaNeue.ttc":
        linux_font = "DejaVuSans-Bold.ttf" if is_bold else "DejaVuSans.ttf"
        for search_dir in ("/usr/share/fonts/truetype/dejavu",
                           "/usr/share/fonts/TTF",
                           "/usr/share/fonts/dejavu-sans-fonts"):
            candidate = os.path.join(search_dir, linux_font)
            if os.path.exists(candidate):
                print(f"[md_renderer] Font fallback: {resolved} → {candidate}")
                return ImageFont.truetype(candidate, size=size)

    # Last resort: bundled fonts
    fallback = FONT_BOLD if is_bold else FONT_THIN
    if os.path.exists(fallback):
        print(f"[md_renderer] Font fallback: {resolved} → {fallback}")
        return ImageFont.truetype(fallback, size=size)

    raise FileNotFoundError(f"Font not found: {resolved} (no fallback available)")


# Inline patterns: **bold**, *italic*, ~~strikethrough~~, `code`
_INLINE_RE = re.compile(
    r"(\*\*(.+?)\*\*"        # **bold**
    r"|~~(.+?)~~"             # ~~strikethrough~~
    r"|`(.+?)`"               # `code`
    r"|\*(.+?)\*)"            # *italic*
)


def _parse_inline(text):
    """
    Parse inline markdown into segments.
    Returns list of (text, style) where style is 'bold', 'italic',
    'strikethrough', 'code', or 'normal'.
    """
    segments = []
    last = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > last:
            segments.append((text[last:m.start()], "normal"))
        if m.group(2) is not None:
            segments.append((m.group(2), "bold"))
        elif m.group(3) is not None:
            segments.append((m.group(3), "strikethrough"))
        elif m.group(4) is not None:
            segments.append((m.group(4), "code"))
        elif m.group(5) is not None:
            segments.append((m.group(5), "italic"))
        last = m.end()
    if last < len(text):
        segments.append((text[last:], "normal"))
    return segments


def _parse_md(text):
    """
    Parse markdown text into a list of blocks.
    Each block is a dict with 'type' and content fields.
    Preserves leading indentation as 'indent' level (number of leading spaces/tabs).
    """
    blocks = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Count indent: each tab = 4 spaces
        indent = len(line) - len(line.lstrip())
        indent += line[:len(line) - len(line.lstrip())].count("\t") * 3  # tabs already counted as 1

        if not stripped:
            blocks.append({"type": "blank"})
        elif stripped.startswith("## "):
            blocks.append({"type": "h2", "text": stripped[3:], "indent": indent})
        elif stripped.startswith("# "):
            blocks.append({"type": "h1", "text": stripped[2:], "indent": indent})
        elif re.match(r"^-{3,}$", stripped):
            blocks.append({"type": "separator"})
        elif stripped.startswith("- "):
            blocks.append({"type": "list", "text": stripped[2:], "indent": indent})
        elif stripped.startswith("> "):
            blocks.append({"type": "quote", "text": stripped[2:], "indent": indent})
        else:
            blocks.append({"type": "paragraph", "text": stripped, "indent": indent})

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
    font_h1 = _load_font(cfg.get("font_word", FONT_BOLD), sz_h1, cfg.get("font_word_index", 0))
    font_h2 = _load_font(cfg.get("font_word", FONT_BOLD), sz_h2, cfg.get("font_word_index", 0))
    font_body = _load_font(cfg.get("font_body", FONT_THIN), sz_body, cfg.get("font_body_index", 0))
    font_bold = _load_font(cfg.get("font_bold", cfg.get("font_word", FONT_BOLD)), sz_body, cfg.get("font_bold_index", cfg.get("font_word_index", 0)))
    font_cite = _load_font(cfg.get("font_cite", FONT_THIN), sz_cite, cfg.get("font_cite_index", 0))
    font_date = _load_font(cfg.get("font_date", FONT_THIN), sz_date, cfg.get("font_date_index", 0))

    scratch = ImageDraw.Draw(Image.new("1", (1, 1)))

    def text_width(text, font):
        return scratch.textbbox((0, 0), text, font=font)[2]

    hard_wrap = cfg.get("hard_wrap", False)

    def wrap_text(text, font, max_w):
        if hard_wrap:
            return _hard_wrap(text, font, max_w, text_width)
        return _helpers_wrap_text(text, font, max_w, scratch)

    def wrap_segments(segments, fonts, max_w):
        """
        Wrap a list of (text, style) segments into rows.
        In hard_wrap mode, cuts at character boundaries.
        """
        if hard_wrap:
            return _hard_wrap_segments(segments, fonts, max_w, text_width)
        # Soft wrap: break at word boundaries
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
        "italic": font_body,       # drawn with underline
        "strikethrough": font_body,  # drawn with line through middle
        "code": font_body,          # drawn with background box
    }

    blocks = _parse_md(md_text)

    # --- Two-pass: measure then draw ---
    # Build a list of draw operations: (y, type, data)
    ops = []
    y = margin

    # Pixels per indent level (roughly one space width in body font)
    indent_px = text_width("  ", font_body)

    for block in blocks:
        btype = block["type"]
        # Convert source indentation to pixel offset
        src_indent = block.get("indent", 0)
        px_offset = int(src_indent / 2) * indent_px if src_indent else 0

        if btype == "blank":
            y += int(sz_body * 0.6)

        elif btype == "h1":
            x0 = margin + px_offset
            for line in wrap_text(block["text"], font_h1, usable - px_offset):
                ops.append((y, "text", line, font_h1, x0))
                y += int(sz_h1 * line_spacing)
            y += gap_after_word

        elif btype == "h2":
            x0 = margin + px_offset
            for line in wrap_text(block["text"], font_h2, usable - px_offset):
                ops.append((y, "text", line, font_h2, x0))
                y += int(sz_h2 * line_spacing)
            y += int(sz_body * 0.3)

        elif btype == "separator":
            ops.append((y, "separator", None, font_date, margin))
            y += int(sz_date * line_spacing)

        elif btype == "list":
            segments = _parse_inline(block["text"])
            indent = margin + 20 + px_offset
            dash_w = text_width("- ", font_body)
            rows = wrap_segments(segments, style_fonts, usable - 20 - px_offset - dash_w)
            for i, row in enumerate(rows):
                if i == 0:
                    ops.append((y, "text", "- ", font_body, indent - dash_w))
                ops.append((y, "segments", row, style_fonts, indent))
                y += int(sz_body * line_spacing)

        elif btype == "quote":
            segments = _parse_inline(block["text"])
            indent = margin + 24 + px_offset
            rows = wrap_segments(segments, style_fonts, usable - 24 - px_offset)
            for row in rows:
                ops.append((y, "quote_bar", None, None, margin + 8 + px_offset))
                ops.append((y, "segments", row, style_fonts, indent))
                y += int(sz_body * line_spacing)
            y += int(sz_body * 0.2)

        elif btype == "paragraph":
            segments = _parse_inline(block["text"])
            x0 = margin + px_offset
            rows = wrap_segments(segments, style_fonts, usable - px_offset)
            for row in rows:
                ops.append((y, "segments", row, style_fonts, x0))
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
                if style == "italic":
                    # Underline
                    uh = oy + sz_body + 2
                    draw.line([(cx, uh), (cx + w - 4, uh)], fill=0, width=1)
                elif style == "strikethrough":
                    # Line through the middle of text
                    sh = oy + int(sz_body * 0.55)
                    draw.line([(cx, sh), (cx + w - 4, sh)], fill=0, width=1)
                elif style == "code":
                    # Dark background with white text effect (invert a box)
                    pad = 2
                    box = (cx - pad, oy + 2, cx + w - 2, oy + sz_body + pad)
                    draw.rectangle(box, fill=0)
                    draw.text((cx, oy), seg_text, font=font, fill=1)
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
