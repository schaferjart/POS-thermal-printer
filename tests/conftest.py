"""Shared test fixtures for the POS thermal printer test suite."""

import os
import time
import tempfile

import pytest
from PIL import Image, ImageFont
from escpos.printer import Dummy


@pytest.fixture
def sample_rgb_image():
    """Create a temporary 100x100 RGB JPEG file."""
    img = Image.new("RGB", (100, 100), color=(128, 64, 200))
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img.save(path, format="JPEG")
    yield path
    os.unlink(path)


@pytest.fixture
def sample_rgba_image():
    """Create a temporary 100x100 RGBA PNG file with semi-transparent pixels."""
    img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path, format="PNG")
    yield path
    os.unlink(path)


@pytest.fixture
def small_font():
    """Return a default PIL ImageFont for testing."""
    return ImageFont.load_default()


@pytest.fixture
def app():
    """Create Flask app configured for testing with dummy printer."""
    import print_server
    print_server._config = {
        "printer": {"vendor_id": 0x0, "product_id": 0x0, "paper_width": 48},
        "server": {"port": 9100},
    }
    print_server._dummy = True
    print_server._printer = Dummy()
    print_server._server_start_time = time.time()
    print_server.app.config["TESTING"] = True
    return print_server.app


@pytest.fixture
def client(app):
    """Flask test client for sending requests without a running server."""
    return app.test_client()


@pytest.fixture
def client_with_auth():
    """Flask test client with API key authentication enabled."""
    import print_server
    print_server._config = {
        "printer": {"vendor_id": 0x0, "product_id": 0x0, "paper_width": 48},
        "server": {"port": 9100, "api_key": "test-secret-key"},
    }
    print_server._dummy = True
    print_server._printer = Dummy()
    print_server._server_start_time = time.time()
    print_server.app.config["TESTING"] = True
    return print_server.app.test_client()
