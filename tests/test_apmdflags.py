import unittest

from powerstar.apmdflags import auto_sleep, with_auto_sleep, without_perf_flags


class ApmdFlagsTest(unittest.TestCase):
    def test_with_auto_sleep(self):
        self.assertEqual(with_auto_sleep("-A", "suspend", 5), "-A -z 5")
        self.assertEqual(with_auto_sleep("-A -z 5 -t 30", None, None), "-A -t 30")
        self.assertEqual(with_auto_sleep("-z5 -A", "hibernate", 3), "-A -Z 3")

    def test_auto_sleep(self):
        self.assertEqual(auto_sleep("-z5 -Z 3"), ("hibernate", 3))
        self.assertEqual(auto_sleep("-A -z 5"), ("suspend", 5))
        self.assertEqual(auto_sleep("-A"), (None, None))

    def test_without_perf_flags(self):
        self.assertEqual(without_perf_flags("-A -z 5"), "-z 5")
        self.assertEqual(without_perf_flags("-aA"), "-a")
        self.assertEqual(without_perf_flags("-A"), "")
