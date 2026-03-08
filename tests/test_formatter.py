"""Tests for Formatter state safety — verify try/finally guards reset printer state on exception.

Each test mocks p.text (or p.qr/p.barcode) to raise, then inspects the mock
call history on p.set to confirm the reset call was still made in the finally block.
"""

import pytest
from unittest.mock import patch, call, MagicMock
from escpos.printer import Dummy
from printer_core import Formatter


class TestFormatterStateReset:
    """Every state-changing Formatter method must reset printer state
    even when the print operation raises an exception.

    Strategy: mock p.set as a MagicMock, mock p.text to raise, call the method,
    and assert p.set was called with the reset arguments AFTER the setup arguments.
    If there's no try/finally, the reset p.set call never happens.
    """

    def _make_mocked(self):
        """Create a Formatter with a Dummy whose set() is a MagicMock."""
        p = Dummy()
        fmt = Formatter(p)
        mock_set = MagicMock()
        p.set = mock_set
        return fmt, p, mock_set

    # --- title() ---

    def test_title_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        with patch.object(p, "text", side_effect=RuntimeError("paper jam")):
            with pytest.raises(RuntimeError):
                fmt.title("BOOM")
        # Must have called set() to reset even though text() raised
        reset_call = call(align="left", bold=False, double_height=False, double_width=False)
        assert reset_call in mock_set.call_args_list, \
            f"title() must reset state on exception. Calls were: {mock_set.call_args_list}"

    # --- subtitle() ---

    def test_subtitle_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        with patch.object(p, "text", side_effect=RuntimeError("paper jam")):
            with pytest.raises(RuntimeError):
                fmt.subtitle("BOOM")
        reset_call = call(align="left", bold=False)
        assert reset_call in mock_set.call_args_list, \
            f"subtitle() must reset state on exception. Calls were: {mock_set.call_args_list}"

    # --- center() ---

    def test_center_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        with patch.object(p, "text", side_effect=RuntimeError("paper jam")):
            with pytest.raises(RuntimeError):
                fmt.center("BOOM")
        reset_call = call(align="left")
        assert reset_call in mock_set.call_args_list, \
            f"center() must reset state on exception. Calls were: {mock_set.call_args_list}"

    # --- bold() ---

    def test_bold_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        with patch.object(p, "text", side_effect=RuntimeError("paper jam")):
            with pytest.raises(RuntimeError):
                fmt.bold("BOOM")
        reset_call = call(bold=False)
        assert reset_call in mock_set.call_args_list, \
            f"bold() must reset state on exception. Calls were: {mock_set.call_args_list}"

    # --- italic_text() ---

    def test_italic_text_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        with patch.object(p, "text", side_effect=RuntimeError("paper jam")):
            with pytest.raises(RuntimeError):
                fmt.italic_text("BOOM")
        reset_call = call(underline=0)
        assert reset_call in mock_set.call_args_list, \
            f"italic_text() must reset state on exception. Calls were: {mock_set.call_args_list}"

    # --- small() ---

    def test_small_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        with patch.object(p, "text", side_effect=RuntimeError("paper jam")):
            with pytest.raises(RuntimeError):
                fmt.small("BOOM")
        reset_call = call(font="a")
        assert reset_call in mock_set.call_args_list, \
            f"small() must reset state on exception. Calls were: {mock_set.call_args_list}"

    # --- right() ---

    def test_right_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        with patch.object(p, "text", side_effect=RuntimeError("paper jam")):
            with pytest.raises(RuntimeError):
                fmt.right("BOOM")
        reset_call = call(align="left")
        assert reset_call in mock_set.call_args_list, \
            f"right() must reset state on exception. Calls were: {mock_set.call_args_list}"

    # --- left_right_bold() ---

    def test_left_right_bold_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        # left_right_bold calls left_right internally, which calls p.text
        with patch.object(p, "text", side_effect=RuntimeError("paper jam")):
            with pytest.raises(RuntimeError):
                fmt.left_right_bold("LEFT", "RIGHT")
        reset_call = call(bold=False)
        assert reset_call in mock_set.call_args_list, \
            f"left_right_bold() must reset state on exception. Calls were: {mock_set.call_args_list}"

    # --- qr() ---

    def test_qr_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        with patch.object(p, "qr", side_effect=RuntimeError("qr fail")):
            with pytest.raises(RuntimeError):
                fmt.qr("https://example.com")
        reset_call = call(align="left")
        assert reset_call in mock_set.call_args_list, \
            f"qr() must reset state on exception. Calls were: {mock_set.call_args_list}"

    # --- barcode() ---

    def test_barcode_resets_on_exception(self):
        fmt, p, mock_set = self._make_mocked()
        with patch.object(p, "barcode", side_effect=RuntimeError("barcode fail")):
            with pytest.raises(RuntimeError):
                fmt.barcode("12345")
        reset_call = call(align="left")
        assert reset_call in mock_set.call_args_list, \
            f"barcode() must reset state on exception. Calls were: {mock_set.call_args_list}"


class TestFontBText:
    """font_b_text() prints in Font B with normal_textsize, resets to Font A."""

    def _make(self):
        p = Dummy()
        return Formatter(p), p

    def test_font_b_text_sets_font_b_and_resets(self):
        """Normal path: sets Font B + normal_textsize, prints, resets to Font A."""
        fmt, p = self._make()
        calls = []
        original_set = p.set

        def spy_set(**kwargs):
            calls.append(kwargs)
            return original_set(**kwargs)

        with patch.object(p, "set", side_effect=spy_set):
            fmt.font_b_text("small text")

        # First call should set font B with normal_textsize
        assert calls[0]["font"] == "b"
        assert calls[0]["normal_textsize"] is True
        # Last call should reset to font A
        assert calls[-1]["font"] == "a"

    def test_font_b_text_resets_on_exception(self):
        """Exception path: resets to Font A even when text() raises."""
        fmt, p = self._make()
        mock_set = MagicMock()
        p.set = mock_set

        with patch.object(p, "text", side_effect=RuntimeError("fail")):
            with pytest.raises(RuntimeError):
                fmt.font_b_text("BOOM")

        # Even after exception, must have a set(font="a") call
        reset_call = call(font="a")
        assert reset_call in mock_set.call_args_list, \
            f"font_b_text must reset to Font A even on exception. Calls were: {mock_set.call_args_list}"
