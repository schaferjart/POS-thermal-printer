"""Unit tests for md_renderer.py — block parsing, inline parsing, and image rendering."""

from md_renderer import _parse_md, _parse_inline


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
