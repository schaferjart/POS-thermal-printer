"""Unit tests for md_renderer.py — block parsing, inline parsing, and image rendering."""

from PIL import Image

from md_renderer import _parse_md, _parse_inline, render_markdown


# ── _parse_md block parsing ───────────────────────────────────────


class TestParseMd:
    """Verify _parse_md correctly identifies block types from markdown syntax."""

    def test_h1(self):
        """'# Hello' produces an h1 block with text 'Hello'."""
        blocks = _parse_md("# Hello")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "h1"
        assert blocks[0]["text"] == "Hello"

    def test_h2(self):
        """'## Sub' produces an h2 block with text 'Sub'."""
        blocks = _parse_md("## Sub")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "h2"
        assert blocks[0]["text"] == "Sub"

    def test_paragraph(self):
        """'Regular text' produces a paragraph block."""
        blocks = _parse_md("Regular text")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "paragraph"
        assert blocks[0]["text"] == "Regular text"

    def test_list(self):
        """'- item' produces a list block with text 'item'."""
        blocks = _parse_md("- item")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "list"
        assert blocks[0]["text"] == "item"

    def test_quote(self):
        """'> quote' produces a quote block with text 'quote'."""
        blocks = _parse_md("> quote")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "quote"
        assert blocks[0]["text"] == "quote"

    def test_separator(self):
        """'---' produces a separator block."""
        blocks = _parse_md("---")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "separator"

    def test_blank(self):
        """Empty string produces a blank block."""
        blocks = _parse_md("")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "blank"

    def test_all_block_types_combined(self):
        """Multi-line input with all block types produces correct type sequence."""
        md = "# Heading 1\n## Heading 2\nParagraph\n- List item\n> Quote\n---\n"
        blocks = _parse_md(md)
        types = [b["type"] for b in blocks]
        assert types == ["h1", "h2", "paragraph", "list", "quote", "separator", "blank"]


# ── _parse_inline style parsing ───────────────────────────────────


class TestParseInline:
    """Verify _parse_inline correctly identifies inline style segments."""

    def test_bold(self):
        """'normal **bold** text' produces three segments with bold in the middle."""
        segments = _parse_inline("normal **bold** text")
        assert segments == [("normal ", "normal"), ("bold", "bold"), (" text", "normal")]

    def test_italic(self):
        """'*italic*' produces a single italic segment."""
        segments = _parse_inline("*italic*")
        assert segments == [("italic", "italic")]

    def test_strikethrough(self):
        """'~~strike~~' produces a single strikethrough segment."""
        segments = _parse_inline("~~strike~~")
        assert segments == [("strike", "strikethrough")]

    def test_code(self):
        """`code` produces a single code segment."""
        segments = _parse_inline("`code`")
        assert segments == [("code", "code")]

    def test_plain_text(self):
        """Plain text with no markup produces a single normal segment."""
        segments = _parse_inline("plain text no markup")
        assert segments == [("plain text no markup", "normal")]

    def test_mixed_styles(self):
        """String with multiple inline styles produces segments containing all style types."""
        segments = _parse_inline("normal **bold** *italic* ~~strike~~ `code` end")
        styles = {s for _, s in segments}
        assert {"normal", "bold", "italic", "strikethrough", "code"} == styles


# ── render_markdown image output ──────────────────────────────────


def _md_config():
    """Return a dictionary-style config using bundled Burra fonts (works on all platforms)."""
    return {
        "dictionary": {
            "font_word": "fonts/Burra-Bold.ttf",
            "font_body": "fonts/Burra-Thin.ttf",
            "font_cite": "fonts/Burra-Thin.ttf",
            "font_date": "fonts/Burra-Thin.ttf",
            "paper_px": 576,
            "margin": 20,
            "line_spacing": 1.4,
            "gap_after_word": 30,
            "size_word": 32,
            "size_body": 20,
            "size_cite": 18,
            "size_date": 16,
        }
    }


class TestRenderMarkdown:
    """Verify render_markdown produces correct PIL Image properties."""

    def test_render_returns_1bit_image(self):
        """render_markdown returns a 1-bit PIL Image."""
        img = render_markdown("# Hello\nWorld", config=_md_config(), show_date=False)
        assert isinstance(img, Image.Image)
        assert img.mode == "1"

    def test_render_width_matches_paper(self):
        """Rendered image width matches paper_px (576)."""
        img = render_markdown("# Hello\nWorld", config=_md_config(), show_date=False)
        assert img.size[0] == 576

    def test_render_height_positive(self):
        """Rendered image has non-zero height."""
        img = render_markdown("# Hello\nWorld", config=_md_config(), show_date=False)
        assert img.size[1] > 0

    def test_render_empty_string(self):
        """Empty string still produces a valid 1-bit image with positive height."""
        img = render_markdown("", config=_md_config(), show_date=False)
        assert isinstance(img, Image.Image)
        assert img.mode == "1"
        assert img.size[0] == 576
        assert img.size[1] > 0

    def test_render_complex_markdown_taller(self):
        """Multi-block markdown produces a taller image than a single heading."""
        simple = render_markdown("# Hello", config=_md_config(), show_date=False)
        complex_md = "# Heading\n\n## Subheading\n\nParagraph text here.\n\n- List item\n\n> Blockquote\n\n---"
        complex_img = render_markdown(complex_md, config=_md_config(), show_date=False)
        assert complex_img.size[1] > simple.size[1]
