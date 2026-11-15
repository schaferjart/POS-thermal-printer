import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def synthetic_portrait(w=800, h=1200) -> Image.Image:
    """A grey gradient with a light 'head' ellipse: no real face, but enough
    tone for the dither to have something to do."""
    img = Image.linear_gradient("L").resize((w, h)).convert("RGB")
    d = ImageDraw.Draw(img)
    d.ellipse((w * 0.3, h * 0.2, w * 0.7, h * 0.6), fill=(210, 210, 210))
    d.ellipse((w * 0.4, h * 0.35, w * 0.45, h * 0.38), fill=(30, 30, 30))
    d.ellipse((w * 0.55, h * 0.35, w * 0.6, h * 0.38), fill=(30, 30, 30))
    return img


# Landmarks as faces.detect would return them for the synthetic head.
FAKE_LANDMARKS = {
    "forehead_top": (400, 240), "chin": (400, 720), "nose_tip": (400, 520),
    "left_eye_center": (340, 440), "right_eye_center": (460, 440), "face_center_x": 400,
}


@pytest.fixture
def cfg():
    import yaml
    return yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())
