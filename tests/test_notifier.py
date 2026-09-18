"""Tests for the notifier module."""

import io
import urllib.error
import pytest

from flaktor.notifier import build_flaky_alert_payload, send_webhook, NotifierError


class TestBuildFlakyAlertPayload:
    """Tests for building the webhook payload."""

    def test_payload_contains_expected_fields(self):
        """Test the payload has a text summary, count, and full test list."""
        tests = [
            {"test_name": "test_a", "flip_rate": 0.8, "pass_rate": 0.6, "total_runs": 10},
        ]

        payload = build_flaky_alert_payload(tests)

        assert payload["event"] == "new_flaky_tests"
        assert payload["count"] == 1
        assert payload["tests"] == tests
        assert "generated_at" in payload
        assert "test_a" in payload["text"]
        assert "80%" in payload["text"]

    def test_payload_singular_wording(self):
        """Test the summary text uses singular wording for exactly one test."""
        tests = [{"test_name": "test_a", "flip_rate": 0.5, "pass_rate": 0.5, "total_runs": 4}]

        payload = build_flaky_alert_payload(tests)

        assert "1 new flaky test detected" in payload["text"]

    def test_payload_truncates_long_lists(self):
        """Test only the first 10 tests are listed by name, with a remainder note."""
        tests = [
            {"test_name": f"test_{i}", "flip_rate": 0.5, "pass_rate": 0.5, "total_runs": 4}
            for i in range(15)
        ]

        payload = build_flaky_alert_payload(tests)

        assert "test_9" in payload["text"]
        assert "test_10" not in payload["text"]
        assert "5 more" in payload["text"]
        assert payload["count"] == 15
        assert len(payload["tests"]) == 15


class TestSendWebhook:
    """Tests for sending the webhook HTTP request."""

    def test_send_webhook_rejects_non_http_scheme(self):
        """Test a non-http(s) URL scheme is rejected before any network call."""
        with pytest.raises(NotifierError, match="Unsupported webhook URL scheme"):
            send_webhook("file:///etc/passwd", {"text": "hi"})

    def test_send_webhook_success(self, monkeypatch):
        """Test a successful POST doesn't raise."""
        class FakeResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["body"] = request.data
            return FakeResponse()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        send_webhook("https://example.com/hook", {"text": "hi"})

        assert captured["url"] == "https://example.com/hook"
        assert captured["method"] == "POST"
        assert b"hi" in captured["body"]

    def test_send_webhook_http_error(self, monkeypatch):
        """Test an HTTPError from the server is wrapped in NotifierError."""
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 500, "Internal Server Error", None, io.BytesIO()
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        with pytest.raises(NotifierError, match="500"):
            send_webhook("https://example.com/hook", {"text": "hi"})

    def test_send_webhook_url_error(self, monkeypatch):
        """Test a connection failure is wrapped in NotifierError."""
        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        with pytest.raises(NotifierError, match="Failed to reach webhook URL"):
            send_webhook("https://example.com/hook", {"text": "hi"})
