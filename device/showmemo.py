"""The `showmemo` print template: a MoMA artwork as an 80mm thermal card.

Moved from schaferjart/showmemo-printer (render.py). Sending is no longer done
here: the printer service turns the returned images into print jobs.

Two layouts, both without a separator rule:
  title   - QR sits beside the catalogue block, stamp full width beneath
  header  - QR alone top-right, catalogue and stamp beneath the image
"""
from __future__ import annotations

import io
import json
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import qrcode
from qrcode.constants import ERROR_CORRECT_L
from PIL import Image, ImageDraw, ImageFont, ImageOps

# --- printer geometry -------------------------------------------------------
WIDTH = 576                  # 80mm printable area, in dots
MARGIN = 28                  # no full bleed
INNER = WIDTH - 2 * MARGIN

# --- typography (fixed sizes; long text wraps, it never shrinks) -------------
# Liberation Sans is metric-compatible with Arial, which the cards were designed
# in, and ships in the repo so the Mac and every printer render identically.
# ponytail: no narrow face bundled; the one date line uses the regular face.
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts") + "/"
REG, BOLD = "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"
NARROW = REG
S_TITLE, S_ARTIST, S_DATE, S_STAMP = 32, 28, 26, 25
RULE_ABOVE, RULE_BELOW = 24, 18   # breathing room either side of a separator
S_ID = S_STAMP                    # bare ObjectID: quiet metadata, matches the stamp

# --- ink budget -------------------------------------------------------------
# Artworks are printed as they are. Every automatic correction tried here made
# the cards worse: a dark work bleached to grey, a pale one forced to a density
# it never had. Autocontrast and dithering are enough, and what comes out looks
# like the work rather than like an algorithm's opinion of it.
#
# CARD_MAX is a safety valve for the print head, not an aesthetic control. It is
# disabled. Set it to a fraction (0.75 would be a near-solid card) to have
# make_card lighten anything above that; nothing in MoMA's collection has come
# close in testing - the darkest composed card measured 46%.
CARD_MAX = None

# --- linking ----------------------------------------------------------------
# Only used by the QR variants, which are not the default. Set SITE_PERMALINK
# in the environment to point at the site.
PERMALINK = os.environ.get("SITE_PERMALINK", "https://example.invalid/?id={}")
QR_MODULE = 3                # 3px modules scan reliably on this printer

MOMA = (40.7614, -73.9776)
WMO = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Showers",
    81: "Showers", 82: "Violent showers", 95: "Thunderstorm",
    96: "Thunderstorm, hail", 99: "Thunderstorm, hail",
}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_DIR + name, size)


# --- moment -----------------------------------------------------------------
def season(dt: datetime) -> str:
    return ("Winter", "Spring", "Summer", "Autumn")[((dt.month % 12) // 3)]


def weather_now() -> tuple[float, str]:
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={MOMA[0]}"
           f"&longitude={MOMA[1]}&current=temperature_2m,weather_code"
           f"&timezone=America%2FNew_York")
    cur = json.load(urllib.request.urlopen(url, timeout=20))["current"]
    return cur["temperature_2m"], WMO.get(cur["weather_code"], "—")


def stamp_text(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(ZoneInfo("America/New_York"))
    try:
        temp, sky = weather_now()
    except Exception:            # no weather is better than no card
        return f"{season(dt)} {dt:%Y}, {dt:%H:%M}"
    return f"{season(dt)} {dt:%Y}, {dt:%H:%M}, {round(temp)}°C, {sky}"


# --- image ------------------------------------------------------------------
def coverage(im: Image.Image) -> float:
    h = im.convert("1").histogram()
    return h[0] / (h[0] + h[255])


def _gamma(im: Image.Image, g: float) -> Image.Image:
    """g > 1 darkens (more ink); g < 1 lightens (less ink)."""
    return im.point(lambda p: int(255 * ((p / 255.0) ** g)))


def _local_contrast(im: Image.Image, tiles: int = 8, blend: float = 0.65):
    out = im.copy()
    tw, th = im.size[0] // tiles, im.size[1] // tiles
    for i in range(tiles):
        for j in range(tiles):
            box = (i * tw, j * th,
                   (i + 1) * tw if i < tiles - 1 else im.size[0],
                   (j + 1) * th if j < tiles - 1 else im.size[1])
            out.paste(ImageOps.autocontrast(im.crop(box), cutoff=2), box)
    return Image.blend(im, out, blend)


def fetch_image(url: str, timeout: int = 45) -> bytes:
    """The media server 403s without a browser User-Agent. Referer is not
    checked - tested with none, a matching origin and an unrelated one, all
    200 - so none is sent."""
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"),
        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
    })
    return urllib.request.urlopen(req, timeout=timeout).read()


def prepare(data: bytes, width: int = INNER) -> Image.Image:
    """Greyscale, autocontrast, fit to width. No tone correction - see CARD_MAX."""
    im = ImageOps.autocontrast(Image.open(io.BytesIO(data)).convert("L"), cutoff=1)
    h = round(im.size[1] * width / im.size[0])
    return im.resize((width, h), Image.LANCZOS)


def qr_for(object_id) -> Image.Image:
    q = qrcode.QRCode(error_correction=ERROR_CORRECT_L, border=2, box_size=QR_MODULE)
    q.add_data(PERMALINK.format(object_id))
    q.make(fit=True)
    return q.make_image(fill_color="black", back_color="white").convert("L")


# --- layout -----------------------------------------------------------------
def wrap(draw, text: str, fnt, maxw: int) -> list[str]:
    lines, cur = [], ""
    for word in (text or "").split(" "):
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def render(work: dict, art: Image.Image, stamp: str, variant: str = "title",
           piece: tuple[int, int] | None = None):
    """Compose one card. `piece` is (index, total) for a chunked print: it adds
    an `i/n` mark top-left, and only the first piece carries the catalogue block
    and the moment - the rest are the artwork and their number, so the pieces
    read as one work cut up rather than as n cards of the same thing."""
    qr = qr_for(work["ObjectID"])
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    title, artist = work.get("Title") or "Untitled", work.get("Artist") or ""
    date = work.get("Date") or ""
    lead = piece is None or piece[0] == 1

    cat_w = INNER - qr.size[0] - 24 if variant == "title" else INNER
    tl = wrap(probe, title, font(BOLD, S_TITLE), cat_w) if lead else []
    al = wrap(probe, artist, font(REG, S_ARTIST), cat_w) if lead else []
    sl = wrap(probe, stamp, font(REG, S_STAMP), INNER) if lead else []

    cat_h = (len(tl) * (S_TITLE + 6) + len(al) * (S_ARTIST + 6) + (S_DATE + 6)
             if lead else 0)
    stamp_h = len(sl) * (S_STAMP + 6)
    use_id = variant.startswith("id")            # bare ObjectID instead of a QR
    is_header = variant.startswith("header") or use_id
    top_rule = variant in ("header-top", "id-top")
    mark_h = S_ID if use_id else qr.size[1]
    head_h = mark_h + (RULE_ABOVE + 2 + RULE_BELOW if top_rule else 20) if is_header else 0
    if piece and not is_header:
        head_h = S_STAMP + 20        # `title` has no header band; i/n needs a line
    body_h = (max(cat_h, qr.size[1]) if variant == "title" else cat_h) if lead else 0
    # Only the first piece closes the artwork with a rule and the catalogue.
    tail_h = (RULE_ABOVE + 2 + RULE_BELOW + body_h + 18 + stamp_h) if lead else 0

    h = MARGIN + head_h + art.size[1] + tail_h + MARGIN
    c = Image.new("L", (WIDTH, int(h)), 255)
    d = ImageDraw.Draw(c)

    def rule(yy):
        d.rectangle([MARGIN, yy, WIDTH - MARGIN, yy + 1], fill=0)

    y = MARGIN
    if piece:
        d.text((MARGIN, y), f"{piece[0]}/{piece[1]}", 0, font=font(REG, S_STAMP))
    if is_header:
        if use_id:
            d.text((WIDTH - MARGIN, y), str(work["ObjectID"]), 0,
                   font=font(REG, S_ID), anchor="ra")
        else:
            c.paste(qr, (WIDTH - MARGIN - qr.size[0], y))
        y += mark_h
        if top_rule:
            y += RULE_ABOVE
            rule(y)
            y += 2 + RULE_BELOW
        else:
            y += 20
    else:
        y += head_h                  # zero unless this is a `title` piece
    c.paste(art, (MARGIN, y))
    if not lead:
        return c
    y += art.size[1] + RULE_ABOVE
    rule(y)
    y += 2 + RULE_BELOW

    if variant == "title":
        c.paste(qr, (WIDTH - MARGIN - qr.size[0], y))
    ty = y
    for line in tl:
        d.text((MARGIN, ty), line, 0, font=font(BOLD, S_TITLE)); ty += S_TITLE + 6
    for line in al:
        d.text((MARGIN, ty), line, 0, font=font(REG, S_ARTIST)); ty += S_ARTIST + 6
    d.text((MARGIN, ty), date, 0, font=font(NARROW, S_DATE))

    y += body_h + 18
    for line in sl:
        d.text((MARGIN, y), line, 0, font=font(REG, S_STAMP)); y += S_STAMP + 6
    return c


def _fit_ink(art: Image.Image, build):
    """Compose with `build(art)`, honouring CARD_MAX. Returns (card, note)."""
    card = build(art)
    if CARD_MAX is None or coverage(card) <= CARD_MAX:
        return card, "as-is"
    g = 1.0
    while coverage(card) > CARD_MAX and g > 0.13:
        g = max(g - 0.08, 0.12)
        card = build(_gamma(art, g))
    return card, f"over safety valve, lightened g={g:.2f}"


def make_card(work: dict, data: bytes, stamp: str, variant: str = "id"):
    """Compose a card. The artwork is printed as it is; CARD_MAX, if set, is a
    print-head safety valve rather than an aesthetic control. Returns (card, note)."""
    return _fit_ink(prepare(data),
                    lambda art: render(work, art, stamp, variant))


# --- chunking ---------------------------------------------------------------
# The nth download of a work prints it in n pieces. The cuts run top to bottom,
# so each piece is a column of the artwork blown up to the full paper width, and
# the pieces are laid side by side to rebuild it. A work downloaded once is one
# card, as before; the fragmentation is what repetition looks like on paper.
def slice_columns(data: bytes, n: int, width: int = INNER) -> list[Image.Image]:
    """Cut the artwork into n columns, each scaled to the full paper width.

    Autocontrast runs on the whole image before cutting, not per column: a tone
    curve fitted to each piece separately would make them disagree at the seams
    and the reassembled work would band. Every column is scaled by the same
    factor, so the pieces line up when laid out.

    Paper cost grows with the square of n - n pieces, each n times taller than
    the single card would have been - which is the point, and worth knowing
    before setting MAX_CHUNKS in poll.py loose.
    """
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    im = ImageOps.autocontrast(Image.open(io.BytesIO(data)).convert("L"), cutoff=1)
    w, h = im.size
    n = min(n, w)                # a column has to be at least one pixel wide
    edges = [round(i * w / n) for i in range(n + 1)]
    cols = []
    for i in range(n):
        col = im.crop((edges[i], 0, edges[i + 1], h))
        ch = round(col.size[1] * width / col.size[0])
        cols.append(col.resize((width, ch), Image.LANCZOS))
    return cols


def make_pieces(work: dict, data: bytes, stamp: str, n: int,
                variant: str = "id") -> list[tuple[Image.Image, str]]:
    """Compose the n cards of a chunked print, in the order they go to paper.

    Returns [(card, note), ...]; n == 1 is exactly make_card, so callers do not
    need to special-case the first download of a work. Fewer than n pieces come
    back only where slice_columns had to clamp n to the artwork's pixel width;
    the i/n marks then count what was actually printed."""
    if n == 1:
        return [make_card(work, data, stamp, variant)]
    cols = slice_columns(data, n)
    total = len(cols)
    return [_fit_ink(col, lambda art, i=i: render(work, art, stamp, variant,
                                                  piece=(i, total)))
            for i, col in enumerate(cols, start=1)]


