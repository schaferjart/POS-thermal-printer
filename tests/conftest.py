"""Shared test fixtures for the POS thermal printer test suite."""

import os
import tempfile

import pytest
from PIL import Image, ImageFont


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
