"""Engine Block B (docs/superpowers/specs/2026-11-26-engine-block-b-design.md): score-or-pass decisions are
continuous weights of the player, not hard thresholds."""
import unittest
from types import SimpleNamespace

from core.game_engine import Partita

TEND = dict(playmaking_tendency=50, dish_to_open_man_tendency=50, touch_tendency=50, hero_ball_tendency=50,
            pass_out_of_shot_tendency=50)
SKILL = dict(passing_vision=50, close_shot_rating=50, dunk_rating=50, three_point_shot_rating=50,
             mid_range_shot_rating=50, ball_handling=50, shot_iq=50)


def player(role="SG", **kw):
    tend = {k: kw.pop(k) for k in list(kw) if k in TEND}
    skill = {k: kw.pop(k) for k in list(kw) if k in SKILL}
    assert not kw, kw
    return SimpleNamespace(ruolo=role, temp_tendenze=SimpleNamespace(**{**TEND, **tend}),
                           temp_abilita=SimpleNamespace(**{**SKILL, **skill}))


def kidd():
    return player("PG", playmaking_tendency=99, dish_to_open_man_tendency=96, touch_tendency=72, hero_ball_tendency=40,
                  pass_out_of_shot_tendency=90, passing_vision=98, close_shot_rating=74, three_point_shot_rating=70,
                  mid_range_shot_rating=72, ball_handling=92, shot_iq=90)


def nash():
    return player("PG", playmaking_tendency=96, dish_to_open_man_tendency=92, touch_tendency=77, hero_ball_tendency=54,
                  pass_out_of_shot_tendency=85, passing_vision=98, close_shot_rating=78, three_point_shot_rating=88,
                  mid_range_shot_rating=88, ball_handling=95, shot_iq=95)


def scorer():
    return player("SG", playmaking_tendency=45, dish_to_open_man_tendency=40, touch_tendency=90, hero_ball_tendency=85,
                  pass_out_of_shot_tendency=35, passing_vision=65, close_shot_rating=88, dunk_rating=85,
                  three_point_shot_rating=82, mid_range_shot_rating=88, ball_handling=88, shot_iq=85)


def extremes():
    return [player("C", **{k: 99 for k in TEND}, **{k: 99 for k in SKILL}),
            player("PG", **{k: 25 for k in TEND}, **{k: 25 for k in SKILL})]


class DriveDish(unittest.TestCase):
    def test_drive_dish_order(self):
        k, n, s = (Partita._drive_dish_chance(p) for p in (kidd(), nash(), scorer()))
        self.assertGreater(k, n)
        self.assertGreater(n, s)
        self.assertLess(s, 10)
        self.assertGreater(n, 25)

    def test_drive_dish_no_touch_cutoff(self):
        a = Partita._drive_dish_chance(player(playmaking_tendency=88, dish_to_open_man_tendency=85, touch_tendency=70))
        b = Partita._drive_dish_chance(player(playmaking_tendency=88, dish_to_open_man_tendency=85, touch_tendency=71))
        self.assertLess(abs(a - b), 3)

    def test_average_player_rarely_dishes(self):
        self.assertLess(Partita._drive_dish_chance(player()), 15)   # today: 0 for everyone under 82 playmaking

    def test_bounds_extremes(self):
        for p in extremes():
            self.assertTrue(0 <= Partita._drive_dish_chance(p) <= 95)
            self.assertTrue(15 <= Partita._kickout_chance(p) <= 90)


class KickOut(unittest.TestCase):
    def test_kickout_reads_hero_ball(self):
        low = Partita._kickout_chance(player(hero_ball_tendency=40))
        high = Partita._kickout_chance(player(hero_ball_tendency=85))
        self.assertGreaterEqual(low - high, 10)

    def test_kickout_touch_matters_little(self):
        a = Partita._kickout_chance(player(touch_tendency=60, hero_ball_tendency=50))
        b = Partita._kickout_chance(player(touch_tendency=90, hero_ball_tendency=50))
        self.assertLess(abs(a - b), 5)

    def test_average_player_unchanged(self):
        # today's formula for an all-50 player: 0.35*50 + 0.35*50 + 0.30*50 = 50, no malus
        self.assertAlmostEqual(Partita._kickout_chance(player()), 50.0, delta=5)

    def test_missing_tendencies_default(self):
        p = player()
        del p.temp_tendenze.hero_ball_tendency
        Partita._kickout_chance(p)
        Partita._drive_dish_chance(p)



class ExtraPass(unittest.TestCase):
    def test_extra_pass_graded(self):
        a = Partita._extra_pass_chance(player(three_point_shot_rating=77), open_look=True)
        b = Partita._extra_pass_chance(player(three_point_shot_rating=79), open_look=True)
        self.assertLess(abs(a - b), 5)

    def test_extra_pass_vision_softens(self):
        seer = Partita._extra_pass_chance(player(three_point_shot_rating=90, passing_vision=98), open_look=True)
        plain = Partita._extra_pass_chance(player(three_point_shot_rating=90, passing_vision=60), open_look=True)
        self.assertGreaterEqual(seer - plain, 10)

    def test_average_player_unchanged(self):
        # today: 40 + 50*0.15 + 15 (not a shooter) = 62.5, open look or not
        self.assertAlmostEqual(Partita._extra_pass_chance(player(), open_look=False), 62.5, delta=0.01)
        self.assertAlmostEqual(Partita._extra_pass_chance(player(), open_look=True), 62.5, delta=0.01)

    def test_bounds_extremes(self):
        for p in extremes():
            for open_look in (True, False):
                self.assertTrue(0 <= Partita._extra_pass_chance(p, open_look=open_look) <= 100)


class DropPickAndRoll(unittest.TestCase):
    def luka(self):
        return player("PG", three_point_shot_rating=85, mid_range_shot_rating=88, hero_ball_tendency=85,
                      playmaking_tendency=90, passing_vision=98)

    def test_drop_scorer_passer_keeps_more(self):
        self.assertGreaterEqual(Partita._drop_pull_up_share(self.luka()), 0.40)   # today 0.37

    def test_drop_pure_passer_rolls(self):
        self.assertLessEqual(Partita._drop_pull_up_share(kidd()), 0.30)

    def test_drop_shooter_keeps(self):
        self.assertGreaterEqual(Partita._drop_pull_up_share(player(three_point_shot_rating=92, playmaking_tendency=60)), 0.60)

    def test_bounds_extremes(self):
        top, bottom = extremes()
        self.assertTrue(0.05 <= Partita._drop_pull_up_share(top) <= 0.85)
        self.assertIsNone(Partita._drop_pull_up_share(bottom))   # neither shooter nor passer: the old weak read


class Initiation(unittest.TestCase):
    def creator(self, role):
        return player(role, ball_handling=92, passing_vision=92, playmaking_tendency=85, shot_iq=85)

    def test_creator_wing_close_to_pg(self):
        pg = Partita._initiation_factor(self.creator("PG"))
        sg = Partita._initiation_factor(self.creator("SG"))
        self.assertGreater(sg, pg * 0.85)

    def test_pg_label_still_counts(self):
        self.assertGreater(Partita._initiation_factor(self.creator("PG")), Partita._initiation_factor(self.creator("SG")))

    def test_non_creator_low(self):
        big = Partita._initiation_factor(player("C", ball_handling=50, passing_vision=55))
        self.assertLess(big, 0.6 * Partita._initiation_factor(kidd()))

    def test_factor_at_least_one(self):
        for p in extremes() + [player()]:
            self.assertGreaterEqual(Partita._initiation_factor(p), 1.0)


class VolumeTax(unittest.TestCase):
    def test_volume_tax_same_until_high_volume(self):
        from core.config import CONFIG
        for fga in range(0, CONFIG.PLAYMAKING.VOLUME_TAX_HIGH_FROM + 1):   # today's line: -0.5 per FGA over 14
            self.assertAlmostEqual(Partita._volume_tax(fga, interior=False), min(6.0, max(0, fga - 14) * 0.5))

    def test_volume_tax_steeper_after_20(self):
        self.assertGreater(Partita._volume_tax(26, interior=False), 6.0)
        self.assertGreater(Partita._volume_tax(30, interior=False), Partita._volume_tax(26, interior=False))

    def test_interior_smaller(self):
        self.assertLess(Partita._volume_tax(26, interior=True), Partita._volume_tax(26, interior=False))
        self.assertGreater(Partita._volume_tax(26, interior=True), 0)



class SoloCarryFocus(unittest.TestCase):
    def test_no_gap_unchanged(self):
        from core.models import Squadra
        self.assertEqual(Squadra.focus_rank_weights(0.0), [25.0, 23.0, 20.0, 17.0, 15.0])

    def test_solo_star_gets_more(self):
        from core.models import Squadra
        w = Squadra.focus_rank_weights(40.0)
        self.assertGreater(w[0], 30.0)
        self.assertAlmostEqual(sum(w), 100.0)
        self.assertTrue(all(x > 0 for x in w))

    def test_solo_star_bonus_back_to_8(self):
        # 14 gave seven players 30+ PPG in a modern league (League_2002_5, season 26)
        from core.config import CONFIG
        from core.models import Squadra
        self.assertLessEqual(CONFIG.PLAYMAKING.SOLO_CARRY_P1_BONUS, 8.0)
        self.assertLessEqual(Squadra.focus_rank_weights(40.0)[0], 33.0)


class LoneStarAtTheRim(unittest.TestCase):
    """Volume at the rim costs percentage too (League_2002_5: Embiid 38.8 PPG on 24 FGA at 66% TS)."""

    def test_rim_pays_most_of_the_tax(self):
        self.assertGreaterEqual(Partita._volume_tax(24, interior=True), 0.7 * Partita._volume_tax(24, interior=False))

    def test_lone_star_big_draws_the_crowd(self):
        # a 95 with 79-rated teammates: nothing before, any role now
        self.assertEqual(Partita._crowded_paint_malus(10, 95, 79), 0.0)
        self.assertGreater(Partita._crowded_paint_malus(20, 95, 79), 2.0)

    def test_star_with_a_real_second_option_does_not(self):
        self.assertEqual(Partita._crowded_paint_malus(20, 92, 84), 0.0)

    def test_weak_teammates_still_count(self):
        self.assertGreater(Partita._crowded_paint_malus(20, 80, 70), 2.0)
        self.assertLessEqual(Partita._crowded_paint_malus(30, 99, 60), 3.0)


def post_big(mid, mid_t, post, close):
    p = player("PF", mid_range_shot_rating=mid, close_shot_rating=close)
    p.temp_abilita.post_control_rating = post
    p.temp_tendenze.mid_range_shot_tendency = mid_t
    return p


class PostFadeaway(unittest.TestCase):
    """A post-up ended at the rim every time: Dirk (mid 93) took 16 rim shots a game and 3.6 from mid-range."""

    def test_dirk_fades_often(self):
        self.assertGreater(Partita._post_fade_chance(post_big(93, 85, 86, 84)), 40.0)

    def test_garnett_fades_sometimes(self):
        c = Partita._post_fade_chance(post_big(86, 80, 89, 88))
        self.assertGreater(c, 20.0)
        self.assertLess(c, Partita._post_fade_chance(post_big(93, 85, 86, 84)))

    def test_shaq_never_fades(self):
        self.assertEqual(Partita._post_fade_chance(post_big(55, 30, 95, 95)), 0.0)

    def test_capped(self):
        from core.config import CONFIG
        self.assertLessEqual(Partita._post_fade_chance(post_big(99, 99, 60, 60)), CONFIG.PLAYMAKING.POST_FADE_MAX)


if __name__ == "__main__":
    unittest.main()
