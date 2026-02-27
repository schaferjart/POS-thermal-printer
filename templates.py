"""
Receipt templates — reusable print layouts that accept structured data.
"""

from datetime import datetime
from printer_core import Formatter


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
