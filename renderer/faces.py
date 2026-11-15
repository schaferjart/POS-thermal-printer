"""Face landmarks with MediaPipe's FaceLandmarker (Tasks API).

The only module that imports mediapipe, and only inside detect(), so the rest
of the service and the tests run without it. mediapipe 1.x has no
`mp.solutions` any more; the Tasks API uses the same 478-point face mesh, so
the landmark indices of the old renderer still hold.

The model file is baked into the Docker image at build time (see Dockerfile).
Locally it is downloaded once into renderer/models/ (gitignored).
"""

import os
import threading
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")
MODEL_PATH = Path(os.environ.get(
    "FACE_MODEL_PATH", Path(__file__).resolve().parent / "models" / "face_landmarker.task"))

# Face-mesh indices (same as meinungeheuer print-renderer/pipeline.py).
FOREHEAD_TOP, CHIN, NOSE_TIP = 10, 152, 4
LEFT_EYE_OUTER, LEFT_EYE_INNER = 33, 133
RIGHT_EYE_INNER, RIGHT_EYE_OUTER = 362, 263

_download_lock = threading.Lock()


def ensure_model() -> Path:
    with _download_lock:
        if not MODEL_PATH.exists():
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = MODEL_PATH.with_suffix(".part")
            urllib.request.urlretrieve(MODEL_URL, tmp)
            tmp.replace(MODEL_PATH)
    return MODEL_PATH


def detect(image: Image.Image) -> dict | None:
    """Landmarks of the first face in pixel coordinates, or None if no face."""
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    w, h = image.size
    rgb = np.ascontiguousarray(np.asarray(image.convert("RGB")))
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(ensure_model())),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.5,
    )
    # One landmarker per call: cheap next to the model call, and thread-safe.
    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    if not result.face_landmarks:
        return None
    lm = result.face_landmarks[0]

    def px(i):
        return int(lm[i].x * w), int(lm[i].y * h)

    def mid(a, b):
        return (a[0] + b[0]) // 2, (a[1] + b[1]) // 2

    left_eye = mid(px(LEFT_EYE_OUTER), px(LEFT_EYE_INNER))
    right_eye = mid(px(RIGHT_EYE_OUTER), px(RIGHT_EYE_INNER))
    return {
        "forehead_top": px(FOREHEAD_TOP),
        "chin": px(CHIN),
        "nose_tip": px(NOSE_TIP),
        "left_eye_center": left_eye,
        "right_eye_center": right_eye,
        "face_center_x": (left_eye[0] + right_eye[0]) // 2,
    }
