"""Launcher: server-check en browser zoeken (zonder echt een browser te starten)."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import launcher  # noqa: E402


class LauncherTests(unittest.TestCase):
    def test_server_not_up(self):
        self.assertFalse(launcher.server_up(1))

    def test_no_browser_found(self):
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}), mock.patch("pathlib.Path.exists", return_value=False):
            self.assertIsNone(launcher.find_browser("chrome"))

    def test_fallback_to_default_browser(self):
        with mock.patch.object(launcher, "find_browser", return_value=None), \
                mock.patch.object(launcher.webbrowser, "open") as op:
            self.assertIsNone(launcher.open_window("http://localhost:1/", "chrome", False, Path("/tmp/x")))
            op.assert_called_once()


    def test_pi_install_script_syntax(self):
        import shutil
        import subprocess
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("geen bash")
        script = Path(__file__).resolve().parent.parent / "install_pi.sh"
        self.assertEqual(subprocess.run([bash, "-n", str(script)]).returncode, 0)

    def test_pi_flags(self):
        import launcher
        self.assertEqual(launcher.pi_flags("x86_64", {}), [])
        f = launcher.pi_flags("aarch64", {"WAYLAND_DISPLAY": "wayland-0"})
        self.assertIn("--enable-gpu-rasterization", f)
        self.assertIn("--ozone-platform=wayland", f)
        f = launcher.pi_flags("armv7l", {"AFGOOIEN_GPU": "0"})
        self.assertNotIn("--enable-gpu-rasterization", f)
        self.assertNotIn("--ozone-platform=wayland", f)
        self.assertIn("--disable-background-networking", f)

    def test_pi_install_has_tuning(self):
        script = (Path(__file__).resolve().parent.parent / "install_pi.sh").read_text()
        self.assertIn("Nice=-5", script)
        self.assertIn("afgooien-snelheid.service", script)
        self.assertIn("--geen-turbo", script)


if __name__ == "__main__":
    unittest.main()
