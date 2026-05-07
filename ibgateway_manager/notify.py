"""Best-effort Slack notifier for runtime MFA-triggering events.

Set ``SLACK_WEBHOOK_URL`` in the environment to enable. If unset, every
notify call is a no-op. If the webhook is unreachable or returns non-2xx,
the failure is logged at WARNING and ``False`` is returned — the calling
path never raises, since blocking the gateway on Slack availability would
defeat the purpose.

We send to a Slack incoming webhook (https://api.slack.com/messaging/webhooks)
with a minimal ``{"text": "..."}`` payload so this works for the simplest
webhook configurations without any extra setup.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import urllib.error
import urllib.request

_logger = logging.getLogger(__name__)
_TIMEOUT_SECONDS = 5.0


def notify_slack(text: str) -> bool:
    """POST ``text`` to the Slack incoming webhook in ``SLACK_WEBHOOK_URL``.

    Returns ``True`` on 2xx, ``False`` if the env var is unset, the request
    failed, or the response was non-2xx. Never raises.
    """
    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return False

    try:
        host = socket.gethostname()
    except OSError:
        host = "?"

    payload = {"text": f"[ibgateway @ {host}] {text}"}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            if 200 <= resp.status < 300:
                return True
            _logger.warning(
                "Slack notify HTTP %s: %s",
                resp.status,
                resp.read(256).decode("utf-8", errors="replace"),
            )
            return False
    except (urllib.error.URLError, OSError) as exc:
        _logger.warning("Slack notify failed: %s", exc)
        return False
