import contextlib
import io
import unittest
from unittest import mock

from powerstar.cli import main


class CliTest(unittest.TestCase):
    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--version"]), 0)
        self.assertEqual(out.getvalue().strip(), "powerstar 0.1.0")

    def test_missing_pyqt6_prints_install_hint(self):
        err = io.StringIO()
        with mock.patch("importlib.util.find_spec", return_value=None), contextlib.redirect_stderr(err):
            self.assertEqual(main([]), 1)
        self.assertIn("doas pkg_add py3-qt6", err.getvalue())
        self.assertIn("pipx install --system-site-packages powerstar", err.getvalue())
