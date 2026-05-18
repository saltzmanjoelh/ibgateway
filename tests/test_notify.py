"""Tests for the Slack notifier (KIM-200 follow-up — include task id in prefix).

Focuses on the new ECS task-id enrichment path:
  * On ECS (metadata endpoint reachable) the prefix becomes
    ``[ibgateway @ <host>/<task_id>]``
  * Off ECS (env var unset) the prefix stays ``[ibgateway @ <host>]``
  * A malformed metadata response is treated like "off ECS" (graceful
    degrade — we never want a flaky metadata endpoint to prevent a
    notification from going out)
"""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from ibgateway_manager import notify


def _fake_urlopen(body: object | None, status: int = 200):
    """Build a urlopen replacement that returns a context-manager
    whose .read() yields json.dumps(body), and whose .status is `status`."""

    def _opener(_req, timeout=None):  # noqa: ARG001
        encoded = json.dumps(body).encode("utf-8") if body is not None else b""
        resp = mock.MagicMock()
        resp.status = status
        resp.read.return_value = encoded
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    return _opener


class _EnvSandbox(unittest.TestCase):
    """Snapshot SLACK_WEBHOOK_URL + ECS_CONTAINER_METADATA_URI_V4 around
    each test so the lookups don't leak across cases — and clear the
    lru_cache so each test re-resolves the task id from scratch."""

    def setUp(self) -> None:
        self._env_snapshot = os.environ.copy()
        notify._ecs_task_id.cache_clear()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_snapshot)
        notify._ecs_task_id.cache_clear()


class TestEcsTaskId(_EnvSandbox):
    def test_env_var_unset_returns_empty(self) -> None:
        os.environ.pop("ECS_CONTAINER_METADATA_URI_V4", None)
        self.assertEqual(notify._ecs_task_id(), "")

    def test_extracts_short_id_from_task_arn(self) -> None:
        os.environ["ECS_CONTAINER_METADATA_URI_V4"] = "http://169.254.170.2/v4/abc"
        arn = (
            "arn:aws:ecs:us-east-1:123456789012:task/cluster/"
            "9e7f8a1d4c0b4a2b8e9d0c1f2a3b4c5d"
        )
        with mock.patch.object(
            notify.urllib.request,
            "urlopen",
            _fake_urlopen({"TaskARN": arn}),
        ):
            self.assertEqual(
                notify._ecs_task_id(),
                "9e7f8a1d4c0b4a2b8e9d0c1f2a3b4c5d",
            )

    def test_malformed_response_returns_empty(self) -> None:
        os.environ["ECS_CONTAINER_METADATA_URI_V4"] = "http://169.254.170.2/v4/abc"
        with mock.patch.object(
            notify.urllib.request,
            "urlopen",
            _fake_urlopen({"NotTheRightField": "x"}),
        ):
            self.assertEqual(notify._ecs_task_id(), "")

    def test_network_error_returns_empty(self) -> None:
        os.environ["ECS_CONTAINER_METADATA_URI_V4"] = "http://169.254.170.2/v4/abc"
        with mock.patch.object(
            notify.urllib.request,
            "urlopen",
            side_effect=OSError("network down"),
        ):
            self.assertEqual(notify._ecs_task_id(), "")

    def test_non_2xx_returns_empty(self) -> None:
        os.environ["ECS_CONTAINER_METADATA_URI_V4"] = "http://169.254.170.2/v4/abc"
        with mock.patch.object(
            notify.urllib.request,
            "urlopen",
            _fake_urlopen({}, status=500),
        ):
            self.assertEqual(notify._ecs_task_id(), "")

    def test_arn_without_slash_returns_empty(self) -> None:
        os.environ["ECS_CONTAINER_METADATA_URI_V4"] = "http://169.254.170.2/v4/abc"
        with mock.patch.object(
            notify.urllib.request,
            "urlopen",
            _fake_urlopen({"TaskARN": "garbage"}),
        ):
            self.assertEqual(notify._ecs_task_id(), "")


class TestNotifyPrefix(_EnvSandbox):
    """Assert the assembled prefix shape with + without task id."""

    def test_includes_task_id_when_on_ecs(self) -> None:
        os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.example/test"
        os.environ["ECS_CONTAINER_METADATA_URI_V4"] = "http://meta"
        arn = "arn:aws:ecs:us-east-1:1:task/cluster/abc12345"
        captured: dict[str, bytes] = {}

        def _capture_urlopen(req, timeout=None):  # noqa: ARG001
            # urlopen is used for BOTH metadata (string URL) and Slack
            # POST (Request object). Branch on which form we got.
            url = req if isinstance(req, str) else req.full_url
            if "meta" in url:
                return _fake_urlopen({"TaskARN": arn})(req, timeout=timeout)
            captured["url"] = url
            captured["body"] = req.data
            resp = mock.MagicMock()
            resp.status = 200
            resp.read.return_value = b""
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            return resp

        with mock.patch.object(
            notify.urllib.request, "urlopen", side_effect=_capture_urlopen
        ):
            self.assertTrue(notify.notify_slack("hello"))

        payload = json.loads(captured["body"])
        self.assertTrue(payload["text"].startswith("[ibgateway @ "))
        self.assertIn("/abc12345]", payload["text"])
        self.assertTrue(payload["text"].endswith(" hello"))

    def test_omits_task_id_when_off_ecs(self) -> None:
        os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.example/test"
        os.environ.pop("ECS_CONTAINER_METADATA_URI_V4", None)
        captured: dict[str, bytes] = {}

        def _capture_urlopen(req, timeout=None):  # noqa: ARG001
            captured["body"] = req.data
            resp = mock.MagicMock()
            resp.status = 200
            resp.read.return_value = b""
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            return resp

        with mock.patch.object(
            notify.urllib.request, "urlopen", side_effect=_capture_urlopen
        ):
            self.assertTrue(notify.notify_slack("hello"))

        payload = json.loads(captured["body"])
        # No task-id segment — the prefix is just host.
        prefix = payload["text"].split("]")[0]
        self.assertNotIn("/", prefix)
        self.assertTrue(payload["text"].endswith(" hello"))


if __name__ == "__main__":
    unittest.main()
