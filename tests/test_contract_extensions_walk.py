"""Extension window: stars on hopeless teams walk (user's team too), loyalty is earned, walkers want out for trades."""
import unittest
from types import SimpleNamespace
from unittest import mock

from core.front_office import contracts
from core.front_office.wishes import build_wishes
from offseason.contract_extensions import ContractExtensions
from tests.test_wishes import ctx_of, roster_with, team_of
from tests.trade_fixtures import make_player


def walker_team(name="Sixers"):
    star = make_player(f"{name}-Star", ovr=90, age=29, years=1, role="SF", team_years=4)
    star.morale, star.is_flight_risk, star.is_untouchable, star.walks_away = 70, False, True, ""
    team = team_of(roster_with(star), name=name)
    team.vittorie, team.sconfitte = 10, 30
    return team, star


def engine(teams, user=None):
    torneo = SimpleNamespace(squadra_giocatore=user, squadre=teams, season_number=1)
    return ContractExtensions(torneo, teams)


class WalkerTests(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(contracts, "context_for", lambda torneo, team: ctx_of("REBUILDER")),
                  mock.patch("offseason.contract_extensions.add_news")):
            p.start()
            self.addCleanup(p.stop)

    def test_a_walker_is_marked_and_not_extended(self):
        team, star = walker_team()
        ext = engine([team])
        with mock.patch.object(ContractExtensions, "_attempt_extension", return_value=False) as attempt:
            ext.process_extensions()
        self.assertEqual(star.walks_away, "hopeless team")
        self.assertFalse(star.is_untouchable)
        self.assertTrue(star.is_flight_risk)
        self.assertEqual(star.contract.anni_rimanenti, 1)
        self.assertNotIn(star, [c.args[1] for c in attempt.call_args_list])

    def test_the_user_team_walker_is_marked_too(self):
        team, star = walker_team()
        ext = engine([team], user=team)
        with mock.patch.object(ContractExtensions, "_attempt_extension", return_value=False) as attempt:
            ext.process_extensions()
        self.assertEqual(star.walks_away, "hopeless team")
        attempt.assert_not_called()

    def test_walker_gets_star_wants_out_wish(self):
        team, star = walker_team()
        star.walks_away = "hopeless team"
        star.morale = 95   # happy: only the walk makes him want out
        wishes = [w for w in build_wishes(team, ctx_of("REBUILDER")) if w.kind == "STAR_WANTS_OUT"]
        self.assertEqual([w.player for w in wishes], [star.nome])


class UserFacingTests(unittest.TestCase):
    def ext(self, team):
        e = engine([team])
        e.compute_player_market_request = lambda p, option_type="None": 20.0
        e.torneo._determina_stato_squadra = lambda t: "Rebuilding"
        return e

    def test_walker_rejects_the_user_extension(self):
        team, star = walker_team()
        star.walks_away = "hopeless team"
        e = self.ext(team)
        evaluation = e.evaluate_realtime_offer(star, team, 25.0, 4)
        self.assertEqual(evaluation["tier"], "Won't negotiate")
        self.assertFalse(evaluation["can_accept"])
        self.assertIn("hopeless team", evaluation["agent_reaction"])
        score, reason = e.calculate_extension_score(star, team, 25.0)
        self.assertEqual(score, 0.0)
        self.assertIn("will not negotiate", reason)

    def test_loyalty_replaces_the_flat_bonus(self):
        team, star = walker_team()
        e = self.ext(team)
        star.anni_nella_squadra, star.morale = 0, 70     # a newcomer: no loyalty
        newcomer, _ = e.calculate_extension_score(star, team, 20.0)
        star.anni_nella_squadra = 5                       # 5 seasons: LOYALTY_PER_YEAR x 5
        veteran, _ = e.calculate_extension_score(star, team, 20.0)
        self.assertAlmostEqual(veteran - newcomer, contracts.loyalty(star) - 0.0)

    def test_willingness_tier_says_wont_negotiate(self):
        _team, star = walker_team()
        star.walks_away = "asked out"
        self.assertEqual(star.get_willingness_tier(), "Won't negotiate")

    def test_reset_for_season_clears_the_walk(self):
        _team, star = walker_team()
        star.walks_away = "hopeless team"
        star.season_stats = SimpleNamespace(reset=lambda: None)
        star.playoff_stats = SimpleNamespace(reset=lambda: None)
        star.recupera_stamina_offseason = lambda: None
        star.reset_for_season()
        self.assertEqual(star.walks_away, "")


class RenewalByPlanTests(unittest.TestCase):
    def attempt(self, plan, ovr, age, payroll=30.0):
        p = make_player("P", ovr=ovr, age=age, years=1, role="SF", team_years=3)
        p.morale, p.is_flight_risk, p.walks_away = 70, False, ""
        team = team_of(roster_with(p), name="T", payroll=payroll)
        team.personalita_proprietario, team.vittorie = "Normale", 20
        e = engine([team])
        e.torneo.second_apron, e.torneo.luxury_tax_threshold, e.torneo.first_apron = 70.0, 55.0, 60.0
        e.compute_player_market_request = lambda pl, option_type="None": 10.0
        with mock.patch.object(contracts, "context_for", lambda torneo, t: ctx_of(plan)),                 mock.patch.object(ContractExtensions, "calculate_extension_score", return_value=(100.0, "ok")),                 mock.patch("offseason.contract_extensions.add_news"),                 mock.patch("offseason.contract_extensions.random.random", return_value=0.0):
            done = e._attempt_extension(team, p)
        return done, p

    def test_attempt_extension_uses_the_plan(self):
        done, p = self.attempt("REBUILDER", 78, 31)   # a veteran starter on a rebuild: no offer, whatever the dice
        self.assertFalse(done)
        self.assertEqual(p.contract.anni_rimanenti, 1)

    def test_a_contender_extends_its_star_above_market(self):
        done, p = self.attempt("CONTENDER", 90, 29)
        self.assertTrue(done)
        # 10.0 x RENEW_STAR_MULT["CONTENDER"], from next season: this year stays at the old salary
        self.assertAlmostEqual(p.contract.salari_per_anno[1], 11.0)
        self.assertAlmostEqual(p.contract.salario_annuale, p.contract.salari_per_anno[0])

    def test_the_owner_budget_still_stops_a_non_star(self):
        done, _p = self.attempt("CONTENDER", 80, 27, payroll=69.0)   # 69 + 10 over the owner's limit
        self.assertFalse(done)


class SaveTests(unittest.TestCase):
    def test_walks_away_round_trips_and_defaults(self):
        from core.save_manager import serialize_player
        _team, star = walker_team()
        star.walks_away = "asked out"
        data = serialize_player(star)
        self.assertEqual(data["walks_away"], "asked out")
        from core import save_manager
        src = open(save_manager.__file__, encoding="utf-8").read()
        self.assertIn('g.walks_away = data.get("walks_away", "")', src)


if __name__ == "__main__":
    unittest.main()
