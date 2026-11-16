"""Contract rules (core/front_office/contracts.py): earned loyalty, stars walking away, renewals by plan."""
import unittest
from types import SimpleNamespace

from core.front_office import contracts
from tests.test_wishes import balanced, ctx_of, roster_with, team_of
from tests.trade_fixtures import make_player


def aged(p, age, morale=70, years_on_team=0, potential=None):
    p.eta, p.morale, p.anni_nella_squadra = age, morale, years_on_team
    if potential is not None:
        p.potenziale = potential
    return p


class LoyaltyTests(unittest.TestCase):
    def loyalty(self, years, morale):
        return contracts.loyalty(aged(make_player("L", ovr=80), 28, morale=morale, years_on_team=years), None)

    def test_loyalty_grows_with_years_and_morale(self):
        self.assertAlmostEqual(self.loyalty(0, 70), 0.0)
        self.assertAlmostEqual(self.loyalty(3, 70), 12.0)
        self.assertAlmostEqual(self.loyalty(9, 70), 20.0)
        self.assertAlmostEqual(self.loyalty(5, 100), 25.0)   # clamped at LOYALTY_MAX
        self.assertAlmostEqual(self.loyalty(0, 20), 0.0)     # clamped at LOYALTY_MIN

    def test_loyalty_defaults_without_attributes(self):
        self.assertAlmostEqual(contracts.loyalty(SimpleNamespace(morale=70), None), 0.0)


class WalkTests(unittest.TestCase):
    def star(self, ovr=90, age=29, morale=70):
        return aged(make_player("Star", ovr=ovr, role="SF"), age, morale=morale, years_on_team=4)

    def test_a_star_on_a_hopeless_team_walks(self):
        s = self.star()
        self.assertEqual(contracts.walk_reason(s, team_of(roster_with(s)), ctx_of("REBUILDER")), "hopeless team")

    def test_a_young_core_keeps_him(self):
        s = self.star()
        kids = [aged(make_player(f"K{i}", ovr=70, role="PG"), 21, potential=86) for i in range(2)]
        self.assertEqual(contracts.walk_reason(s, team_of(roster_with(s, *kids)), ctx_of("REBUILDER")), "")

    def test_not_a_star_or_too_young_does_not_walk(self):
        for s in (self.star(ovr=80), self.star(age=24)):
            with self.subTest(ovr=s.ovr, age=s.eta):
                self.assertEqual(contracts.walk_reason(s, team_of(roster_with(s)), ctx_of("REBUILDER")), "")

    def test_a_losing_middle_team_is_hopeless_after_enough_games(self):
        s = self.star()
        t = team_of(roster_with(s))
        self.assertEqual(contracts.walk_reason(s, t, ctx_of("MIDDLE", win_pct=0.30, games=40)), "hopeless team")
        self.assertEqual(contracts.walk_reason(s, t, ctx_of("MIDDLE", win_pct=0.30, games=10)), "")
        self.assertEqual(contracts.walk_reason(s, t, ctx_of("MIDDLE", win_pct=0.50, games=40)), "")

    def test_asked_out_wins_over_everything(self):
        s = self.star(ovr=86, age=31, morale=30)   # the wants_out case of tests/test_wishes.py test_star_wants_out
        self.assertEqual(contracts.walk_reason(s, team_of(roster_with(s)), ctx_of("REBUILDER")), "asked out")


class Fixed:
    """rng stub: random() returns this value."""
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


class RenewalTests(unittest.TestCase):
    def offer(self, ovr, age, plan, rng=0.0, pot=None):
        p = aged(make_player("R", ovr=ovr, role="SF"), age, potential=pot)
        return contracts.renewal_offer(p, ctx_of(plan), rng=Fixed(rng))

    def test_a_contender_pays_its_star_above_market(self):
        self.assertEqual(self.offer(90, 29, "CONTENDER").salary_mult, 1.10)
        self.assertEqual(self.offer(90, 29, "MIDDLE").salary_mult, 1.0)

    def test_a_rebuilder_lets_a_veteran_starter_walk(self):
        self.assertIsNone(self.offer(78, 31, "REBUILDER"))
        self.assertIsNone(self.offer(90, 30, "REBUILDER"))   # an old star too

    def test_a_rebuilder_keeps_its_young_star(self):
        self.assertEqual(self.offer(88, 25, "REBUILDER"), contracts.Renewal(1.0, 4))

    def test_a_rebuilder_prime_starter_is_a_chance(self):
        offer = self.offer(76, 27, "REBUILDER", rng=0.1)       # a prime starter (27), the chance says yes
        self.assertEqual(offer.years, 4)
        self.assertIsNone(self.offer(76, 27, "REBUILDER", rng=0.9))
        young_bench = self.offer(70, 23, "REBUILDER", pot=80)   # young with starter potential: kept
        self.assertIsNotNone(young_bench)

    def test_bench_renewal_is_a_chance(self):
        self.assertIsNotNone(self.offer(72, 29, "PLAYOFF", rng=0.3))
        self.assertIsNone(self.offer(72, 29, "PLAYOFF", rng=0.5))
        self.assertIsNone(self.offer(72, 30, "REBUILDER", rng=0.0))   # an old bench player on a rebuild: never

    def test_years_follow_age(self):
        self.assertEqual(self.offer(80, 27, "CONTENDER").years, 4)
        self.assertEqual(self.offer(80, 30, "CONTENDER").years, 3)
        self.assertEqual(self.offer(80, 33, "CONTENDER").years, 2)
        self.assertEqual(self.offer(80, 35, "CONTENDER").years, 1)


if __name__ == "__main__":
    unittest.main()
