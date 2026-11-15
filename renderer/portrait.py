"""Portrait pipeline: wax transform -> face landmarks -> 4 shared-height crops
-> 1-bit dithered strips, 576 px wide.

Ported from meinungeheuer apps/print-renderer (pipeline.py, dithering.py) with
one deliberate change: if the model call fails or returns no image, this raises
ModelError. It never falls back to the plain photo.
"""

import base64
import io
import os

import numpy as np
import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
Image.MAX_IMAGE_PIXELS = 60_000_000     # refuse decompression bombs


class ModelError(Exception):
    """The image model failed or returned no usable image."""


class BadImage(Exception):
    """The upload is not an image we can read."""


# ── images ────────────────────────────────────────────────────────

def open_image(data: bytes) -> Image.Image:
    """Decode, apply EXIF rotation, flatten alpha onto white, return RGB."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.load()
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        raise BadImage(str(e)) from None
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def downscale(img: Image.Image, max_px: int) -> Image.Image:
    if max(img.size) <= max_px:
        return img
    img = img.copy()
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    return img


# ── stage 1: wax transform (OpenRouter image model) ───────────────

def _image_from_message(msg: dict) -> bytes | None:
    """OpenRouter puts generated images in message.images[]; some models in content[]."""
    parts = list(msg.get("images") or [])
    if isinstance(msg.get("content"), list):
        parts += msg["content"]
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "image_url":
            url = (p.get("image_url") or {}).get("url", "")
            if url.startswith("data:"):
                url = url.split(",", 1)[1]
            if url:
                return base64.b64decode(url)
    return None


def wax_transform(photo: Image.Image, model_cfg: dict) -> Image.Image:
    """Send the photo + wax prompt to the model, return the generated image."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise ModelError("OPENROUTER_API_KEY is not set")
    buf = io.BytesIO()
    photo.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    body = {
        "model": model_cfg["id"],
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": model_cfg["style_prompt"]},
        ]}],
    }
    try:
        r = requests.post(OPENROUTER_URL, json=body, timeout=model_cfg.get("timeout_s", 180),
                          headers={"Authorization": f"Bearer {key}"})
    except requests.RequestException as e:
        raise ModelError(f"model request failed: {type(e).__name__}") from None
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code != 200 or "error" in data:
        err = data.get("error") if isinstance(data.get("error"), dict) else {}
        raise ModelError(f"model returned HTTP {r.status_code}: "
                         f"{(err.get('message') or r.text)[:300]}")
    choices = data.get("choices") or []
    raw = _image_from_message(choices[0].get("message") or {}) if choices else None
    if not raw:
        raise ModelError("model returned no image")
    try:
        return open_image(raw)
    except BadImage as e:
        raise ModelError(f"model image is unreadable: {e}") from None


# ── stage 2: shared-height crops ──────────────────────────────────

def crop_boxes(size: tuple[int, int], landmarks: dict | None, crops: dict) -> list[tuple]:
    """Four (left, top, right, bottom) boxes. All share top and bottom; only
    width (zoom_N_width x shared height) and center (+ zoom_N_offset x image
    width) change. Same math as the tuner's computeCrop and pipeline.py's
    compute_zoom_crops. Without a face the shared height is the whole image
    and the center is crops.center_x (pipeline.py's no-face fallback)."""
    w, h = size
    if landmarks:
        forehead_y = landmarks["forehead_top"][1]
        chin_y = landmarks["chin"][1]
        face_h = chin_y - forehead_y
        top = max(0, round(forehead_y - face_h * crops["pad_top"]))
        bottom = min(h, round(chin_y + face_h * crops["pad_bottom"]))
        center = landmarks["face_center_x"] / w
    else:
        top, bottom, center = 0, h, crops["center_x"]
    crop_h = max(1, bottom - top)
    boxes = []
    for i in range(4):
        crop_w = max(1, min(w, round(crop_h * crops[f"zoom_{i}_width"])))
        cx = round((center + crops.get(f"zoom_{i}_offset", 0.0)) * w)
        left = max(0, min(cx - crop_w // 2, w - crop_w))
        boxes.append((left, top, left + crop_w, top + crop_h))
    return boxes


# ── stage 3: prepare + blur + dither ──────────────────────────────

# 8x8 Bayer threshold map, values 0..63 (x4 to compare against 0..255).
BAYER_8 = np.array([
    [0, 48, 12, 60, 3, 51, 15, 63],
    [32, 16, 44, 28, 35, 19, 47, 31],
    [8, 56, 4, 52, 11, 59, 7, 55],
    [40, 24, 36, 20, 43, 27, 39, 23],
    [2, 50, 14, 62, 1, 49, 13, 61],
    [34, 18, 46, 30, 33, 17, 45, 29],
    [10, 58, 6, 54, 9, 57, 5, 53],
    [42, 26, 38, 22, 41, 25, 37, 21],
], dtype=np.int16) * 4


def prepare(img: Image.Image, paper_px: int, d: dict) -> Image.Image:
    """Resize to paper width, greyscale, autocontrast, sharpness/contrast/brightness, blur."""
    w, h = img.size
    img = img.resize((paper_px, max(1, int(h * paper_px / w))), Image.LANCZOS)
    img = ImageOps.autocontrast(img.convert("L"))
    for enhancer, key in ((ImageEnhance.Sharpness, "sharpness"),
                          (ImageEnhance.Contrast, "contrast"),
                          (ImageEnhance.Brightness, "brightness")):
        if d.get(key, 1.0) != 1.0:
            img = enhancer(img).enhance(d[key])
    if d.get("blur", 0) > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=d["blur"]))
    return img


def bayer(grey: Image.Image) -> Image.Image:
    """Ordered dither: white where pixel > threshold. Vectorised version of the
    old per-pixel loop, same output."""
    a = np.asarray(grey.convert("L"), dtype=np.int16)
    h, w = a.shape
    thr = np.tile(BAYER_8, (h // 8 + 1, w // 8 + 1))[:h, :w]
    return Image.fromarray(a > thr).convert("1")


def dither(grey: Image.Image, mode: str) -> Image.Image:
    if mode == "floyd":
        return grey.convert("1")
    if mode == "bayer":
        return bayer(grey)
    raise ValueError(f"unknown dither mode {mode!r}")


# ── whole pipeline ────────────────────────────────────────────────

def render(photo_bytes: bytes, cfg: dict, transform=None, detect=None) -> dict:
    """Photo bytes -> {"face_detected", "model", "crops": [(name, 1-bit image)]}.
    `transform` and `detect` are injectable for tests."""
    transform = transform or wax_transform
    if detect is None:
        import faces
        detect = faces.detect
    photo = downscale(open_image(photo_bytes), cfg["max_input_px"])
    styled = transform(photo, cfg["model"])
    landmarks = detect(styled)
    out = []
    for i, box in enumerate(crop_boxes(styled.size, landmarks, cfg["portrait_crops"])):
        grey = prepare(styled.crop(box), cfg["paper_px"], cfg["dither"])
        out.append((f"zoom_{i}", dither(grey, cfg["dither"]["mode"])))
    return {"face_detected": landmarks is not None, "model": cfg["model"]["id"], "crops": out}
