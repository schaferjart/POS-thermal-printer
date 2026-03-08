"""Tests for config validation in printer_core.py."""

import pytest
from printer_core import validate_config


@pytest.fixture
def valid_config():
    return {
        "printer": {
            "vendor_id": "0x0416",
            "product_id": "0x5011",
            "paper_width": 48,
        },
        "server": {
            "port": 9100,
        },
    }


def test_valid_config_passes(valid_config):
    """A config dict with all required keys does not raise SystemExit."""
    validate_config(valid_config)  # should not raise


def test_missing_vendor_id(valid_config, capsys):
    """Config without printer.vendor_id raises SystemExit and error message contains 'printer.vendor_id'."""
    del valid_config["printer"]["vendor_id"]
    with pytest.raises(SystemExit):
        validate_config(valid_config)
    captured = capsys.readouterr()
    assert "printer.vendor_id" in captured.out


def test_missing_product_id(valid_config, capsys):
    """Config without printer.product_id raises SystemExit and message contains 'printer.product_id'."""
    del valid_config["printer"]["product_id"]
    with pytest.raises(SystemExit):
        validate_config(valid_config)
    captured = capsys.readouterr()
    assert "printer.product_id" in captured.out


def test_missing_paper_width(valid_config, capsys):
    """Config without printer.paper_width raises SystemExit and message contains 'printer.paper_width'."""
    del valid_config["printer"]["paper_width"]
    with pytest.raises(SystemExit):
        validate_config(valid_config)
    captured = capsys.readouterr()
    assert "printer.paper_width" in captured.out


def test_missing_server_port(valid_config, capsys):
    """Config without server.port raises SystemExit and message contains 'server.port'."""
    del valid_config["server"]["port"]
    with pytest.raises(SystemExit):
        validate_config(valid_config)
    captured = capsys.readouterr()
    assert "server.port" in captured.out


def test_missing_printer_section(capsys):
    """Config without 'printer' key at all raises SystemExit and message names the first missing key."""
    config = {"server": {"port": 9100}}
    with pytest.raises(SystemExit):
        validate_config(config)
    captured = capsys.readouterr()
    assert "printer.vendor_id" in captured.out


def test_multiple_missing(valid_config, capsys):
    """Config missing multiple keys reports all of them (not just the first)."""
    del valid_config["printer"]["vendor_id"]
    del valid_config["printer"]["product_id"]
    with pytest.raises(SystemExit):
        validate_config(valid_config)
    captured = capsys.readouterr()
    assert "printer.vendor_id" in captured.out
    assert "printer.product_id" in captured.out


def test_empty_config(capsys):
    """Empty dict raises SystemExit."""
    with pytest.raises(SystemExit):
        validate_config({})
    captured = capsys.readouterr()
    assert "printer.vendor_id" in captured.out
    assert "server.port" in captured.out
