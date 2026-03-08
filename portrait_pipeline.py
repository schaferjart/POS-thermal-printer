"""
Portrait-to-Statue pipeline — captures a portrait, selects the best shot
via AI vision, transforms it into a monochrome sculptural aesthetic via
n8n workflow (Gemini 2.5 Flash Image), and prints at multiple zoom levels.

Three stages:
    A. Photo selection  — OpenRouter vision model picks the best portrait
    B. Style transfer   — n8n webhook → Gemini 2.5 Flash Image
    C. Print output     — face-landmark zoom crops, blur + bayer dithering

Usage (standalone test):
    python portrait_pipeline.py photo.jpg --dummy
"""

import base64
import io
import os
from datetime import datetime
import numpy as np
import requests
from PIL import Image

from helpers import open_image
from image_printer import _prepare, _apply_blur, _dither_bayer, _dither_floyd, _dither_halftone


# ── Stage A: Photo Selection ────────────────────────────────────────

def select_best_photo(image_paths: list[str], config: dict) -> str:
    """
    Send all photos to an OpenRouter vision model and ask it to pick
    the best portrait based on focus, framing, expression, lighting.
    """
    cfg = config.get("portrait", {})
    api_key = os.environ.get(cfg.get("openrouter_api_key_env", "OPENROUTER_API_KEY"), "")
    model = cfg.get("selection_model", "google/gemini-2.0-flash-001")

    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Export it or set portrait.openrouter_api_key_env in config."
        )

    content = []
    for i, path in enumerate(image_paths):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(path)[1].lower()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "webp": "image/webp"}.get(ext.lstrip("."), "image/jpeg")
        content.append({"type": "text", "text": f"Photo {i + 1}:"})
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    content.append({
        "type": "text",
        "text": (
            f"You are evaluating {len(image_paths)} portrait photos. "
            "Pick the single best photo for an art portrait print. "
            "Criteria: sharp focus on the face, centered framing, natural expression, "
            "clean background, good lighting. "
            "Reply with ONLY the photo number (e.g. '2'). Nothing else."
        )
    })

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 10,
        },
        timeout=60,
    )
    resp.raise_for_status()

    answer = resp.json()["choices"][0]["message"]["content"].strip()
    num = int("".join(c for c in answer if c.isdigit()) or "1")
    idx = max(0, min(num - 1, len(image_paths) - 1))

    print(f"[PORTRAIT] AI selected photo {idx + 1}/{len(image_paths)}: {image_paths[idx]}")
    return image_paths[idx]


# ── Stage B: Style Transfer via n8n ────────────────────────────────

def transform_to_statue(image_path: str, config: dict) -> Image.Image:
    """
    Send portrait to n8n webhook which calls OpenRouter Gemini 2.5 Flash
    to transform it into a monochrome sculptural aesthetic.

    Prompt is read from config.yaml so you can edit it without touching n8n.
    """
    cfg = config.get("portrait", {})
    webhook_url = cfg.get("n8n_webhook_url")
    api_key = os.environ.get(cfg.get("openrouter_api_key_env", "OPENROUTER_API_KEY"), "")
    prompt = cfg.get("style_prompt", "Transform this portrait into a monochrome sculpture.")

    if not webhook_url:
        raise RuntimeError("portrait.n8n_webhook_url not set in config.yaml")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    # Load and prepare image
    img = open_image(image_path)

    # Encode as PNG base64
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    print(f"[PORTRAIT] Sending to n8n ({img.size[0]}x{img.size[1]})...")

    resp = requests.post(
        webhook_url,
        json={"image": b64, "prompt": prompt},
        headers={
            "Content-Type": "application/json",
            "X-OpenRouter-Key": api_key,
        },
        timeout=180,
    )
    resp.raise_for_status()

    if not resp.text:
        raise RuntimeError("n8n webhook returned empty response")

    result = resp.json()

    if "error" in result:
        raise RuntimeError(f"n8n error: {result['error']}")

    if "image" not in result:
        raise RuntimeError(f"n8n webhook returned no image. Keys: {list(result.keys())}")

    img_data = base64.b64decode(result["image"])
    out = Image.open(io.BytesIO(img_data))
    print(f"[PORTRAIT] Transform complete — {out.size[0]}x{out.size[1]}")
    return out


# ── Face Landmark Detection ──────────────────────────────────────────

def detect_face_landmarks(image: Image.Image) -> dict:
    """
    Use mediapipe FaceMesh to find key facial landmarks.

    Returns dict with pixel coordinates:
        forehead_top, chin, left_eye_outer, left_eye_inner,
        right_eye_inner, right_eye_outer, left_eye_center,
        right_eye_center, nose_tip, face_center_x
    Returns None if no face detected.
    """
    import mediapipe as mp

    w, h = image.size
    rgb = np.array(image.convert("RGB"))

    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as mesh:
        results = mesh.process(rgb)

    if not results.multi_face_landmarks:
        return None

    lm = results.multi_face_landmarks[0].landmark

    def px(idx):
        return int(lm[idx].x * w), int(lm[idx].y * h)

    # Key mediapipe landmark indices
    forehead_top = px(10)
    chin = px(152)
    nose_tip = px(4)
    left_eye_outer = px(33)
    left_eye_inner = px(133)
    right_eye_inner = px(362)
    right_eye_outer = px(263)

    # Eye centers (average of inner and outer corners)
    left_eye_center = (
        (left_eye_outer[0] + left_eye_inner[0]) // 2,
        (left_eye_outer[1] + left_eye_inner[1]) // 2,
    )
    right_eye_center = (
        (right_eye_outer[0] + right_eye_inner[0]) // 2,
        (right_eye_outer[1] + right_eye_inner[1]) // 2,
    )

    face_center_x = (left_eye_center[0] + right_eye_center[0]) // 2

    landmarks = {
        "forehead_top": forehead_top,
        "chin": chin,
        "nose_tip": nose_tip,
        "left_eye_outer": left_eye_outer,
        "left_eye_inner": left_eye_inner,
        "right_eye_inner": right_eye_inner,
        "right_eye_outer": right_eye_outer,
        "left_eye_center": left_eye_center,
        "right_eye_center": right_eye_center,
        "face_center_x": face_center_x,
    }

    print(f"[PORTRAIT] Face detected — eyes at y={left_eye_center[1]}, chin at y={chin[1]}")
    return landmarks


def compute_zoom_crops(image: Image.Image, landmarks: dict) -> list[dict]:
    """
    Compute 4 zoom crop regions from face landmarks.

    zoom_0: shoulders to hairline — full portrait
    zoom_1: chin to forehead, outer-eye-to-outer-eye width
    zoom_2: eye-center to eye-center width, nose-bridge height
    zoom_3: narrow vertical strip through face center
    """
    w, h = image.size
    face_cx = landmarks["face_center_x"]
    forehead_y = landmarks["forehead_top"][1]
    chin_y = landmarks["chin"][1]
    face_h = chin_y - forehead_y

    left_eye_out_x = landmarks["left_eye_outer"][0]
    right_eye_out_x = landmarks["right_eye_outer"][0]
    left_eye_cx = landmarks["left_eye_center"][0]
    right_eye_cx = landmarks["right_eye_center"][0]
    eye_y = (landmarks["left_eye_center"][1] + landmarks["right_eye_center"][1]) // 2
    nose_y = landmarks["nose_tip"][1]

    def clamp_box(left, top, right, bottom):
        left = max(0, left)
        top = max(0, top)
        right = min(w, right)
        bottom = min(h, bottom)
        return (left, top, right, bottom)

    # zoom_0: shoulders to hairline
    # Extend above forehead by 30% of face height, below chin by 80% of face height
    pad_top = int(face_h * 0.3)
    pad_bottom = int(face_h * 0.8)
    z0_top = forehead_y - pad_top
    z0_bottom = chin_y + pad_bottom
    z0_h = z0_bottom - z0_top
    # Width proportional to height (2:3 portrait ratio)
    z0_w = int(z0_h * 0.67)
    z0_left = face_cx - z0_w // 2
    zoom_0 = clamp_box(z0_left, z0_top, z0_left + z0_w, z0_bottom)

    # zoom_1: chin to forehead, outer-eye width + padding
    eye_span = right_eye_out_x - left_eye_out_x
    pad_x = int(eye_span * 0.35)
    pad_top1 = int(face_h * 0.15)
    pad_bottom1 = int(face_h * 0.15)
    z1_left = left_eye_out_x - pad_x
    z1_right = right_eye_out_x + pad_x
    z1_top = forehead_y - pad_top1
    z1_bottom = chin_y + pad_bottom1
    zoom_1 = clamp_box(z1_left, z1_top, z1_right, z1_bottom)

    # zoom_2: mid-eye to mid-eye width, centered on nose bridge
    ipd = right_eye_cx - left_eye_cx  # inter-pupillary distance
    pad_x2 = int(ipd * 0.15)
    z2_left = left_eye_cx - pad_x2
    z2_right = right_eye_cx + pad_x2
    z2_w = z2_right - z2_left
    # Height: proportional, centered between eyes and nose
    z2_center_y = (eye_y + nose_y) // 2
    z2_h = int(z2_w * 1.4)
    z2_top = z2_center_y - z2_h // 2
    zoom_2 = clamp_box(z2_left, z2_top, z2_right, z2_top + z2_h)

    # zoom_3: narrow strip through face center (nose width)
    nose_x = landmarks["nose_tip"][0]
    inner_eye_span = landmarks["right_eye_inner"][0] - landmarks["left_eye_inner"][0]
    strip_w = int(inner_eye_span * 0.55)
    z3_left = nose_x - strip_w // 2
    z3_top = forehead_y - int(face_h * 0.05)
    z3_bottom = chin_y + int(face_h * 0.1)
    zoom_3 = clamp_box(z3_left, z3_top, z3_left + strip_w, z3_bottom)

    return [
        {"name": "zoom_0", "box": zoom_0},
        {"name": "zoom_1", "box": zoom_1},
        {"name": "zoom_2", "box": zoom_2},
        {"name": "zoom_3", "box": zoom_3},
    ]


# ── Stage C: Print Output ───────────────────────────────────────────

def _dither_image(grey: Image.Image, mode: str, dot_size: int = 6) -> Image.Image:
    """Apply the selected dithering mode."""
    if mode == "halftone":
        return _dither_halftone(grey, dot_size=dot_size)
    elif mode == "bayer":
        return _dither_bayer(grey)
    elif mode == "floyd":
        return _dither_floyd(grey)
    else:
        return _dither_bayer(grey)


def print_portrait(image: Image.Image, config: dict, printer, dummy: bool = False,
                   save_dir: str = None,
                   blur_override: float = None, dither_mode_override: str = None):
    """
    Print the transformed portrait at multiple zoom levels using face landmarks.
    """
    from printer_core import Formatter

    cfg = config.get("portrait", {})
    halftone_cfg = config.get("halftone", {})

    blur = blur_override if blur_override is not None else cfg.get("blur", 10)
    dither_mode = dither_mode_override if dither_mode_override is not None else cfg.get("dither_mode", "bayer")
    paper_px = halftone_cfg.get("paper_px", 576)
    contrast = halftone_cfg.get("contrast", 1.3)
    brightness = halftone_cfg.get("brightness", 1.0)
    sharpness = halftone_cfg.get("sharpness", 1.2)
    dot_size = halftone_cfg.get("dot_size", 6)

    # Detect face landmarks
    landmarks = detect_face_landmarks(image)
    if not landmarks:
        print("[PORTRAIT] WARNING: No face detected, using center crops as fallback")
        zooms = [
            {"name": "zoom_0", "box": (0, 0, image.size[0], image.size[1])},
            {"name": "zoom_1", "box": _fallback_box(image, 0.7)},
            {"name": "zoom_2", "box": _fallback_box(image, 0.4)},
            {"name": "zoom_3", "box": _fallback_strip(image)},
        ]
    else:
        zooms = compute_zoom_crops(image, landmarks)

    fmt = Formatter(printer, config.get("printer", {}).get("paper_width", 48))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    for zoom in zooms:
        name = zoom["name"]
        box = zoom["box"]
        cropped = image.crop(box)
        crop_w = box[2] - box[0]
        crop_h = box[3] - box[1]

        grey = _prepare(cropped, paper_px, contrast, brightness, sharpness)
        grey = _apply_blur(grey, blur)
        dithered = _dither_image(grey, dither_mode, dot_size)

        label = f"{name}  {timestamp}"
        if dummy and save_dir:
            out_path = os.path.join(save_dir, f"portrait_{name}.png")
            dithered.save(out_path)
            print(f"[PORTRAIT] Saved preview: {out_path} ({crop_w}x{crop_h})")
        else:
            fmt.bold(label)
            printer.image(dithered)
            fmt.feed()
            fmt.cut()
            print(f"[PORTRAIT] Printed: {name} ({crop_w}x{crop_h})")


def _fallback_box(image: Image.Image, ratio: float) -> tuple:
    """Center crop fallback when no face detected."""
    w, h = image.size
    nw, nh = int(w * ratio), int(h * ratio)
    left = (w - nw) // 2
    top = (h - nh) // 2
    return (left, top, left + nw, top + nh)


def _fallback_strip(image: Image.Image) -> tuple:
    """Narrow strip fallback."""
    w, h = image.size
    nw = int(w * 0.12)
    left = (w - nw) // 2
    return (left, 0, left + nw, h)


# ── Full Pipeline ────────────────────────────────────────────────────

def run_pipeline(image_paths: list[str], config: dict, printer,
                 dummy: bool = False, save_dir: str = None,
                 skip_selection: bool = False, skip_transform: bool = False,
                 blur: float = None, dither_mode: str = None):
    """
    Run the full portrait pipeline: select -> transform -> print.
    """
    # Stage A: Photo selection
    if len(image_paths) > 1 and not skip_selection:
        selected = select_best_photo(image_paths, config)
    else:
        selected = image_paths[0]
        print(f"[PORTRAIT] Using image: {selected}")

    # Stage B: Style transfer via n8n
    if skip_transform:
        image = open_image(selected)
        print("[PORTRAIT] Skipping style transfer")
    else:
        image = transform_to_statue(selected, config)

    # Save raw transformed image before dithering
    if save_dir:
        raw_path = os.path.join(save_dir, "portrait_raw.png")
        image.save(raw_path)
        print(f"[PORTRAIT] Saved raw transform: {raw_path}")

    # Stage C: Print at multiple zoom levels
    print_portrait(image, config, printer, dummy=dummy, save_dir=save_dir,
                   blur_override=blur, dither_mode_override=dither_mode)

    return selected, image


# ── CLI test entry point ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from printer_core import load_config, connect

    parser = argparse.ArgumentParser(description="Portrait pipeline test")
    parser.add_argument("images", nargs="+", help="Image file(s)")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dummy", action="store_true", help="Save previews instead of printing")
    parser.add_argument("--skip-selection", action="store_true")
    parser.add_argument("--skip-transform", action="store_true")
    parser.add_argument("--blur", type=float)
    parser.add_argument("--mode", choices=["bayer", "floyd", "halftone"])
    parser.add_argument("--output", default=".", help="Output directory for previews")
    args = parser.parse_args()

    config = load_config(args.config)
    printer = connect(config, dummy=args.dummy)

    run_pipeline(
        args.images, config, printer,
        dummy=args.dummy,
        save_dir=args.output,
        skip_selection=args.skip_selection,
        skip_transform=args.skip_transform,
        blur=args.blur,
        dither_mode=args.mode,
    )
