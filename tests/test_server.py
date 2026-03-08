"""Integration tests for print_server.py input validation, error format, ESC@ init,
graceful shutdown, and portrait pipeline config safety."""

import copy
import json
from unittest.mock import patch, MagicMock

import pytest


class TestValidationMissingFields:
    """POST {} to each JSON endpoint returns 400 with structured error."""

    def test_receipt_missing_items(self, client):
        resp = client.post("/print/receipt", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "Missing required field 'items'"
        assert data["field"] == "items"

    def test_message_missing_text(self, client):
        resp = client.post("/print/message", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "Missing required field 'text'"
        assert data["field"] == "text"

    def test_label_missing_heading(self, client):
        resp = client.post("/print/label", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "Missing required field 'heading'"
        assert data["field"] == "heading"

    def test_list_missing_title(self, client):
        resp = client.post("/print/list", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["field"] in ("title", "rows")
        assert "Missing required field" in data["error"]

    def test_dictionary_missing_word(self, client):
        resp = client.post("/print/dictionary", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["field"] in ("word", "definition")
        assert "Missing required field" in data["error"]

    def test_markdown_missing_text(self, client):
        resp = client.post("/print/markdown", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "Missing required field 'text'"
        assert data["field"] == "text"


class TestValidationBadJSON:
    """Non-JSON and non-object bodies return 400 with clear messages."""

    def test_invalid_json_body(self, client):
        resp = client.post(
            "/print/message",
            data="not json at all",
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "Invalid or missing JSON body"

    def test_json_array_not_object(self, client):
        resp = client.post(
            "/print/message",
            data=json.dumps([1, 2, 3]),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "Request body must be a JSON object"


class TestMaxContentLength:
    """Requests over 10MB are rejected with 413."""

    def test_oversized_request_returns_413(self, client):
        big_body = "x" * (11 * 1024 * 1024)  # 11MB
        resp = client.post(
            "/print/message",
            data=big_body,
            content_type="application/json",
        )
        assert resp.status_code == 413


class TestValidRequestSucceeds:
    """Valid POST with required fields returns 200."""

    def test_message_with_text_returns_200(self, client):
        resp = client.post("/print/message", json={"text": "hello"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["template"] == "message"


class TestErrorResponseFormat:
    """All error responses have 'error' key as string."""

    def test_validation_error_has_error_key(self, client):
        resp = client.post("/print/message", json={})
        data = resp.get_json()
        assert "error" in data
        assert isinstance(data["error"], str)

    def test_invalid_json_error_has_error_key(self, client):
        resp = client.post(
            "/print/receipt",
            data="garbage",
            content_type="application/json",
        )
        data = resp.get_json()
        assert "error" in data
        assert isinstance(data["error"], str)


class TestNoRawEscPosInServer:
    """Static check: no _raw() calls exist in print_server.py source."""

    def test_no_raw_calls_in_source(self):
        with open("print_server.py") as f:
            source = f.read()
        # Exclude comments and docstrings by checking actual method calls
        lines = source.split("\n")
        raw_calls = [
            line.strip()
            for line in lines
            if "_raw(" in line and not line.strip().startswith("#")
        ]
        assert raw_calls == [], f"Found _raw() calls in print_server.py: {raw_calls}"


class TestGracefulShutdown:
    """Verify graceful_shutdown handler exists and is wired to SIGTERM/SIGINT."""

    def test_graceful_shutdown_is_callable(self):
        import print_server
        assert hasattr(print_server, "graceful_shutdown")
        assert callable(print_server.graceful_shutdown)

    def test_sigterm_registration_in_source(self):
        """Verify signal.signal(signal.SIGTERM, graceful_shutdown) appears in main()."""
        with open("print_server.py") as f:
            source = f.read()
        assert "signal.signal(signal.SIGTERM, graceful_shutdown)" in source
        assert "signal.signal(signal.SIGINT, graceful_shutdown)" in source

    def test_shutdown_does_not_acquire_print_lock(self):
        """Signal handler must not acquire _print_lock (deadlock risk)."""
        with open("print_server.py") as f:
            source = f.read()
        # Extract the graceful_shutdown function body
        in_func = False
        func_lines = []
        for line in source.split("\n"):
            if "def graceful_shutdown" in line:
                in_func = True
                continue
            elif in_func:
                if line and not line[0].isspace() and line.strip():
                    break  # next top-level def/class
                func_lines.append(line)
        func_body = "\n".join(func_lines)
        assert "_print_lock" not in func_body, \
            "graceful_shutdown must not reference _print_lock (deadlock risk)"


class TestPortraitConfigNotMutated:
    """Verify run_pipeline does not mutate the shared config dict."""

    def test_config_unchanged_after_run_pipeline(self):
        """After calling run_pipeline with blur/dither_mode overrides, config is unchanged."""
        pytest.importorskip("numpy", reason="portrait_pipeline requires numpy")
        portrait_pipeline = __import__("portrait_pipeline")

        config = {
            "portrait": {"blur": 10, "dither_mode": "bayer"},
            "printer": {"paper_width": 48},
            "halftone": {"paper_px": 576},
        }
        original = copy.deepcopy(config)

        mock_printer = MagicMock()

        with patch.object(portrait_pipeline, "select_best_photo") as mock_select, \
             patch.object(portrait_pipeline, "open_image") as mock_open, \
             patch.object(portrait_pipeline, "print_portrait") as mock_print:

            mock_open.return_value = MagicMock()

            portrait_pipeline.run_pipeline(
                ["fake_image.jpg"], config, mock_printer,
                dummy=True,
                skip_selection=True,
                skip_transform=True,
                blur=5.0,
                dither_mode="floyd",
            )

        assert config == original, \
            f"run_pipeline mutated config! Before: {original}, After: {config}"

    def test_no_config_setdefault_in_run_pipeline(self):
        """Static check: config.setdefault should not appear in portrait_pipeline.py."""
        with open("portrait_pipeline.py") as f:
            source = f.read()
        assert "config.setdefault" not in source, \
            "portrait_pipeline.py still contains config.setdefault (config mutation)"


class TestAuth:
    """API key authentication when api_key is configured."""

    def test_no_key_returns_401(self, client_with_auth):
        resp = client_with_auth.post("/print/message", json={"text": "hi"})
        assert resp.status_code == 401
        data = resp.get_json()
        assert "error" in data

    def test_wrong_key_returns_401(self, client_with_auth):
        resp = client_with_auth.post(
            "/print/message",
            json={"text": "hi"},
            headers={"X-Print-Key": "wrong"},
        )
        assert resp.status_code == 401

    def test_correct_key_returns_200(self, client_with_auth):
        resp = client_with_auth.post(
            "/print/message",
            json={"text": "hi"},
            headers={"X-Print-Key": "test-secret-key"},
        )
        assert resp.status_code == 200

    def test_health_no_key_returns_200(self, client_with_auth):
        resp = client_with_auth.get("/health")
        assert resp.status_code == 200

    def test_index_no_key_returns_200(self, client_with_auth):
        resp = client_with_auth.get("/")
        assert resp.status_code == 200


class TestAuthDisabled:
    """When no api_key is set in config, all endpoints are open."""

    def test_no_key_config_allows_all(self, client):
        resp = client.post("/print/message", json={"text": "hi"})
        assert resp.status_code == 200


class TestHealthEnhanced:
    """Enhanced /health endpoint returns printer status, uptime, and last_print."""

    def test_health_has_printer_field(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        assert "printer" in data

    def test_health_has_uptime_field(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))

    def test_health_has_last_print_field(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        assert "last_print" in data

    def test_health_dummy_mode_printer_status(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        assert data["printer"] == "dummy"
