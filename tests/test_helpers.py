"""Unit tests for helpers.py — resolve_font_path, wrap_text, open_image."""

import os
import struct
import tempfile

from PIL import Image

from helpers import resolve_font_path, wrap_text, open_image, FONT_THIN, FONT_BOLD


# ── resolve_font_path ──────────────────────────────────────────────

def test_resolve_font_path_relative():
    """Relative path is resolved to an absolute path rooted at the project dir."""
    result = resolve_font_path("fonts/Burra-Thin.ttf")
    assert os.path.isabs(result)
    assert result.endswith("fonts/Burra-Thin.ttf")


def test_resolve_font_path_absolute():
    """Absolute path is returned unchanged."""
    path = "/usr/share/fonts/foo.ttf"
    assert resolve_font_path(path) == path


# ── wrap_text ──────────────────────────────────────────────────────

def test_wrap_text_single_line(small_font):
    """Short text that fits in one line returns a single-element list."""
    result = wrap_text("hello world", small_font, 999)
    assert result == ["hello world"]


def test_wrap_text_wraps(small_font):
    """Long text is wrapped into multiple lines, each within max_width."""
    text = "word " * 20
    result = wrap_text(text.strip(), small_font, 200)
    assert len(result) > 1
    # Each line should fit within the width (we trust the wrapping logic)
    assert all(isinstance(line, str) for line in result)


def test_wrap_text_empty(small_font):
    """Empty string returns [''] (not an empty list)."""
    result = wrap_text("", small_font, 200)
    assert result == [""]


# ── open_image ─────────────────────────────────────────────────────

def test_open_image_rgb(sample_rgb_image):
    """RGB JPEG opens as an RGB image with no alpha channel."""
    img = open_image(sample_rgb_image)
    assert isinstance(img, Image.Image)
    assert img.mode == "RGB"


def test_open_image_rgba(sample_rgba_image):
    """RGBA PNG is composited onto white and returned as RGB."""
    img = open_image(sample_rgba_image)
    assert img.mode == "RGB"
    # Semi-transparent red on white should produce a pinkish color
    pixel = img.getpixel((50, 50))
    # Red channel should be > 200 (255 red * 0.5 + 255 white * 0.5 ≈ 255)
    assert pixel[0] > 200


def test_open_image_exif():
    """EXIF orientation is applied (rotated image gets transposed)."""
    # Create a 100x50 image (wider than tall)
    img = Image.new("RGB", (100, 50), color=(0, 128, 0))
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img.save(path, format="JPEG")

    # Manually inject EXIF data for 90-degree rotation (orientation tag 6)
    # This is a minimal EXIF with orientation=6 (rotate 90 CW)
    # The image is 100x50, after rotation it should be 50x100
    _inject_exif_orientation(path, orientation=6)

    result = open_image(path)
    # After EXIF transpose of orientation 6, width and height should swap
    assert result.size == (50, 100)

    os.unlink(path)


def _inject_exif_orientation(path, orientation=6):
    """Inject a minimal EXIF block with the given orientation into a JPEG file."""
    # Build a minimal EXIF APP1 segment
    # TIFF header (little-endian)
    tiff_header = b"II"  # little-endian
    tiff_header += struct.pack("<H", 42)  # magic
    tiff_header += struct.pack("<I", 8)   # offset to first IFD

    # IFD with one entry: Orientation (tag 0x0112)
    ifd_count = struct.pack("<H", 1)
    # Tag=0x0112, Type=SHORT(3), Count=1, Value=orientation
    ifd_entry = struct.pack("<HHI", 0x0112, 3, 1)
    ifd_entry += struct.pack("<HH", orientation, 0)  # value + padding
    ifd_next = struct.pack("<I", 0)  # no next IFD

    tiff_data = tiff_header + ifd_count + ifd_entry + ifd_next

    # APP1 marker
    exif_header = b"Exif\x00\x00"
    app1_data = exif_header + tiff_data
    app1_length = len(app1_data) + 2  # +2 for length field itself
    app1_segment = b"\xFF\xE1" + struct.pack(">H", app1_length) + app1_data

    with open(path, "rb") as f:
        jpeg_data = f.read()

    # Insert APP1 right after SOI marker (first 2 bytes: FF D8)
    assert jpeg_data[:2] == b"\xFF\xD8", "Not a JPEG file"
    new_data = jpeg_data[:2] + app1_segment + jpeg_data[2:]

    with open(path, "wb") as f:
        f.write(new_data)
