import base64
import io

import numpy as np
import pytest
from PIL import Image

import portrait
from conftest import FAKE_LANDMARKS, synthetic_portrait

CROPS = {"pad_top": 0.3, "pad_bottom": 0.8, "center_x": 0.5,
         "zoom_0_width": 0.67, "zoom_1_width": 0.5, "zoom_2_width": 0.3, "zoom_3_width": 0.15}


def png_bytes(img, fmt="PNG"):
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ── crop math ─────────────────────────────────────────────────────

def test_crops_share_height_and_only_width_changes():
    boxes = portrait.crop_boxes((800, 1200), FAKE_LANDMARKS, CROPS)
    face_h = 720 - 240
    top, bottom = round(240 - face_h * 0.3), round(720 + face_h * 0.8)   # 96, 1104
    assert [(b[1], b[3]) for b in boxes] == [(top, bottom)] * 4
    crop_h = bottom - top
    widths = [b[2] - b[0] for b in boxes]
    assert widths == [round(crop_h * r) for r in (0.67, 0.5, 0.3, 0.15)]
    for b, w in zip(boxes, widths):          # centered on the eye midpoint
        assert b[0] == 400 - w // 2


def test_crops_clamp_to_image_edges():
    lm = {**FAKE_LANDMARKS, "forehead_top": (40, 20), "chin": (40, 1150), "face_center_x": 40}
    boxes = portrait.crop_boxes((800, 1200), lm, CROPS)
    for left, top, right, bottom in boxes:
        assert (top, bottom) == (0, 1200)
        assert left >= 0 and right <= 800
    assert boxes[0] == (0, 0, 800, 1200)            # 0.67 * 1200 > 800: full width
    assert boxes[3][0] == 0                          # pushed in from the left edge
    right_lm = {**lm, "face_center_x": 790}
    assert portrait.crop_boxes((800, 1200), right_lm, CROPS)[3][2] == 800


def test_crop_offset_shifts_center_by_image_width_fraction():
    boxes = portrait.crop_boxes((800, 1200), FAKE_LANDMARKS, {**CROPS, "zoom_2_offset": 0.1})
    base = portrait.crop_boxes((800, 1200), FAKE_LANDMARKS, CROPS)
    assert boxes[2][0] - base[2][0] == 80
    assert boxes[2][1:4:2] == base[2][1:4:2]


def test_no_face_uses_full_height_and_center_x():
    boxes = portrait.crop_boxes((800, 1200), None, CROPS)
    assert all((b[1], b[3]) == (0, 1200) for b in boxes)
    assert boxes[3] == (400 - 90, 0, 400 + 90, 1200)


# ── dithering ─────────────────────────────────────────────────────

def bayer_reference(grey):
    """The per-pixel loop from meinungeheuer print-renderer/dithering.py."""
    m = portrait.BAYER_8 // 4
    w, h = grey.size
    src = grey.load()
    out = Image.new("1", (w, h), 1)
    dst = out.load()
    for y in range(h):
        for x in range(w):
            dst[x, y] = 1 if src[x, y] > m[y % 8][x % 8] * 4 else 0
    return out


def test_vectorised_bayer_matches_reference_loop():
    grey = synthetic_portrait(203, 157).convert("L")    # sizes not multiples of 8
    fast, ref = portrait.bayer(grey), bayer_reference(grey)
    assert fast.mode == "1" and fast.size == ref.size
    assert fast.tobytes() == ref.tobytes()


# ── whole pipeline, mocked model + detection ──────────────────────

def test_render_gives_four_1bit_strips_576_wide(cfg):
    styled = synthetic_portrait()
    seen = {}

    def fake_transform(photo, model_cfg):
        seen["photo"] = photo.size
        seen["prompt"] = model_cfg["style_prompt"]
        return styled

    res = portrait.render(png_bytes(synthetic_portrait(3000, 4000), "JPEG"), cfg,
                          transform=fake_transform, detect=lambda img: FAKE_LANDMARKS)
    assert max(seen["photo"]) == cfg["max_input_px"]          # downscaled before the model
    assert "translucent wax" in seen["prompt"]
    assert res["face_detected"] is True
    assert [n for n, _ in res["crops"]] == ["zoom_0", "zoom_1", "zoom_2", "zoom_3"]
    boxes = portrait.crop_boxes(styled.size, FAKE_LANDMARKS, cfg["portrait_crops"])
    for (_, img), (l, t, r, b) in zip(res["crops"], boxes):
        assert img.mode == "1" and img.width == 576
        assert img.height == int((b - t) * 576 / (r - l))
        px = np.asarray(img)
        assert px.any() and not px.all()                          # black and white present


def test_render_reports_missing_face(cfg):
    res = portrait.render(png_bytes(synthetic_portrait()), cfg,
                          transform=lambda p, m: synthetic_portrait(), detect=lambda img: None)
    assert res["face_detected"] is False and len(res["crops"]) == 4


def test_render_rejects_non_image(cfg):
    with pytest.raises(portrait.BadImage):
        portrait.render(b"not an image", cfg, transform=lambda p, m: p, detect=lambda i: None)


# ── model call (requests mocked, no network, no key) ──────────────

class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


def image_message(img):
    url = "data:image/png;base64," + base64.b64encode(png_bytes(img)).decode()
    return {"choices": [{"message": {"content": "", "images": [
        {"type": "image_url", "image_url": {"url": url}}]}}]}


def test_wax_transform_parses_openrouter_image(monkeypatch, cfg):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    sent = {}

    def fake_post(url, json, timeout, headers):
        sent.update(url=url, body=json, headers=headers)
        return FakeResponse(200, image_message(synthetic_portrait(64, 96)))

    monkeypatch.setattr(portrait.requests, "post", fake_post)
    out = portrait.wax_transform(synthetic_portrait(100, 150), cfg["model"])
    assert out.size == (64, 96) and out.mode == "RGB"
    assert sent["body"]["model"] == cfg["model"]["id"]
    assert sent["body"]["modalities"] == ["image", "text"]
    assert sent["headers"]["Authorization"] == "Bearer test-key"


@pytest.mark.parametrize("status,payload", [
    (500, {"error": {"message": "upstream down"}}),
    (200, {"error": {"message": "moderation"}}),
    (200, {"choices": []}),
    (200, {"choices": [{"message": {"content": "I can't do that."}}]}),
    (200, {"choices": [{"message": {"images": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,bm90IGFuIGltYWdl"}}]}}]}),
])
def test_wax_transform_failures_raise(monkeypatch, cfg, status, payload):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(portrait.requests, "post", lambda *a, **k: FakeResponse(status, payload))
    with pytest.raises(portrait.ModelError):
        portrait.wax_transform(synthetic_portrait(100, 150), cfg["model"])


def test_wax_transform_without_key_raises(monkeypatch, cfg):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(portrait.requests, "post", lambda *a, **k: pytest.fail("no call without key"))
    with pytest.raises(portrait.ModelError):
        portrait.wax_transform(synthetic_portrait(100, 150), cfg["model"])


# ── real MediaPipe, if installed (no face in a synthetic image) ───

def test_real_mediapipe_finds_no_face_in_synthetic_image():
    pytest.importorskip("mediapipe")
    import faces
    try:
        faces.ensure_model()
    except OSError as e:
        pytest.skip(f"face model not available offline: {e}")
    assert faces.detect(synthetic_portrait()) is None
