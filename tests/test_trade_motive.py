import unittest

from trades.motive import (SideMotive, TradeMotive, reasons_for, why_line,
                           user_side_motive, log_line, REASON_TEMPLATES, TRAIT_REASONS, TRAIT_KINDS, WHY_PHRASES)


def _side(team="Denver", **kw):
    base = dict(team=team, gm_name="Pat Ross", trade_skill=60, plan="REBUILDER", traits=["PICK_HOARDER"],
                wish_kind="SELL_VETERANS", need=None, reasons=["a"], value_given=10.0, value_received=12.0)
    base.update(kw)
    return SideMotive(**base)


class TradeMotiveTests(unittest.TestCase):
    def test_public_dict_drops_values(self):
        d = _side().to_dict(public=True)
        self.assertNotIn("value_given", d)
        self.assertNotIn("value_received", d)
        self.assertIn("value_given", _side().to_dict(public=False))

    def test_round_trip(self):
        m = TradeMotive("veteran_sale", "why", [_side(), user_side_motive("Boston")], 2)
        self.assertEqual(TradeMotive.from_dict(m.to_dict(public=False)), m)

    def test_need_starter_reasons(self):
        r = reasons_for("NEED_STARTER", team="Sacramento", plan="CONTENDER", traits=["DEFENSE_FIRST"],
                        gets=["Howard (PF, 78)"], gives=["Smith (PF, 60)"], need="PF")
        self.assertTrue(2 <= len(r) <= 3)
        self.assertTrue(any("PF" in s for s in r))
        for s in r:
            self.assertNotIn("%", s)
            self.assertNotIn("x1.", s)

    def test_no_wish_gives_empty(self):
        self.assertEqual(reasons_for(None, team="A", plan="MIDDLE", traits=[], gets=[], gives=[], need=None), [])

    def test_why_line_skips_user(self):
        sides = [_side("Sacramento", wish_kind="NEED_STARTER", need="PF", plan="CONTENDER"),
                 user_side_motive("Boston"), _side("Denver")]
        line = why_line("star_upgrade", sides)
        self.assertIn(" · ", line)
        self.assertNotIn("Boston", line)
        self.assertIn("Sacramento needed a starting PF", line)

    def test_user_side(self):
        s = user_side_motive("Boston")
        self.assertEqual((s.plan, s.reasons), ("USER", []))

    def test_log_line(self):
        m = TradeMotive("veteran_sale", "Denver sells", [_side(), user_side_motive("Boston")], 2)
        line = log_line(m, {"Denver": "Smith", "Boston": "a 1st"})
        self.assertIn("Denver", line)
        self.assertIn("a 1st", line)

    def test_tables_nonempty(self):
        self.assertEqual(len(REASON_TEMPLATES), 18)
        self.assertEqual(len(TRAIT_REASONS), 10)

    def test_no_engine_numbers_in_any_sentence(self):
        sentences = [t for ts in REASON_TEMPLATES.values() for t in ts] + list(WHY_PHRASES.values()) + list(TRAIT_REASONS.values())
        for s in sentences:
            self.assertFalse(any(c.isdigit() for c in s), s)
            self.assertNotIn("%", s)
            self.assertNotIn("x1.", s)

    def test_templates_do_not_assume_one_player(self):
        import re
        for kind, ts in REASON_TEMPLATES.items():
            for s in ts:
                self.assertIsNone(re.search(r"\{(gives|gets)\} (is|was|has|needs|can|drops|carries|costs|fits|adds|asked|are|were)\b", s), s)   # no verb agreeing with the names
                self.assertNotRegex(s.lower(), r"\b(him|he|his)\b", s)

    def test_star_chaser_trait_only_on_want_star(self):
        self.assertEqual(TRAIT_KINDS["STAR_CHASER"], ("WANT_STAR",))
        out = reasons_for("NEED_STARTER", team="A", plan="CONTENDER", traits=["STAR_CHASER"], gets=["X", "Y"],
                          gives=["Z"], need="C")
        self.assertNotIn(TRAIT_REASONS["STAR_CHASER"], out)


if __name__ == "__main__":
    unittest.main()
