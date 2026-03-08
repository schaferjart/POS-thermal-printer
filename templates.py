"""
Print templates — reusable layouts that accept structured data.
"""

from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from printer_core import Formatter
from helpers import resolve_font_path, wrap_text, FONT_THIN, FONT_BOLD


def receipt(fmt: Formatter, data: dict, config: dict):
    """
    Standard receipt template.

    data = {
        "items": [
            {"name": "Coffee", "qty": 2, "price": 5.00},
            {"name": "Croissant", "qty": 1, "price": 3.50},
        ],
        "payment_method": "Card",   # optional
        "receipt_id": "R-00142",    # optional
    }
    """
    tpl = config.get("template", {})
    currency = tpl.get("currency", "EUR")

    # --- Header ---
    for i, line in enumerate(tpl.get("header_lines", [])):
        if i == 0:
            fmt.title(line)
        else:
            fmt.center(line)
    fmt.blank()

    # --- Date/time ---
    if tpl.get("show_datetime", True):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fmt.center(now)

    if data.get("receipt_id"):
        fmt.center(f"Receipt: {data['receipt_id']}")
    fmt.double_line()

    # --- Column headers ---
    fmt.columns(
        ["Item", "Qty", "Price"],
        widths=[28, 6, 14],
        aligns=["l", "r", "r"],
    )
    fmt.line()

    # --- Items ---
    total = 0.0
    for item in data.get("items", []):
        name = item["name"]
        qty = item.get("qty", 1)
        price = item["price"]
        line_total = qty * price
        total += line_total
        fmt.columns(
            [name, str(qty), f"{line_total:.2f} {currency}"],
            widths=[28, 6, 14],
            aligns=["l", "r", "r"],
        )

    fmt.line()
    fmt.left_right_bold("TOTAL", f"{total:.2f} {currency}")

    if data.get("payment_method"):
        fmt.blank()
        fmt.left_right("Payment", data["payment_method"])

    fmt.double_line()

    # --- Footer ---
    fmt.blank()
    for line in tpl.get("footer_lines", []):
        fmt.center(line)

    # --- QR code ---
    if tpl.get("show_qr") and tpl.get("qr_base_url") and data.get("receipt_id"):
        fmt.blank()
        fmt.qr(f"{tpl['qr_base_url']}/{data['receipt_id']}")

    fmt.feed()
    fmt.cut()


def simple_message(fmt: Formatter, text: str, title_text: str = None):
    """
    Print a simple text message — useful for announcements, notes, labels.
    """
    if title_text:
        fmt.title(title_text)
        fmt.blank()
    for line in text.strip().split("\n"):
        fmt.text(line)
    fmt.feed()
    fmt.cut()


def label(fmt: Formatter, heading: str, body_lines: list[str]):
    """
    Print a compact label with a bold heading and body lines.
    """
    fmt.subtitle(heading)
    fmt.line()
    for line in body_lines:
        fmt.text(line)
    fmt.feed()
    fmt.cut()


def two_column_list(fmt: Formatter, title_text: str, rows: list[tuple[str, str]]):
    """
    Print a two-column list (e.g., order summary, inventory check, price list).
    rows = [("Item A", "12.00"), ("Item B", "8.50")]
    """
    fmt.subtitle(title_text)
    fmt.double_line()
    for left, right in rows:
        fmt.left_right(left, right)
    fmt.line()
    fmt.feed()
    fmt.cut()


def _render_dictionary_image(data: dict, config: dict = None):
    """
    Render a dictionary entry as a black-on-white image.
    All layout settings come from config["dictionary"].
    Returns a PIL Image ready to send to the printer.
    """
    cfg = (config or {}).get("dictionary", {})

    paper_px = cfg.get("paper_px", 576)
    margin = cfg.get("margin", 20)
    line_spacing = cfg.get("line_spacing", 1.4)
    gap_after_word = cfg.get("gap_after_word", 30)
    gap_before_cite = cfg.get("gap_before_cite", 20)

    sz_word = cfg.get("size_word", 32)
    sz_body = cfg.get("size_body", 20)
    sz_cite = cfg.get("size_cite", 18)
    sz_date = cfg.get("size_date", 16)

    usable = paper_px - margin * 2

    # Load fonts from config paths (fall back to bundled Burra)
    word_font = ImageFont.truetype(resolve_font_path(cfg.get("font_word", FONT_BOLD)), sz_word)
    body_font = ImageFont.truetype(resolve_font_path(cfg.get("font_body", FONT_THIN)), sz_body)
    cite_font = ImageFont.truetype(resolve_font_path(cfg.get("font_cite", FONT_THIN)), sz_cite)
    date_font = ImageFont.truetype(resolve_font_path(cfg.get("font_date", FONT_THIN)), sz_date)

    # --- Pre-calculate wrapped text ---
    scratch = ImageDraw.Draw(Image.new("1", (1, 1)))

    # Prepare all text blocks
    word_lines = [data["word"]]
    def_lines = wrap_text(data["definition"], body_font, usable, scratch)

    cite_blocks = []
    for cite in data.get("citations", []):
        wrapped = wrap_text(f"- {cite}", cite_font, usable - 10, scratch)
        for i in range(1, len(wrapped)):
            wrapped[i] = f"  {wrapped[i]}"
        cite_blocks.append(wrapped)

    now = datetime.now().strftime("%Y-%m-%d  %H:%M")

    # --- Calculate total height ---
    y = margin
    word_h = int(sz_word * line_spacing) * len(word_lines)
    def_h = int(sz_body * line_spacing) * len(def_lines)
    cite_gap = gap_before_cite if cite_blocks else 0
    cite_h = 0
    for block in cite_blocks:
        cite_h += int(sz_cite * line_spacing) * len(block) + 6
    sep_gap = 16
    date_h = 24

    total_h = (y + word_h + gap_after_word + def_h + cite_gap + cite_h
               + sep_gap + date_h + margin)

    # --- Draw ---
    img = Image.new("1", (paper_px, total_h), 1)
    draw = ImageDraw.Draw(img)

    # Word (bold)
    for line in word_lines:
        draw.text((margin, y), line, font=word_font, fill=0)
        y += int(sz_word * line_spacing)

    y += gap_after_word

    # Definition (thin)
    for line in def_lines:
        draw.text((margin, y), line, font=body_font, fill=0)
        y += int(sz_body * line_spacing)

    # Citations
    if cite_blocks:
        y += cite_gap
        for block in cite_blocks:
            for line in block:
                draw.text((margin + 10, y), line, font=cite_font, fill=0)
                y += int(sz_cite * line_spacing)
            y += 6

    # Dotted separator
    y += sep_gap
    dot_w = scratch.textbbox((0, 0), ". ", font=date_font)[2] or 8
    dots = ". " * (usable // dot_w)
    draw.text((margin, y), dots.strip(), font=date_font, fill=0)
    y += 20

    # Date
    draw.text((margin, y), now, font=date_font, fill=0)

    return img


def dictionary_entry(fmt: Formatter, data: dict, config: dict = None):
    """
    Dictionary / glossary art-print template — rendered as image with custom font.

    data = {
        "word": "Ephemeral",
        "definition": "Lasting for a very short time.",
        "citations": [                          # optional
            "The ephemeral beauty of cherry blossoms.",
            "All fame is ephemeral. — Voltaire"
        ],
        "qr_url": "https://example.com/word",   # optional
    }

    Layout is configured in config.yaml under the "dictionary" key.
    """
    img = _render_dictionary_image(data, config)
    fmt.p.image(img)

    if data.get("qr_url"):
        fmt.p.text("\n")
        fmt.p.qr(data["qr_url"], size=3)

    fmt.feed()
    fmt.cut()


def markdown(fmt: Formatter, md_text: str, config: dict = None, show_date: bool = True, style: str = "dictionary"):
    """
    Print markdown text rendered as an image with custom fonts.
    style: config section name ('dictionary', 'helvetica', etc.)
    """
    from md_renderer import render_markdown
    img = render_markdown(md_text, config, show_date, style)
    fmt.p.image(img)
    fmt.feed()
    fmt.cut()
