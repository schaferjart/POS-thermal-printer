"""Unit tests for image_printer.py dithering functions and process_image pipeline."""

import pytest
from PIL import Image

from image_printer import _dither_floyd, _dither_bayer, _dither_halftone, process_image


class TestDitherFunctions:
    """Each dither function returns a 1-bit image with correct dimensions."""

    def test_floyd_returns_1bit_correct_size(self):
        grey = Image.new("L", (100, 100), 128)
        result = _dither_floyd(grey)
        assert result.mode == "1"
        assert result.size == (100, 100)

    def test_bayer_returns_1bit_correct_size(self):
        grey = Image.new("L", (100, 100), 128)
        result = _dither_bayer(grey)
        assert result.mode == "1"
        assert result.size == (100, 100)

    def test_halftone_returns_1bit_correct_size(self):
        grey = Image.new("L", (120, 120), 128)
        result = _dither_halftone(grey, dot_size=6)
        assert result.mode == "1"
        assert result.size == (120, 120)

    def test_floyd_black_input_has_black_pixels(self):
        """All-black input should produce some black pixels (value 0)."""
        grey = Image.new("L", (100, 100), 0)
        result = _dither_floyd(grey)
        pixels = list(result.tobytes())
        assert 0 in pixels, "Floyd on all-black input should produce some black pixels"

    def test_floyd_white_input_has_white_pixels(self):
        """All-white input should produce some white pixels (value 255)."""
        grey = Image.new("L", (100, 100), 255)
        result = _dither_floyd(grey)
        pixels = list(result.tobytes())
        assert 255 in pixels, "Floyd on all-white input should produce some white pixels"


class TestProcessImage:
    """process_image returns a 1-bit image ready for thermal printing."""

    def test_process_image_returns_1bit_width_576(self, sample_rgb_image):
        result = process_image(sample_rgb_image, mode="floyd")
        assert result.mode == "1"
        assert result.size[0] == 576

    def test_process_image_bayer_returns_1bit(self, sample_rgb_image):
        result = process_image(sample_rgb_image, mode="bayer")
        assert result.mode == "1"

    def test_process_image_invalid_mode_raises(self, sample_rgb_image):
        with pytest.raises(ValueError, match="Unknown dither mode"):
            process_image(sample_rgb_image, mode="invalid")
