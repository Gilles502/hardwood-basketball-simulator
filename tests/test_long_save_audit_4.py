"""Fixes from the no-mod 25-season audit of 2026-11-21 (docs/audits/LONG_SAVE_AUDIT_2026-11-21_nomod.md)."""
import random
import statistics
import unittest
from types import SimpleNamespace

from core.config import CONFIG


def _prospects(year, count=600, seed=11):
    from offseason.draft import Draft
    random.seed(seed)
    d = object.__new__(Draft)
    d.torneo = SimpleNamespace(anno_corrente=year, squadre=[], free_agents_pool=[], draft_class=[])
    return [p for _ in range(count // 60) for p in d._genera_giocatori_mancanti(60, [])]


def _mean(players, role, attr):
    values = [getattr(p.abilita, attr) if hasattr(p.abilita, attr) else getattr(p.tendenze, attr)
              for p in players if p.ruolo == role]
    return statistics.mean(values)


class GeneratedProspectRoles(unittest.TestCase):
    def test_each_role_keeps_its_profile(self):
        players = _prospects(2002)
        self.assertLess(_mean(players, 'C', 'three_point_shot_rating') + 15, _mean(players, 'PG', 'three_point_shot_rating'))
        self.assertLess(_mean(players, 'C', 'three_point_shot_tendency') + 20, _mean(players, 'SF', 'three_point_shot_tendency'))
        self.assertLess(_mean(players, 'PG', 'block_rating') + 25, _mean(players, 'C', 'block_rating'))
        self.assertLess(_mean(players, 'PG', 'post_up_tendency') + 15, _mean(players, 'PF', 'post_up_tendency'))
        self.assertLess(_mean(players, 'C', 'steal_rating') + 15, _mean(players, 'SG', 'steal_rating'))
        self.assertGreater(_mean(players, 'C', 'dunk_tendency'), _mean(players, 'PG', 'dunk_tendency') + 20)

    def test_later_classes_shoot_more_threes(self):
        old, new = _prospects(2002), _prospects(2026)
        for role in ('PF', 'C'):
            self.assertGreater(_mean(new, role, 'three_point_shot_tendency'), _mean(old, role, 'three_point_shot_tendency') + 8)

    def test_wing_role_players_are_not_clamped_out_of_hero_ball(self):
        wings = [p for p in _prospects(2002) if p.ruolo == 'SF']
        self.assertGreater(len({p.tendenze.hero_ball_tendency for p in wings}), 10)


class UsageFollowsTalent(unittest.TestCase):
    def test_a_player_who_grows_takes_more_shots(self):
        player = _prospects(2002, count=60)[0]
        player.eta = 23
        # on his role's usage slope, as most generated prospects are
        player.tendenze.touch_tendency = round(player._usage_target('touch_tendency'))
        player.tendenze.hero_ball_tendency = round(player._usage_target('hero_ball_tendency'))
        touch, hero = player.tendenze.touch_tendency, player.tendenze.hero_ball_tendency
        player.valutazione += 6   # the progression sets the new OVR first
        player._distribuisci_cambio_abilita(6)
        per = CONFIG.PROGRESSION.USAGE_TENDENCY_PER_OVR
        self.assertGreaterEqual(player.tendenze.touch_tendency, min(99, touch + round(6 * per['touch_tendency'])))
        self.assertGreaterEqual(player.tendenze.hero_ball_tendency, min(99, hero + round(6 * per['hero_ball_tendency'])))

    def _real_player(self, role, ovr, touch, hero):
        player = _prospects(2002, count=60)[0]
        player.eta, player.ruolo, player.valutazione = 22, role, ovr
        player.tendenze.touch_tendency, player.tendenze.hero_ball_tendency = touch, hero
        return player

    def test_a_real_player_born_with_adult_usage_keeps_it(self):
        # League_2002_5: Embiid drafted at 78 OVR with touch 88 grew to 95 and touch 99; Love 74 -> 99
        embiid = self._real_player('C', 78, 88, 80)
        for _ in range(17):
            embiid.valutazione += 1
            embiid._distribuisci_cambio_abilita(1)
        self.assertEqual(embiid.tendenze.touch_tendency, 88)
        self.assertEqual(embiid.tendenze.hero_ball_tendency, 80)

    def test_a_low_usage_star_still_grows_to_his_slope(self):
        love = self._real_player('PF', 75, 60, 30)
        for _ in range(12):
            love.valutazione += 1
            love._distribuisci_cambio_abilita(1)
        target = love._usage_target('touch_tendency') + CONFIG.PROGRESSION.USAGE_TARGET_MARGIN
        self.assertGreater(love.tendenze.touch_tendency, 60)
        self.assertLessEqual(love.tendenze.touch_tendency, round(target))

    def test_losing_ovr_still_costs_usage(self):
        embiid = self._real_player('C', 95, 88, 80)
        embiid.valutazione -= 3
        embiid._distribuisci_cambio_abilita(-3)
        self.assertLess(embiid.tendenze.touch_tendency, 88)


class EraNeutralPerformance(unittest.TestCase):
    def _league(self, factor, players=80):
        from core.models import CumulativeStats
        roster = []
        for _ in range(players):
            stats = CumulativeStats(partite_giocate=70, minuti_giocati=2000.0)
            ref = CONFIG.PROGRESSION.PVS_REFERENCE
            stats.punti, stats.assist, stats.rimbalzi = (round(ref[k] * factor * 2000 / 36) for k in ('pts', 'ast', 'reb'))
            p = SimpleNamespace(season_stats=stats)
            p.production_indexes = (lambda f: (lambda: (ref['off'] * f, ref['def'] * f)))(factor)
            roster.append(p)
        return SimpleNamespace(season_number=3, squadre=[SimpleNamespace(roster=roster)], free_agents_pool=[])

    def test_a_faster_league_is_scaled_back(self):
        from core.models import league_season_scales
        scales = league_season_scales(self._league(1.5))
        for key in ('off', 'def', 'pts', 'ast', 'reb'):
            self.assertAlmostEqual(scales[key], 1 / 1.5, places=2)

    def test_too_few_players_means_no_scaling(self):
        from core.models import league_season_scales
        self.assertEqual(set(league_season_scales(self._league(1.5, players=10)).values()), {1.0})
        self.assertEqual(set(league_season_scales(None).values()), {1.0})

    def test_scaled_pvs_is_lower_for_the_same_numbers(self):
        player = _prospects(2002, count=60)[0]
        s = player.season_stats
        s.partite_giocate, s.minuti_giocati, s.punti, s.assist, s.rimbalzi, s.turnover = 70, 2200.0, 1500, 300, 400, 150
        player.calcola_pvs()
        plain = player.performance_scores.total
        player.calcola_pvs({'off': 0.7, 'def': 0.7})
        self.assertLess(player.performance_scores.total, plain)


class RivalriesFade(unittest.TestCase):
    def test_the_season_rollover_decays_intensity(self):
        import main
        from core.rivalry_tracker import RivalryTracker
        tracker = RivalryTracker()
        rivalry = tracker.get_or_create_rivalry("A", "B")
        rivalry.intensity = 80.0
        torneo = SimpleNamespace(rivalry_tracker=tracker, season_number=7)
        main.Tournament._fade_rivalries(torneo)
        self.assertLess(rivalry.intensity, 80.0 * tracker.INTENSITY_DECAY_RATE + 0.01)
        self.assertEqual(tracker.current_season, 8)


class LoadManagementByEra(unittest.TestCase):
    def test_early_stars_rest_less(self):
        import main
        cfg = CONFIG.SIM
        start, full = cfg.LOAD_MANAGEMENT_RAMP_YEARS
        factor = lambda year: main.Tournament._load_management_factor(SimpleNamespace(anno_corrente=year))
        self.assertAlmostEqual(factor(2002), cfg.LOAD_MANAGEMENT_EARLY_FACTOR)
        self.assertAlmostEqual(factor(full + 5), 1.0)
        self.assertLess(factor(start + 1), factor(full - 1))


class AgingStars(unittest.TestCase):
    def _veteran(self, age_after, ovr, pvs):
        player = _prospects(2002, count=60)[0]
        player.eta, player.valutazione, player.potenziale = age_after - 1, ovr, ovr
        player.contract = None
        s = player.season_stats
        s.partite_giocate, s.minuti_giocati, s.punti = 72, 2500.0, 1600
        player.performance_scores.total = pvs
        return player

    def test_a_star_with_a_good_season_holds_at_34(self):
        player = self._veteran(34, 88, 87.0)
        player.gestisci_progressione_offseason()
        self.assertEqual(player.valutazione, 88)

    def test_a_star_still_loses_a_little_at_37(self):
        player = self._veteran(37, 88, 87.0)
        player.gestisci_progressione_offseason()
        self.assertEqual(player.valutazione, 86)

    def test_a_poor_season_still_declines(self):
        player = self._veteran(34, 88, 78.0)
        player.gestisci_progressione_offseason()
        self.assertLessEqual(player.valutazione, 85)


if __name__ == "__main__":
    unittest.main()
