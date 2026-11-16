"""Salary match rule follows the era: 125% + $100k until 2022, banded rule after."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trades.salary_rules import salary_match_ok


def ok(**kw):
    base = dict(payroll=45.0, incoming=0.0, outgoing=0.0, cap=40.27, second_apron=9999.0,
                year=2002, cba_mode="realistic")
    base.update(kw)
    return salary_match_ok(**base)[0]


class SalaryRulesTest(unittest.TestCase):
    def test_under_cap_after_trade_always_ok(self):
        self.assertTrue(ok(payroll=30.0, incoming=8.0, outgoing=3.0))

    def test_2002_over_cap_125_plus_100k(self):
        self.assertTrue(ok(incoming=3.85, outgoing=3.0))      # 3.0 * 1.25 + 0.1
        self.assertFalse(ok(incoming=3.86, outgoing=3.0))
        self.assertFalse(ok(incoming=8.0, outgoing=3.0))

    def test_2015_uses_125_rule(self):
        self.assertTrue(ok(year=2015, cap=70.0, payroll=75.0, incoming=10.1, outgoing=8.0))
        self.assertFalse(ok(year=2015, cap=70.0, payroll=75.0, incoming=10.2, outgoing=8.0))

    def test_2025_modern_bands_scaled(self):
        kw = dict(year=2025, cap=155.0, payroll=160.0)
        self.assertTrue(ok(incoming=6.0 * 1.75 + 0.25, outgoing=6.0, **kw))
        self.assertFalse(ok(incoming=6.0 * 1.75 + 0.3, outgoing=6.0, **kw))
        self.assertTrue(ok(incoming=15.0 + 5.0, outgoing=15.0, **kw))
        self.assertTrue(ok(incoming=30.0 * 1.25 + 0.25, outgoing=30.0, **kw))
        self.assertFalse(ok(incoming=30.0 * 1.25 + 0.3, outgoing=30.0, **kw))

    def test_2025_bands_scale_with_cap(self):
        # cap 77.5 is half the reference: 3.0 out is the same as 6.0 at the reference
        self.assertTrue(ok(year=2025, cap=77.5, payroll=80.0, incoming=(6.0 * 1.75 + 0.25) / 2, outgoing=3.0))
        self.assertFalse(ok(year=2025, cap=77.5, payroll=80.0, incoming=(6.0 * 1.75 + 0.25) / 2 + 0.1, outgoing=3.0))

    def test_2025_second_apron_110(self):
        kw = dict(year=2025, cap=155.0, payroll=200.0, second_apron=190.0)
        self.assertTrue(ok(incoming=11.0, outgoing=10.0, **kw))
        self.assertFalse(ok(incoming=11.1, outgoing=10.0, **kw))

    def test_2002_over_second_apron_still_125_plus_100k(self):
        self.assertTrue(ok(payroll=60.0, second_apron=50.0, incoming=3.85, outgoing=3.0))
        self.assertFalse(ok(payroll=60.0, second_apron=50.0, incoming=3.86, outgoing=3.0))

    def test_no_cap_mode_always_ok(self):
        self.assertTrue(ok(incoming=99.0, outgoing=1.0, cba_mode="no_cap"))
        self.assertTrue(ok(incoming=99.0, outgoing=1.0, cap=9999.0))


if __name__ == "__main__":
    unittest.main()
