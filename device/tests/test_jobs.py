"""Every template renders, and the ESC/POS output is a printable job."""

import io

import pytest
from PIL import Image

import jobs
import printerd


def _png(w=800, h=600):
    img = Image.new("RGB", (w, h))
    for x in range(w):                       # a gradient, so dithering has work to do
        for y in range(0, h, 50):
            img.putpixel((x, y), (x % 256, 100, 200))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


CFG = printerd.CFG


@pytest.mark.parametrize("style", jobs.STYLES)
def test_markdown_styles(style):
    plan = jobs.render(CFG, "markdown", {"body": "# Hi\n\nSome **bold** text.", "style": style})
    assert len(plan.images) == 1 and plan.images[0].width == 576


@pytest.mark.parametrize("mode", ["floyd", "bayer", "halftone"])
def test_image_dither(mode):
    plan = jobs.render(CFG, "image", {"dither": mode, "blur": "2"}, _png())
    img = plan.images[0]
    assert img.mode == "1" and img.width == 576


def test_slices_separate_and_single():
    plan = jobs.render(CFG, "slices", {"count": "3", "caption": "hello\nworld"}, _png())
    assert len(plan.images) == 3 and plan.pause == 1.0
    plan = jobs.render(CFG, "slices", {"count": 4, "direction": "horizontal", "mode": "single",
                                       "padding": 0, "gap": 10}, _png(576, 400))
    assert len(plan.images) == 1 and plan.images[0].height == 400 + 3 * 10


def test_showmemo_repeat_prints_strips():
    payload = {"object_id": 13802, "title": "Ada", "artist": "Alex Katz", "date": "1990"}
    assert len(jobs.render(CFG, "showmemo", payload, _png()).images) == 1
    assert len(jobs.render(CFG, "showmemo", {**payload, "times_before": 1}, _png()).images) == 2


@pytest.mark.parametrize("bad", [
    ("markdown", {}), ("markdown", {"body": "x", "style": "comic"}),
    ("image", {"dither": "nope"}), ("slices", {"count": 0}),
    ("slices", {"mode": "single"}), ("showmemo", {"title": "x"}), ("fax", {}),
])
def test_bad_payloads_raise(bad):
    template, payload = bad
    with pytest.raises(ValueError):
        jobs.render(CFG, template, payload, _png())


def test_fetch_rejects_non_http():
    with pytest.raises(ValueError):
        jobs.fetch("file:///etc/passwd")


def test_escpos_bytes_scale_and_cut():
    wide = Image.new("L", (1200, 300), 128)
    assert printerd.fit(wide).size == (576, 144)
    data = printerd.escpos_bytes([wide, Image.new("1", (100, 50), 0)])
    assert data.startswith(b"\x1b@")          # ESC @ init
    assert b"\x1dV" in data[-8:]              # GS V cut at the end


def test_font_upload_and_use(tmp_path, monkeypatch):
    monkeypatch.setattr(printerd, "FONTS", tmp_path)
    monkeypatch.setitem(printerd.CFG, "_fonts_dir", str(tmp_path))
    c = printerd.app.test_client()
    font = open("fonts/Inter-Bold.ttf", "rb").read()
    r = c.post("/fonts", data={"file": (io.BytesIO(font), "My Font.ttf")})
    assert r.status_code == 200 and r.json["font"] == "My-Font.ttf"
    r = c.post("/fonts", data={"file": (io.BytesIO(b"not a font"), "x.ttf")})
    assert r.status_code == 400
    r = c.post("/fonts", data={"file": (io.BytesIO(font), "../evil.ttf")})
    assert r.status_code == 200 and (tmp_path / "evil.ttf").exists()   # basename only
    assert "My-Font.ttf" in c.get("/fonts").json["uploaded"]
    plan = jobs.render(printerd.CFG, "markdown", {"body": "# Hi\n\ntext", "style": "My-Font.ttf", "size": 30})
    assert plan.images[0].width == 576
    with pytest.raises(ValueError):
        jobs.render(printerd.CFG, "markdown", {"body": "x", "style": "Missing.ttf"})
    assert c.delete("/fonts/My-Font.ttf").status_code == 200
    assert c.delete("/fonts/My-Font.ttf").status_code == 404


def test_slip_has_qr(monkeypatch):
    printed = []
    monkeypatch.setattr(printerd, "print_plan", lambda plan, title: printed.append(plan))
    printerd.slip("# Hello\n\ntext", "t")
    img = printed[0].images[0]
    assert img.width == 576 and img.height > 300     # text + QR + url
