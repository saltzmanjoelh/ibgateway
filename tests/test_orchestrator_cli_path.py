"""Tests for ``resolve_ibgateway_manager_cli_script`` (orchestrator CLI path resolution)."""

import tempfile
import unittest
from pathlib import Path

from ibgateway_manager.orchestrator import resolve_ibgateway_manager_cli_script


class TestResolveIbgatewayManagerCliScript(unittest.TestCase):
    def test_prefers_docker_path_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docker = Path(tmp) / "ibgateway_manager_cli.py"
            docker.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            repo_root = Path(tmp) / "repo"
            pkg = repo_root / "ibgateway_manager"
            pkg.mkdir(parents=True)
            orchestrator = pkg / "orchestrator.py"
            orchestrator.write_text("", encoding="utf-8")
            workspace_cli = repo_root / "ibgateway_manager_cli.py"
            workspace_cli.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

            resolved = resolve_ibgateway_manager_cli_script(
                docker_cli_path=docker,
                orchestrator_file=orchestrator,
            )
            self.assertEqual(resolved, str(docker))

    def test_falls_back_to_repo_root_next_to_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docker = Path(tmp) / "nonexistent_ibgateway_manager_cli.py"
            repo_root = Path(tmp) / "repo"
            pkg = repo_root / "ibgateway_manager"
            pkg.mkdir(parents=True)
            orchestrator = pkg / "orchestrator.py"
            orchestrator.write_text("", encoding="utf-8")
            workspace_cli = repo_root / "ibgateway_manager_cli.py"
            workspace_cli.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

            resolved = resolve_ibgateway_manager_cli_script(
                docker_cli_path=docker,
                orchestrator_file=orchestrator,
            )
            self.assertEqual(resolved, str(workspace_cli))

    def test_returns_docker_string_when_neither_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docker = Path(tmp) / "missing_docker_cli.py"
            repo_root = Path(tmp) / "repo"
            pkg = repo_root / "ibgateway_manager"
            pkg.mkdir(parents=True)
            orchestrator = pkg / "orchestrator.py"
            orchestrator.write_text("", encoding="utf-8")

            resolved = resolve_ibgateway_manager_cli_script(
                docker_cli_path=docker,
                orchestrator_file=orchestrator,
            )
            self.assertEqual(resolved, str(docker))


if __name__ == "__main__":
    unittest.main()
