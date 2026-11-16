import json
import os
import random
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core import all_star_weekend as asw


def make_player(name='P', gp=20, pts=400, att3=0, made3=0, team='BOS', age=25, ovr=75, rookie=False):
    stats = SimpleNamespace(partite_giocate=gp, punti=pts, rimbalzi=gp * 5, assist=gp * 3,
                            tiri_fatti_3=made3, tiri_tentati_3=att3)
    ab = SimpleNamespace(three_point_shot_rating=70, dunk_rating=60, vertical=70, speed=60, acceleration=50)
    sq = SimpleNamespace(nome=team) if team else None
    return SimpleNamespace(nome=name, ruolo='SF', eta=age, valutazione=ovr, is_rookie=rookie,
                           squadra=sq, season_stats=stats, abilita=ab)


def line(name, ppg=15.0, ovr=75, age=25, rpg=5.0, apg=3.0, tpm=1.0):
    return {'name': name, 'team': 'BOS', 'pos': 'SF', 'age': age, 'ovr': ovr, 'gp': 50, 'ppg': ppg,
            'rpg': rpg, 'apg': apg, 'tpm': tpm, 'tp_pct': 35.0, 'r3': 70, 'dunk': 60, 'athl': 60}


def side(prefix, n=12, ppg=15.0, ovr=75):
    return [line(f'{prefix}{i}', ppg=ppg + (n - i) * 0.5, ovr=ovr) for i in range(n)]


class SeqRng:
    """Stub rng: randint / uniform pop the given values; sample and choice take the first names."""
    def __init__(self, randint=(), uniform=()):
        self._ri, self._un = iter(randint), iter(uniform)
    def randint(self, a, b):
        return next(self._ri)
    def uniform(self, a, b):
        return next(self._un)
    def sample(self, seq, k):
        return list(seq[:k])
    def choice(self, seq):
        return seq[0]


class AllStarWeekendTests(unittest.TestCase):
    def test_player_line_per_game_and_no_attempts(self):
        l = asw.player_line(make_player(gp=20, pts=400, att3=0, team=None))
        self.assertEqual(l['ppg'], 20.0)
        self.assertIsNone(l['tp_pct'])
        self.assertEqual(l['team'], 'FA')
        self.assertEqual(l['athl'], 60.0)
        l2 = asw.player_line(make_player(gp=20, att3=40, made3=14))
        self.assertEqual(l2['tp_pct'], 35.0)
        self.assertEqual(l2['tpm'], 0.7)

    def test_exhibition_totals_in_range_and_no_tie(self):
        lo, hi = CONFIG.ALL_STAR.ALL_STAR_TOTAL_RANGE
        for seed in range(200):
            g = asw.exhibition_game([('East', side('E')), ('West', side('W'))],
                                    CONFIG.ALL_STAR.ALL_STAR_TOTAL_RANGE, random.Random(seed))
            a, b = g['sides']
            for s in (a, b):
                self.assertGreaterEqual(s['score'], lo * CONFIG.ALL_STAR.SHARE_NOISE[0])
                self.assertLessEqual(s['score'], hi * CONFIG.ALL_STAR.SHARE_NOISE[1])
                self.assertEqual(s['score'], sum(x['pts'] for x in s['lines']))
            self.assertNotEqual(a['score'], b['score'])

    def test_exhibition_better_scorer_scores_more_on_average(self):
        star, scrub = line('Star', ppg=30.0), line('Scrub', ppg=8.0)
        rest = [line(f'R{i}', ppg=12.0) for i in range(10)]
        tot_star = tot_scrub = 0
        for seed in range(300):
            g = asw.exhibition_game([('East', [star, scrub] + rest), ('West', side('W'))],
                                    CONFIG.ALL_STAR.ALL_STAR_TOTAL_RANGE, random.Random(seed))
            by = {x['name']: x['pts'] for x in g['sides'][0]['lines']}
            tot_star += by['Star']
            tot_scrub += by['Scrub']
        self.assertGreater(tot_star, tot_scrub)

    def test_exhibition_mvp_is_on_winning_side(self):
        for seed in range(50):
            g = asw.exhibition_game([('East', side('E')), ('West', side('W'))],
                                    CONFIG.ALL_STAR.ALL_STAR_TOTAL_RANGE, random.Random(seed))
            self.assertEqual(g['mvp']['label'], g['winner'])
            win = next(s for s in g['sides'] if s['label'] == g['winner'])
            self.assertEqual(g['mvp']['pts'], win['lines'][0]['pts'])
            self.assertEqual(g['mvp']['name'], win['lines'][0]['name'])
            pts = [x['pts'] for x in win['lines']]
            self.assertEqual(pts, sorted(pts, reverse=True))

    def test_exhibition_tie_goes_to_higher_ovr_side(self):
        class Stub:
            def __init__(self):
                self.totals = iter([100, 110])
            def randint(self, a, b):
                return next(self.totals)
            def uniform(self, a, b):
                return 1.0
        # gap 10 -> nudge +-5: both raw totals are 105, a forced tie.
        hi = [line('Hi', ppg=20.0, ovr=80, tpm=0.0)]
        lo = [line('Lo', ppg=20.0, ovr=70, tpm=0.0)]
        g = asw.exhibition_game([('Strong', hi), ('Weak', lo)], (100, 110), Stub())
        strong, weak = g['sides']
        self.assertEqual(weak['score'], 105)
        self.assertEqual(strong['score'], 105 + CONFIG.ALL_STAR.TIE_BREAK_POINTS)
        self.assertEqual(strong['score'], sum(x['pts'] for x in strong['lines']))
        self.assertEqual(g['winner'], 'Strong')
        self.assertEqual(g['mvp']['name'], 'Hi')
        self.assertEqual(g['mvp']['pts'], strong['lines'][0]['pts'])

    def test_exhibition_higher_ovr_side_wins_more_often(self):
        wins = 0
        for seed in range(300):
            g = asw.exhibition_game([('Strong', side('S', ovr=85)), ('Weak', side('W', ovr=65))],
                                    CONFIG.ALL_STAR.ALL_STAR_TOTAL_RANGE, random.Random(seed))
            wins += g['winner'] == 'Strong'
        self.assertGreater(wins, 200)

    def test_exhibition_box_looks_like_an_all_star_game(self):
        # 12 All-Stars a side: 28 down to 15 PPG, OVR 85-95, 7 RPG / 4 APG on average.
        def stars(prefix):
            return [line(f'{prefix}{i}', ppg=28.0 - i * 1.2, ovr=95 - i, rpg=7.0, apg=4.0) for i in range(12)]
        mvp, low, reb, ast = [], [], [], []
        for seed in range(300):
            g = asw.exhibition_game([('East', stars('E')), ('West', stars('W'))],
                                    CONFIG.ALL_STAR.ALL_STAR_TOTAL_RANGE, random.Random(seed))
            mvp.append(g['mvp']['pts'])
            for s in g['sides']:
                low.append(s['lines'][-1]['pts'])
                reb.append(sum(x['reb'] for x in s['lines']))
                ast.append(sum(x['ast'] for x in s['lines']))
        mean = lambda xs: sum(xs) / len(xs)
        # An MVP scores like one (~25-30), the bench barely scores, and the box is a ~20-minute night.
        self.assertGreaterEqual(mean(mvp), 24)
        self.assertGreaterEqual(max(mvp), 32)
        self.assertLessEqual(mean(low), 8)
        self.assertLessEqual(mean(reb), 75)
        self.assertLessEqual(mean(ast), 50)

    def test_exhibition_handles_short_side(self):
        g = asw.exhibition_game([('East', side('E', n=3)), ('West', side('W'))],
                                CONFIG.ALL_STAR.ALL_STAR_TOTAL_RANGE, random.Random(1))
        self.assertEqual(len(g['sides'][0]['lines']), 3)
        self.assertNotEqual(g['sides'][0]['score'], g['sides'][1]['score'])

    def test_dunk_score_bounds_and_skill(self):
        good = line('G'); good.update(dunk=95, athl=95)
        weak = line('W'); weak.update(dunk=40, athl=50)
        tg = tw = 0
        for seed in range(300):
            sg = asw.dunk_score(good, random.Random(seed))
            sw = asw.dunk_score(weak, random.Random(seed))
            for s in (sg, sw):
                self.assertGreaterEqual(s, CONFIG.ALL_STAR.DUNK_MIN)
                self.assertLessEqual(s, CONFIG.ALL_STAR.DUNK_MAX)
            tg += sg
            tw += sw
        self.assertGreater(tg, tw)

    def test_sophomores_from_last_rookies(self):
        cands = [line('C', ppg=30, age=21), line('B', ppg=12), line('A', ppg=18)]
        out = asw.pick_sophomores(cands, ['A', 'B'], 2, 22)
        self.assertEqual([x['name'] for x in out], ['A', 'B'])
        out = asw.pick_sophomores(cands, ['A', 'B'], 1, 22)
        self.assertEqual([x['name'] for x in out], ['A'])

    def test_sophomores_fallback_by_age(self):
        cands = [line('Old', ppg=30, age=27), line('Y1', ppg=10, age=21), line('Y2', ppg=20, age=22),
                 line('Y3', ppg=5, age=20)]
        out = asw.pick_sophomores(cands, [], 2, 22)
        self.assertEqual([x['name'] for x in out], ['Y2', 'Y1'])

    def test_sophomores_top_up_when_list_short(self):
        cands = [line('Known', ppg=3, age=24), line('Y1', ppg=10, age=21), line('Y2', ppg=20, age=22),
                 line('Old', ppg=30, age=27)]
        out = asw.pick_sophomores(cands, ['Known'], 3, 22)
        self.assertEqual([x['name'] for x in out], ['Known', 'Y2', 'Y1'])

    def test_pick_host_skips_recent_and_never_empty(self):
        cities = ['A', 'B', 'C']
        for seed in range(20):
            self.assertEqual(asw.pick_host(cities, ['A', 'C'], random.Random(seed)), 'B')
            self.assertIn(asw.pick_host(cities, ['A', 'B', 'C'], random.Random(seed)), cities)

def selections(n=12):
    return {'east': {'starters': side('E', 5), 'reserves': side('ER', 7), 'left_out': side('EL', 3)},
            'west': {'starters': side('W', 5), 'reserves': side('WR', 7), 'left_out': side('WL', 3)}}


def play(seed=1, shooters=8, dunkers=4, sophs=9, rookies=9):
    return asw.play_weekend(
        season=2003, host='Atlanta', selections=selections(),
        shooters=[line(f'S{i}') for i in range(shooters)],
        dunkers=[line(f'D{i}') for i in range(dunkers)],
        rookies=side('R', rookies), sophomores=side('SO', sophs), rng=random.Random(seed))


class PlayWeekendTests(unittest.TestCase):
    def test_weekend_snapshot_shape(self):
        snap = play()
        self.assertEqual(set(snap), {'season', 'host', 'selections', 'rookie_challenge', 'three_point', 'dunk', 'game'})
        self.assertEqual((snap['season'], snap['host']), (2003, 'Atlanta'))
        self.assertEqual(set(snap['rookie_challenge']), {'rookies', 'sophomores', 'game'})
        self.assertIsNotNone(snap['rookie_challenge']['game'])
        self.assertIsNotNone(snap['game'])
        self.assertEqual({s['label'] for s in snap['game']['sides']}, {'East', 'West'})
        self.assertEqual({s['label'] for s in snap['rookie_challenge']['game']['sides']}, {'Rookies', 'Sophomores'})
        tp = snap['three_point']
        self.assertEqual(len(tp['round1']), 8)
        self.assertEqual(sum(e['finalist'] for e in tp['round1']), 3)
        self.assertEqual(len(tp['final']), 3)
        scores = [e['score'] for e in tp['final']]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(tp['winner'], tp['final'][0]['name'])
        dk = snap['dunk']
        self.assertEqual(len(dk['round1']), 4)
        for e in dk['round1']:
            self.assertEqual(len(e['dunks']), 2)
            self.assertEqual(len({d['name'] for d in e['dunks']}), 2)
            self.assertEqual(e['total'], sum(d['score'] for d in e['dunks']))
        self.assertEqual(sum(e['finalist'] for e in dk['round1']), 2)
        self.assertEqual(len(dk['final']), 2)
        self.assertEqual(dk['winner'], dk['final'][0]['name'])
        self.assertTrue(all(e['name'] in {x['name'] for x in dk['round1'] if x['finalist']} for e in dk['final']))

    def test_tied_finals_always_carry_a_tiebreak(self):
        for seed in range(200):
            snap = play(seed)
            for key in ('three_point', 'dunk'):
                c = snap[key]
                tied = c['final'][0]['score'] == c['final'][1]['score']
                self.assertEqual(c['tiebreak'] is not None, tied)
                if tied:
                    self.assertEqual(c['tiebreak'][0]['name'], c['winner'])
                    self.assertEqual(c['final'][0]['name'], c['winner'])

    def test_three_point_scores_follow_existing_rules(self):
        for seed in range(30):
            tp = play(seed)['three_point']
            self.assertTrue(all(5 <= e['score'] <= 30 for e in tp['round1']))
            self.assertTrue(all(10 <= e['score'] <= 30 for e in tp['final']))

    def test_three_point_rating_shifts_scores(self):
        hi = dict(line('Hi'), r3=100)
        lo = dict(line('Lo'), r3=40)
        snap = asw.play_weekend(season=1, host='X', selections=selections(), shooters=[hi, lo], dunkers=[],
                                rookies=[], sophomores=[], rng=random.Random(3))
        by = {e['name']: e['score'] for e in snap['three_point']['round1']}
        self.assertGreater(by['Hi'], by['Lo'])

    def test_weekend_with_too_few_players(self):
        snap = play(shooters=2, dunkers=1, sophs=0)
        self.assertEqual(len(snap['three_point']['final']), 2)
        self.assertEqual(len(snap['dunk']['final']), 1)
        self.assertEqual(snap['dunk']['winner'], 'D0')
        self.assertIsNone(snap['rookie_challenge']['game'])
        empty = asw.play_weekend(season=1, host='X', selections={'east': {'starters': [], 'reserves': [], 'left_out': []},
                                 'west': {'starters': [], 'reserves': [], 'left_out': []}},
                                 shooters=[], dunkers=[], rookies=[], sophomores=[], rng=random.Random(1))
        self.assertIsNone(empty['game'])
        self.assertIsNone(empty['three_point']['winner'])
        self.assertIsNone(empty['dunk']['winner'])

    def test_three_point_final_tie_goes_to_a_shoot_off(self):
        # Round 1: 20, 18, 16; final: 22, 22, 15 (a tie); shoot-off: S0 20, S1 24 -> S1 wins.
        rng = SeqRng(randint=[20, 18, 16, 22, 22, 15, 20, 24])
        tp = asw._three_point_contest([line('S0'), line('S1'), line('S2')], rng)
        self.assertEqual(tp['tiebreak'], [{'name': 'S1', 'score': 24}, {'name': 'S0', 'score': 20}])
        self.assertEqual(tp['winner'], 'S1')
        self.assertEqual(tp['final'][0]['name'], 'S1')

    def test_three_point_shoot_off_still_level_goes_to_round1_rank(self):
        n = CONFIG.ALL_STAR.TIEBREAK_MAX_ROUNDS
        rng = SeqRng(randint=[20, 18, 22, 22] + [21, 21] * n)
        tp = asw._three_point_contest([line('S0'), line('S1')], rng)
        self.assertEqual(tp['winner'], 'S0')
        self.assertEqual(tp['tiebreak'][0]['name'], 'S0')

    def test_three_point_no_tie_no_tiebreak(self):
        rng = SeqRng(randint=[20, 18, 16, 24, 22, 15])
        self.assertIsNone(asw._three_point_contest([line('S0'), line('S1'), line('S2')], rng)['tiebreak'])

    def test_dunk_final_tie_goes_to_a_dunk_off(self):
        # Base skill score 37.5; uniform noise per dunk. Round 1: D0 2 dunks, D1 2 dunks;
        # final: both 40 (a tie); dunk-off: D0 38, D1 45 -> D1 wins.
        noise = [2.5, 2.5, 0.5, 0.5, 2.5, 2.5, 0.5, 7.5]
        dk = asw._dunk_contest([line('D0'), line('D1')], SeqRng(uniform=noise))
        self.assertEqual([e['score'] for e in dk['final']], [40, 40])
        self.assertEqual([(e['name'], e['score']) for e in dk['tiebreak']], [('D1', 45), ('D0', 38)])
        self.assertTrue(all(e['dunk'] in CONFIG.ALL_STAR.DUNK_NAMES for e in dk['tiebreak']))
        self.assertEqual(dk['winner'], 'D1')
        self.assertEqual(dk['final'][0]['name'], 'D1')

    def test_three_point_cutoff_tie_goes_to_better_rating(self):
        # Three finalists; S2 and S3 tie on 18 for the last spot, S3 has the better r3 (74: bonus still 0).
        shooters = [line('S0'), line('S1'), line('S2'), dict(line('S3'), r3=74)]
        tp = asw._three_point_contest(shooters, SeqRng(randint=[20, 19, 18, 18, 24, 22, 20]))
        self.assertEqual([e['name'] for e in tp['round1'] if e['finalist']], ['S0', 'S1', 'S3'])

    def test_dunk_cutoff_tie_goes_to_dunk_then_athl(self):
        a, b, c = line('A'), dict(line('B'), dunk=60, athl=70), dict(line('C'), dunk=61, athl=50)
        # Equal totals whatever the ratings: every dunk scores 40.
        orig = asw.dunk_score
        asw.dunk_score = lambda x, rng: 40
        try:
            dk = asw._dunk_contest([a, b, c], SeqRng())
        finally:
            asw.dunk_score = orig
        self.assertEqual([e['name'] for e in dk['round1']], ['C', 'B', 'A'])
        self.assertEqual([e['name'] for e in dk['round1'] if e['finalist']], ['C', 'B'])

    def test_snapshot_is_json_plain(self):
        snap = play()
        self.assertEqual(json.loads(json.dumps(snap)), snap)


if __name__ == '__main__':
    unittest.main()
