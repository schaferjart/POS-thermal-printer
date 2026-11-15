"""Portrait renderer: one endpoint that turns a photo into 4 printable strips.

    POST /portrait   multipart `photo`, header X-Device-Token
      200 {"face_detected", "model", "crops": [{"name", "width", "height", "png"}]}
          png = base64 PNG, mode 1 (1-bit), 576 px wide, ready to print as is
      401 missing or inactive token     413 upload too large
      400 not an image                  502 model failed / returned no image
      503 token check unavailable (Supabase not reachable or not set up)
    GET /health

Endpoints are sync `def`: FastAPI runs them in its thread pool, so the
blocking model call, PIL and MediaPipe don't stall the event loop.
"""

import base64
import io
import logging
import os
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Header, HTTPException, UploadFile

import devices
import portrait

log = logging.getLogger("renderer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

CONFIG_PATH = Path(os.environ.get("RENDERER_CONFIG", Path(__file__).with_name("config.yaml")))
CFG = yaml.safe_load(CONFIG_PATH.read_text())

app = FastAPI(title="printer portrait renderer")


@app.get("/health")
def health():
    return {"status": "ok", "model": CFG["model"]["id"]}


def _png_b64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


@app.post("/portrait")
def make_portrait(photo: UploadFile = File(...),
                  x_device_token: str = Header(default="")):
    # 1. Token first: nothing is decoded or sent to the model before this.
    if not x_device_token:
        raise HTTPException(401, "missing X-Device-Token")
    try:
        ok = devices.check_device(x_device_token)
    except devices.AuthUnavailable as e:
        log.error("device check unavailable: %s", e)
        raise HTTPException(503, "device check unavailable") from None
    if not ok:
        raise HTTPException(401, "unknown or inactive device")

    # 2. Read the upload with a hard size cap.
    limit = int(CFG["max_upload_mb"] * 1024 * 1024)
    data = photo.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"photo larger than {CFG['max_upload_mb']} MB")

    # 3. Render. A model failure is an error, never a plain-photo print.
    try:
        result = portrait.render(data, CFG)
    except portrait.BadImage as e:
        raise HTTPException(400, f"not a readable image: {e}") from None
    except portrait.ModelError as e:
        log.error("model failed: %s", e)
        raise HTTPException(502, f"portrait model failed: {e}") from None

    log.info("portrait ok: face=%s sizes=%s", result["face_detected"],
             [img.size for _, img in result["crops"]])
    return {
        "face_detected": result["face_detected"],
        "model": result["model"],
        "crops": [{"name": name, "width": img.width, "height": img.height, "png": _png_b64(img)}
                  for name, img in result["crops"]],
    }
