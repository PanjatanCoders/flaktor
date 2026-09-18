"""
Webhook notifications for Flaktor.

Sends a plain HTTP POST with a JSON body using only the standard library,
so notifications work without adding an HTTP client dependency to the base
install. The payload's "text" field is compatible as-is with Slack
Incoming Webhooks.
"""

import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import List
from urllib.parse import urlparse


class NotifierError(Exception):
    """Raised when a webhook notification fails to send."""
    pass


def build_flaky_alert_payload(new_flaky_tests: List[dict]) -> dict:
    """
    Build the webhook JSON payload for newly detected flaky tests.

    Args:
        new_flaky_tests: Flaky-test dicts (as returned by
            Database.get_flaky_tests) for tests not previously alerted on

    Returns:
        A JSON-serializable dict with a human-readable "text" summary
        (usable directly as a Slack Incoming Webhook payload) plus the
        full test list for consumers that want structured data.
    """
    count = len(new_flaky_tests)
    plural = "test" if count == 1 else "tests"
    lines = [f"🔴 {count} new flaky {plural} detected:"]
    for test in new_flaky_tests[:10]:
        lines.append(
            f"  • {test['test_name']} "
            f"(flip rate {test['flip_rate']*100:.0f}%, {test['total_runs']} runs)"
        )
    if count > 10:
        lines.append(f"  ...and {count - 10} more")

    return {
        "text": "\n".join(lines),
        "event": "new_flaky_tests",
        "count": count,
        "tests": new_flaky_tests,
        "generated_at": datetime.now().isoformat(),
    }


def send_webhook(url: str, payload: dict, timeout: float = 10.0) -> None:
    """
    POST a JSON payload to a webhook URL.

    Args:
        url: Destination webhook URL (must be http:// or https://)
        payload: JSON-serializable body
        timeout: Request timeout in seconds

    Raises:
        NotifierError: If the URL scheme is unsupported, the request
            can't reach the server, or the server returns an error status
    """
    scheme = urlparse(url).scheme
    if scheme not in ("http", "https"):
        raise NotifierError(
            f"Unsupported webhook URL scheme '{scheme or url}'. Use http:// or https://."
        )

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status >= 400:
                raise NotifierError(f"Webhook returned HTTP {response.status}")
    except urllib.error.HTTPError as e:
        raise NotifierError(f"Webhook returned HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise NotifierError(f"Failed to reach webhook URL: {e.reason}")
