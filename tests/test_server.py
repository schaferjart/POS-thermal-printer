"""Integration tests for print_server.py input validation, error format, and ESC@ init."""

import json


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
