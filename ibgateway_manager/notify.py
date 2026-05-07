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


def launch_reason() -> str:
    """Resolve a human-readable label for whatever triggered this gateway run.

    Resolution order:
      1. ``IBGATEWAY_LAUNCH_REASON`` env var — caller-supplied free-form
         string (e.g. set by the CFN task definition for ECS, or by a
         workflow's ``docker run -e`` for CI). This wins when set so each
         caller can describe itself precisely.
      2. ``GITHUB_ACTIONS=true`` — auto-build a CI label from the standard
         GitHub Actions env vars so we never silently fall back to "unknown"
         on a runner that forgot to set the explicit env var.
      3. ``"unknown"`` — explicit fallback so the operator sees "we don't
         know who started this" rather than nothing.
    """
    explicit = os.getenv("IBGATEWAY_LAUNCH_REASON", "").strip()
    if explicit:
        return explicit
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        wf = os.getenv("GITHUB_WORKFLOW", "?")
        repo = os.getenv("GITHUB_REPOSITORY", "?")
        run_id = os.getenv("GITHUB_RUN_ID", "?")
        server = os.getenv("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
        return f"ci:{wf} ({server}/{repo}/actions/runs/{run_id})"
    return "unknown"


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
