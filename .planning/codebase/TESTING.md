# Testing

## Current State

**No automated test suite exists.** There are no unit tests, integration tests, or CI/CD pipelines configured.

## Manual Testing

The codebase supports manual testing via the `--dummy` flag available on all CLI commands:

```bash
./print.sh test --dummy           # Test page without hardware
./print.sh image photo.jpg --dummy # Saves preview_<mode>.png instead of printing
./print.sh md "# Hello" --dummy    # Renders markdown without printer
```

### Dummy Printer

- `printer_core.py` provides a `DummyPrinter` class that replaces the USB printer
- When `--dummy` is passed, `connect()` returns a `DummyPrinter` instead of a real USB connection
- Image output is saved as `preview_*.png` files in the working directory

## What Should Be Tested (Priority Order)

### High Priority
1. **Markdown rendering** (`md_renderer.py`) - Core text-to-image pipeline
   - Heading parsing and font sizing
   - Inline formatting: bold, italic, strikethrough, code
   - List rendering and indentation
   - Blockquote styling
   - Line wrapping at paper width (576px)

2. **Image dithering** (`image_printer.py`) - Image processing pipeline
   - Floyd-Steinberg, Bayer, and halftone modes
   - Blur and contrast adjustments
   - Output is valid 1-bit image at correct width

3. **Config loading** (`config.yaml`) - Font style resolution
   - All three styles (`dictionary`, `helvetica`, `acidic`) load correctly
   - Font file paths resolve to existing files
   - `.ttc` font index selection works

### Medium Priority
4. **Template rendering** (`templates.py`) - Layout correctness
   - Receipt template with sample order JSON
   - Label template with heading + lines
   - Dictionary entry with citations and QR

5. **CLI argument parsing** (`print_cli.py`) - All subcommands parse correctly

6. **HTTP endpoints** (`print_server.py`) - Request/response handling

### Low Priority
7. **Image slicer** (`image_slicer.py`) - Strip dimensions and count
8. **Formatter** (`printer_core.py`) - ESC/POS command sequences

## Recommended Setup

```bash
pip install pytest pytest-cov pillow
```

```python
# tests/conftest.py
import pytest
from printer_core import connect

@pytest.fixture
def dummy_printer():
    return connect(dummy=True)
```

### Example Test

```python
# tests/test_md_renderer.py
from md_renderer import render_markdown

def test_heading_renders():
    img = render_markdown("# Hello World", style="helvetica")
    assert img.mode == "1"
    assert img.width == 576

def test_bold_inline():
    img = render_markdown("This is **bold** text", style="helvetica")
    assert img is not None
```

## Coverage Gaps

- No regression tests for dithering output quality
- No validation that ESC/POS byte sequences are correct
- No tests for Flask endpoint error handling
- No tests for USB connection failure scenarios
