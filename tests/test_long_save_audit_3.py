"""Fixes from the 30-season audit of 2026-11-21 (docs/audits/LONG_SAVE_AUDIT_2026-11-21.md)."""
import collections
import random
import unittest
from types import SimpleNamespace
from unittest import mock

from core.config import CONFIG


class CalendarNeverDropsAGame(unittest.TestCase):
    def test_seed_that_dropped_a_pair_now_gives_82_games_to_everyone(self):
        from core.calendar_generator import NBACalendarGenerator
        from core.league.registry import FranchiseRegistry, get_active_registry, set_active_registry
        from core.league.schema import load_league
        previous = get_active_registry()
        reg = FranchiseRegistry.from_league(load_league("data/leagues/fictional_2002/league.json"))
        set_active_registry(reg)
        try:
            teams = [SimpleNamespace(nome=n, roster=[], conference=reg.conference_of(n)) for n in reg.names()]
            cal = NBACalendarGenerator(teams, starting_year=2021, seed=19).generate_calendar()   # was 1229 games
        finally:
            set_active_registry(previous)
        games = collections.Counter()
        for day in cal:
            for g in day.games:
                games[g.home_team] += 1
                games[g.away_team] += 1
        self.assertEqual(set(games.values()), {82})


class SeasonOneRookies(unittest.TestCase):
    def _torneo(self, players):
        return SimpleNamespace(starting_year=2002, squadre=[SimpleNamespace(roster=players)])

    def _player(self, nome, eta, years):
        p = SimpleNamespace(nome=nome, eta=eta, is_rookie=False)
        p._start_years_on_team = years
        return p

    def test_without_a_draft_file_young_first_year_players_are_rookies(self):
        import main
        players = [self._player("Rook", 22, 1), self._player("Soph", 20, 2), self._player("Vet", 25, 1)]
        with mock.patch.object(main, "draft_class_file", return_value=None):
            count, _ = main.tag_season1_rookies(self._torneo(players))
        self.assertEqual(count, 1)
        self.assertEqual([p.nome for p in players if p.is_rookie], ["Rook"])
        self.assertFalse(any(hasattr(p, "_start_years_on_team") for p in players))

    def test_the_starting_years_draft_file_wins(self):
        import json, os, tempfile, main
        players = [self._player("Yao", 22, 1), self._player("Other", 21, 1)]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "DRAFT_2002.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump([{"name": "Yao"}], f)
            with mock.patch.object(main, "draft_class_file", return_value=path) as found:
                count, source = main.tag_season1_rookies(self._torneo(players))
        self.assertEqual(found.call_args[0][1], 2002)
        self.assertEqual((count, source), (1, "DRAFT_2002.json"))


class CoachRetirement(unittest.TestCase):
    def test_age_bounds(self):
        from main import coach_retires_now
        cc = CONFIG.COACHING
        self.assertFalse(coach_retires_now(cc.RETIRE_MIN_AGE - 1, 0.0))
        self.assertTrue(coach_retires_now(cc.RETIRE_MAX_AGE, 0.99))
        self.assertTrue(coach_retires_now(cc.RETIRE_MIN_AGE, cc.RETIRE_BASE_CHANCE - 0.01))
        self.assertFalse(coach_retires_now(cc.RETIRE_MIN_AGE, cc.RETIRE_BASE_CHANCE + 0.01))


class HallOfFameTitles(unittest.TestCase):
    @staticmethod
    def _season(ppg, rpg, apg, champ, premi=()):
        return {"premi": list(premi), "stats_rs": {"ppg": ppg, "rpg": rpg, "apg": apg},
                "partite_giocate_rs": 75, "is_champion": champ}

    def test_bench_rings_do_not_elect(self):
        from main import calcola_hof_score
        career = [self._season(5.6, 5.0, 0.8, champ=i < 5) for i in range(12)]   # a 5-ring bench big
        score, _ = calcola_hof_score(career)
        self.assertLess(score, CONFIG.HISTORY.HOF_MIN_SCORE)

    def test_a_leaders_titles_still_count(self):
        from main import calcola_hof_score
        career = [self._season(26.0, 9.0, 5.0, champ=i < 3, premi=["All-NBA 1st", "All-Star"]) for i in range(12)]
        score, _ = calcola_hof_score(career)
        self.assertGreaterEqual(score, 600)


class GeneratedProspectAges(unittest.TestCase):
    def test_older_prospects_have_smaller_potential_gaps(self):
        from offseason.draft import Draft
        random.seed(5)
        d = object.__new__(Draft)
        d.torneo = None
        players = [p for _ in range(10) for p in d._genera_giocatori_mancanti(60, [])]
        gaps = collections.defaultdict(list)
        for p in players:
            if p.pedigree != "Generational Talent":
                gaps[p.eta].append(p.potenziale - p.valutazione)
        self.assertTrue(set(gaps) <= set(CONFIG.OFFSEASON.ROOKIE_AGE_WEIGHTS))
        mean = {a: sum(v) / len(v) for a, v in gaps.items()}
        self.assertGreater(mean[19], mean[23])
        self.assertGreater(len(gaps[19]), len(gaps[23]))


class TaxDumpPrice(unittest.TestCase):
    def test_no_first_for_an_ordinary_contract_without_seconds(self):
        from trades.engines import tax_dump
        era = SimpleNamespace(is_high_contract=lambda salary, years: False)
        finder = SimpleNamespace(era=lambda: era, _collect_team_picks=lambda team: [(2, "R1-A")],
                                 _is_top5_pick=lambda key: False)
        player = SimpleNamespace(contract=SimpleNamespace(salario_annuale=5.6, anni_rimanenti=2))
        self.assertEqual(tax_dump._prices(finder, None, player), [])
        import dataclasses
        looser = dataclasses.replace(CONFIG, TRADES=dataclasses.replace(CONFIG.TRADES, TAX_DUMP_R1_FALLBACK=True))
        with mock.patch.object(tax_dump, "CONFIG", looser):
            self.assertEqual(tax_dump._prices(finder, None, player), [["2:R1-A"]])


if __name__ == "__main__":
    unittest.main()
