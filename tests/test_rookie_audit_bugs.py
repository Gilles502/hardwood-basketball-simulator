"""Bugs from the rookie generation and development audit of 2026-11-22
(docs/audits/ROOKIE_GENERATION_AND_DEVELOPMENT_AUDIT_2026-11-22.md): C1 season TS%, C3 team state, half-up growth."""
import random
import unittest
from types import SimpleNamespace

from core.models import CumulativeStats, Squadra


def _prospects(count=60, seed=5):
    from offseason.draft import Draft
    random.seed(seed)
    d = object.__new__(Draft)
    d.torneo = SimpleNamespace(anno_corrente=2002, squadre=[], free_agents_pool=[], draft_class=[])
    return d._genera_giocatori_mancanti(count, [])


class SeasonTrueShooting(unittest.TestCase):
    def test_pvs_uses_the_season_not_the_last_game(self):
        player = _prospects(1)[0]
        player.season_stats = CumulativeStats(partite_giocate=70, minuti_giocati=2100.0, punti=1200,
                                              tiri_tentati_2=700, tiri_tentati_3=250, tiri_liberi_tentati=300)
        player.advanced_game_stats.true_shooting_percentage = 20.0   # one cold night
        off_cold, _ = player.production_indexes()
        player.advanced_game_stats.true_shooting_percentage = 90.0   # one hot night
        off_hot, _ = player.production_indexes()
        self.assertEqual(off_cold, off_hot)
        ts = 1200 / (2 * (950 + 0.44 * 300)) * 100
        pts_36 = 1200 / 2100 * 36
        self.assertAlmostEqual(off_cold, pts_36 * ts / 58.0, places=6)   # no assists or turnovers


class TeamStateDuringGames(unittest.TestCase):
    def test_per_team_rotation_sees_the_whole_league(self):
        from main import Tournament
        players = _prospects(150)
        teams = []
        for i in range(10):
            roster = players[i * 15:(i + 1) * 15]
            for p in roster:
                p.valutazione = 60 if i == 0 else 80   # team 0 is far below the league
                p.eta = 28
            teams.append(Squadra(nome=f"Team {i}", roster=roster))
        torneo = object.__new__(Tournament)
        torneo.squadre = teams
        torneo.squadra_giocatore = None
        torneo.campione = None
        torneo.playoff_state = None
        seen = []
        original = Tournament._determina_stato_squadra
        torneo._determina_stato_squadra = lambda s: seen.append((len(torneo.squadre), original(torneo, s))) or seen[-1][1]
        torneo.imposta_rotazioni_stagione_per_squadra(teams[0])
        self.assertEqual(seen, [(10, "Rebuilding")])
        self.assertIs(torneo.squadre, teams)
        self.assertGreater(sum(p.minuti_target for p in teams[0].roster), 0)
        self.assertEqual(sum(p.minuti_target for p in teams[1].roster), 0)   # other teams untouched


class HalfUpGrowth(unittest.TestCase):
    def test_a_half_point_of_growth_counts(self):
        player = _prospects(1)[0]
        player.eta, player.valutazione, player.potenziale = 22, 79, 81   # 23 after the birthday, gap 2
        player.contract = None
        player.season_stats = CumulativeStats(partite_giocate=70, minuti_giocati=70 * 30.0)
        player.performance_scores.total = 79.0                            # played at his level
        player._evolvi_potenziale = lambda *a, **k: None
        player.gestisci_progressione_offseason()
        self.assertEqual(player.valutazione, 80)   # 2 * 0.25 * 1.0 = 0.5 -> 1, Python's round gave 0


if __name__ == "__main__":
    unittest.main()
