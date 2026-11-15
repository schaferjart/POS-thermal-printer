import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as app_module
import devices
import faces
import portrait
from conftest import FAKE_LANDMARKS, synthetic_portrait
from test_portrait import FakeResponse, image_message, png_bytes


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(devices, "check_device", lambda token: token == "good-token")
    monkeypatch.setattr(faces, "detect", lambda img: FAKE_LANDMARKS)
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        return client.model_response
    monkeypatch.setattr(portrait.requests, "post", fake_post)
    client = TestClient(app_module.app)
    client.model_calls = calls
    client.model_response = FakeResponse(200, image_message(synthetic_portrait()))
    return client


def post(client, token="good-token", data=None):
    data = data if data is not None else png_bytes(synthetic_portrait(), "JPEG")
    headers = {"X-Device-Token": token} if token is not None else {}
    return client.post("/portrait", headers=headers, files={"photo": ("p.jpg", data, "image/jpeg")})


def test_portrait_returns_four_printable_pngs(client):
    r = post(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["face_detected"] is True
    assert [c["name"] for c in body["crops"]] == ["zoom_0", "zoom_1", "zoom_2", "zoom_3"]
    for c in body["crops"]:
        img = Image.open(io.BytesIO(base64.b64decode(c["png"])))
        assert img.mode == "1" and img.size == (576, c["height"]) and c["width"] == 576
    assert len(client.model_calls) == 1


@pytest.mark.parametrize("token", [None, "", "bad-token"])
def test_bad_token_is_401_and_model_never_called(client, token):
    r = post(client, token=token)
    assert r.status_code == 401
    assert client.model_calls == []


def test_model_without_image_is_502_without_crops(client):
    client.model_response = FakeResponse(200, {"choices": [{"message": {"content": "no"}}]})
    r = post(client)
    assert r.status_code == 502
    assert "crops" not in r.json()


def test_device_check_down_is_503(client, monkeypatch):
    def down(token):
        raise devices.AuthUnavailable("unreachable")
    monkeypatch.setattr(devices, "check_device", down)
    r = post(client)
    assert r.status_code == 503 and client.model_calls == []


def test_not_an_image_is_400(client):
    assert post(client, data=b"hello").status_code == 400


def test_too_large_is_413(client, monkeypatch):
    monkeypatch.setitem(app_module.CFG, "max_upload_mb", 0.001)
    assert post(client).status_code == 413
    assert client.model_calls == []


def test_check_device_uses_publishable_key_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, json=json, headers=headers)
        return FakeResponse(200, True)
    monkeypatch.setattr(devices.requests, "post", fake_post)
    assert devices.check_device("tok") is True
    assert sent["url"] == "https://example.supabase.co/rest/v1/rpc/check_device"
    assert sent["json"] == {"device_token": "tok"}
    assert sent["headers"] == {"apikey": "sb_publishable_test", "Content-Profile": "printer"}

    monkeypatch.setattr(devices.requests, "post", lambda *a, **k: FakeResponse(404, {}))
    with pytest.raises(devices.AuthUnavailable):
        devices.check_device("tok")


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"
