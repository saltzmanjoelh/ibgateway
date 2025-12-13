import os
import tempfile
import unittest
import subprocess

from ibgateway.cli import IBGatewayCLI


def _write_exe(path: str, contents: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(contents)
    os.chmod(path, 0o755)


class TestCLIInstallAndRun(unittest.TestCase):
    def test_install_ibgateway_success(self) -> None:
        cli = IBGatewayCLI()

        with tempfile.TemporaryDirectory() as td:
            installer = os.path.join(td, "installer.sh")
            _write_exe(
                installer,
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "# accept: -q -f <log>\n"
                "log=''\n"
                "while [[ $# -gt 0 ]]; do\n"
                "  case \"$1\" in\n"
                "    -f) log=\"$2\"; shift 2;;\n"
                "    *) shift;;\n"
                "  esac\n"
                "done\n"
                "echo 'installed' > \"${log:-/tmp/install-ibgateway.log}\"\n"
                "exit 0\n",
            )

            old = os.environ.get("IBGATEWAY_INSTALLER_PATH")
            os.environ["IBGATEWAY_INSTALLER_PATH"] = installer
            try:
                self.assertEqual(cli._install_ibgateway(verbose=False, use_latest=False), 0)
            finally:
                if old is None:
                    os.environ.pop("IBGATEWAY_INSTALLER_PATH", None)
                else:
                    os.environ["IBGATEWAY_INSTALLER_PATH"] = old

    def test_install_ibgateway_calledprocesserror_returns_1(self) -> None:
        cli = IBGatewayCLI()
        with tempfile.TemporaryDirectory() as td:
            installer = os.path.join(td, "installer.sh")
            _write_exe(installer, "#!/usr/bin/env bash\nexit 1\n")

            old = os.environ.get("IBGATEWAY_INSTALLER_PATH")
            os.environ["IBGATEWAY_INSTALLER_PATH"] = installer
            try:
                self.assertEqual(cli._install_ibgateway(verbose=False, use_latest=False), 1)
            finally:
                if old is None:
                    os.environ.pop("IBGATEWAY_INSTALLER_PATH", None)
                else:
                    os.environ["IBGATEWAY_INSTALLER_PATH"] = old

    def test_run_ibgateway_normal_exit(self) -> None:
        cli = IBGatewayCLI()
        with tempfile.TemporaryDirectory() as td:
            xvfb = os.path.join(td, "Xvfb")
            ib = os.path.join(td, "ibgateway")
            _write_exe(xvfb, "#!/usr/bin/env bash\nexit 0\n")
            _write_exe(ib, "#!/usr/bin/env bash\nexit 0\n")

            old_env = dict(os.environ)
            os.environ["XVFB_BIN"] = xvfb
            os.environ["IBGATEWAY_BIN"] = ib
            os.environ["IBGATEWAY_XVFB_STARTUP_DELAY"] = "0"
            os.environ["IBGATEWAY_STARTUP_DELAY"] = "0"
            os.environ["IBGATEWAY_SLEEP_SCALE"] = "0"
            try:
                # Recreate CLI so it reloads Config overrides.
                cli = IBGatewayCLI()
                self.assertEqual(cli._run_ibgateway(verbose=False), 0)
            finally:
                os.environ.clear()
                os.environ.update(old_env)
