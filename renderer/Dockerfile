# syntax=docker/dockerfile:1
# Portrait renderer. Coolify: base directory `renderer/`, Dockerfile build pack.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    FACE_MODEL_PATH=/app/models/face_landmarker.task

# libgl1 + libglib2.0-0: opencv; libegl1 + libgles2: mediapipe 1.x C bindings. curl: health check.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libegl1 libgles2 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the face model into the image (no download at request time), checked by hash.
RUN python - <<'PY'
import hashlib, os, urllib.request
url = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
       "face_landmarker/float16/1/face_landmarker.task")
path = os.environ["FACE_MODEL_PATH"]
os.makedirs(os.path.dirname(path), exist_ok=True)
urllib.request.urlretrieve(url, path)
digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
assert digest == "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff", digest
PY

COPY app.py devices.py faces.py portrait.py config.yaml ./

RUN useradd --system --no-create-home renderer
USER renderer

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
