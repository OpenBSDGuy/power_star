import tempfile
import unittest
from pathlib import Path

from powerstar import userconfig


class UserConfigTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "sub" / "config.toml"

    def test_missing(self):
        self.assertEqual(userconfig.load(self.path), userconfig.DEFAULTS)

    def test_round_trip(self):
        cfg = {**userconfig.DEFAULTS, "brightness": 40, "menu_perf": "H", "show_percent": False}
        userconfig.save(cfg, self.path)
        self.assertEqual(userconfig.load(self.path), cfg)
        self.assertNotIn("screen_off_minutes", self.path.read_text())  # None is skipped

    def test_broken(self):
        self.path.parent.mkdir()
        self.path.write_text("this is [not toml")
        self.assertEqual(userconfig.load(self.path), userconfig.DEFAULTS)
