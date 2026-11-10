import unittest

from powerstar.blockcpu import blocked, compose, problem

BOX = {"P", "S"}


class BlockCpuTest(unittest.TestCase):
    def test_blocked(self):
        self.assertEqual(blocked("SL"), {"S", "L"})

    def test_compose(self):
        self.assertEqual(compose("L", {"S"}, BOX), "SL")
        self.assertEqual(compose("SL", set(), BOX), "L")
        self.assertEqual(compose("", {"S", "P"}, BOX), "SP")

    def test_problem(self):
        self.assertEqual(problem({"P"}, BOX), "This would leave only one CPU running")
        self.assertIsNone(problem({"S"}, BOX))
        self.assertIsNone(problem({"P"}, {"P", "E", "S"}))
