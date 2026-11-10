import unittest

from powerstar.sysctlconf import current_value, disable_key, set_value

BOX = "# my box\nhw.smt=1\n# start and stop charge at 40 and 80\nhw.battery.chargestart=40\nhw.battery.chargestop=80\n"


class SysctlConfTest(unittest.TestCase):
    def test_replace_only_that_line(self):
        out = set_value(BOX, "hw.battery.chargestop", "90")
        self.assertEqual(out, BOX.replace("chargestop=80", "chargestop=90"))

    def test_append(self):
        self.assertEqual(set_value(BOX, "hw.x", "1"), BOX + "# added by powerstar\nhw.x=1\n")

    def test_append_without_trailing_newline(self):
        self.assertEqual(set_value("a=1", "hw.x", "1"), "a=1\n# added by powerstar\nhw.x=1\n")

    def test_append_to_empty(self):
        self.assertEqual(set_value("", "hw.x", "1"), "# added by powerstar\nhw.x=1\n")

    def test_no_trailing_newline_kept_on_replace(self):
        self.assertEqual(set_value("hw.smt=1", "hw.smt", "0"), "hw.smt=0")

    def test_duplicates(self):
        out = set_value("hw.x=1\nfoo=2\n  hw.x = 2\n", "hw.x", "3")
        self.assertEqual(out, "# disabled by powerstar: hw.x=1\nfoo=2\n  hw.x=3\n")

    def test_inline_comment_kept(self):
        self.assertEqual(set_value("hw.smt=1 # x\n", "hw.smt", "0"), "hw.smt=0 # x\n")

    def test_commented_line_ignored(self):
        text = "#hw.perfpolicy=high\n"
        self.assertIsNone(current_value(text, "hw.perfpolicy"))
        self.assertEqual(set_value(text, "hw.perfpolicy", "auto"), text + "# added by powerstar\nhw.perfpolicy=auto\n")

    def test_disable_key(self):
        self.assertIn("# disabled by powerstar: hw.smt=1\n", disable_key(BOX, "hw.smt"))
        self.assertEqual(disable_key(BOX, "hw.nothing"), BOX)

    def test_idempotent(self):
        self.assertEqual(set_value(BOX, "hw.battery.chargestop", "80"), BOX)

    def test_current_value_last_wins(self):
        self.assertEqual(current_value("hw.x=1\nhw.x=2 # c\n", "hw.x"), "2")
