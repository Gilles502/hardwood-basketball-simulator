"""Engine counters the box score did not keep: offensive rebounds, assisted makes, shot zones and clutch numbers.
They only count what the engine already decides; real games must add up with the totals that existed before."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from main import Tournament
from core import db_manager, paths
from core.game_engine import Partita
from core.league.builder import build_league_db
from core.league.schema import load_league

NEW_KEYS = ('oreb', 'dreb', 'ast_fgm', 'rim_fga', 'rim_fgm', 'mid_fga', 'mid_fgm',
            'clutch_pts', 'clutch_fga', 'clutch_fgm', 'clutch_min')
GAMES = []


def setUpModule():
    """Plays games on the built-in fictional league, built into a temp DB: never the active data/nba_sim.db."""
    global _TMP
    main.main_log.disabled = True
    _TMP = tempfile.mkdtemp(prefix="hardwood_engine_stats_")
    db = os.path.join(_TMP, "league.db")
    build_league_db(load_league(paths.game_path("data", "leagues", "fictional_2002", "league.json")), db)
    with mock.patch.object(db_manager, "DB_NAME", db):
        teams, _fa = main.caricamento_squadre()
    for i in range(10):
        home, away = teams[(2 * i) % len(teams)], teams[(2 * i + 1) % len(teams)]
        game = Partita(home, away)
        home.partita = away.partita = game
        game.gioca()
        GAMES.append((game, home, away))


def tearDownModule():
    main.main_log.disabled = False
    shutil.rmtree(_TMP, ignore_errors=True)


def lines(game, team):
    return [s['game_stats'] for s in game.final_box_scores[team.nome]]


class EngineExtraStatsTests(unittest.TestCase):
    def test_player_counters_add_up(self):
        for game, home, away in GAMES:
            for team in (home, away):
                for g in lines(game, team):
                    fga = g.tiri_tentati_2 + g.tiri_tentati_3
                    fgm = g.tiri_fatti_2 + g.tiri_fatti_3
                    self.assertLessEqual(g.oreb, g.rimbalzi)
                    self.assertEqual(g.rim_fga + g.mid_fga + g.tiri_tentati_3, fga)
                    self.assertEqual(g.rim_fgm + g.mid_fgm + g.tiri_fatti_3, fgm)
                    self.assertLessEqual(g.ast_fgm, fgm)
                    self.assertLessEqual(g.clutch_fgm, g.clutch_fga)
                    self.assertLessEqual(g.clutch_fga, fga)
                    self.assertLessEqual(g.clutch_pts, g.punti)
                    self.assertLessEqual(g.clutch_sec, g.secondi_giocati)

    def test_every_assist_is_one_assisted_make(self):
        for game, home, away in GAMES:
            for team in (home, away):
                ls = lines(game, team)
                self.assertEqual(sum(g.ast_fgm for g in ls), sum(g.assist for g in ls))

    def test_counters_are_used(self):
        all_lines = [g for game, h, a in GAMES for t in (h, a) for g in lines(game, t)]
        reb = sum(g.rimbalzi for g in all_lines)
        oreb = sum(g.oreb for g in all_lines)
        self.assertTrue(0.10 < oreb / reb < 0.45, oreb / reb)
        self.assertGreater(sum(g.rim_fga for g in all_lines), 0)
        self.assertGreater(sum(g.mid_fga for g in all_lines), 0)

    def test_box_score_lines_carry_the_new_keys(self):
        game, home, away = GAMES[0]
        t = object.__new__(Tournament)
        sheet = t._genera_box_score_partita(game, home, away, 'g1', '2002-10-29', 0)
        p = sheet['home_team']['players'][0]
        for key in NEW_KEYS:
            self.assertIn(key, p)
        self.assertEqual(p['oreb'] + p['dreb'], p['reb'])


if __name__ == '__main__':
    unittest.main()
