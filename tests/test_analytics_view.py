"""League Analytics views (core/analytics_view.py): pure functions over saved box scores, no Flask."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analytics_view import (ARCHIVE_KEYS, archive_for_rosters, archive_lines, archive_season_lines, fit_exponent,
                                 league_view, player_stats, players_view, playoff_box_scores,
                                 season_label, splits_view, teams_view)

STATS = ('pts', 'reb', 'ast', 'stl', 'blk', 'to', 'pf', 'fgm', 'fga', 'tpm', 'tpa', 'ftm', 'fta', 'plus_minus')


def line(name, pos='PG', min=30.0, **stats):
    out = {'name': name, 'pos': pos, 'is_starter': True, 'min': min}
    for key in STATS:
        out[key] = stats.get(key, 0)
    return out


def side(name, lines, quarters=None):
    score = sum(p['pts'] for p in lines)
    return {'name': name, 'score': score, 'quarters': quarters or [score // 4] * 4, 'players': lines, 'totals': {}}


def game(gid, day, date, home, away, home_lines, away_lines, home_q=None, away_q=None):
    return {'game_id': gid, 'date': date, 'day_index': day,
            'home_team': side(home, home_lines, home_q), 'away_team': side(away, away_lines, away_q), 'top_performer': {}}


def bench(team, n=4, min=52.5, **stats):
    """Filler players so a team's minutes add up (default 4 × 52.5 = 210 + a 30-minute player = 240)."""
    return [line(f'{team} Bench {i}', min=min, **stats) for i in range(n)]


def scores(*games):
    return {g['game_id']: g for g in games}


class PlayersViewTests(unittest.TestCase):
    def test_empty_box_scores_give_empty_views(self):
        view = players_view({}, set(), None)
        self.assertEqual(view['players'], [])
        meta = view['meta']
        self.assertEqual(meta['games'], 0)
        self.assertIsNone(meta['season'])
        self.assertEqual((meta['tint_top'], meta['tint_bottom'], meta['split_tint']), (90, 15, 0.06))
        self.assertEqual((meta['qualify_gp_share'], meta['qualify_mpg'], meta['oreb_share']), (0.5, 20.0, 0.25))

    def test_season_label_from_first_date(self):
        bs = scores(game('g2', 170, '2028-04-14', 'A', 'B', [line('x')], [line('y')]),
                    game('g1', 0, '2027-10-22', 'A', 'B', [line('x')], [line('y')]))
        self.assertEqual(season_label(bs), '2027-28')

    def _star_games(self):
        star = dict(pts=20, fgm=8, fga=16, tpm=2, tpa=5, ftm=2, fta=2, to=4, ast=6)
        return scores(
            game('g1', 1, '2027-10-23', 'A', 'B', [line('Star', **star)] + bench('A'), [line('Opp')] + bench('B')),
            game('g2', 2, '2027-10-24', 'B', 'A', [line('Opp')] + bench('B'), [line('Star', **star)] + bench('A')))

    def _row(self, view, name):
        return next(p for p in view['players'] if p['name'] == name)

    def test_player_per_game_and_shooting(self):
        s = self._row(players_view(self._star_games(), set(), None), 'Star')['s']
        self.assertEqual(s['gp'], 2)
        self.assertEqual(s['pts_pg'], 20.0)
        self.assertEqual(s['efg_pct'], round((16 + 0.5 * 4) / 32 * 100, 1))
        self.assertEqual(s['ts_pct'], round(40 / (2 * (32 + 0.44 * 4)) * 100, 1))
        self.assertEqual(s['tpa_rate'], round(10 / 32 * 100, 1))
        self.assertEqual(s['ft_rate'], 12.5)
        self.assertEqual(s['ato'], 1.5)
        self.assertEqual(s['pts_36'], 24.0)
        self.assertEqual(s['pts_tot'], 40)

    def test_usage_uses_team_totals_of_games_played(self):
        # Team: player 36 min (FGA 20, FTA 5, TO 3) + 4 others at 51 min (FGA 15, FTA 3.75→ use 4+4+4+3, TO 9 total)
        others = [line(f'O{i}', min=51.0, fga=15, fta=f, to=t) for i, (f, t) in enumerate([(4, 3), (4, 2), (4, 2), (3, 2)])]
        bs = scores(game('g1', 1, '2027-10-23', 'A', 'B', [line('P', min=36.0, fga=20, fta=5, to=3)] + others,
                         [line('Opp')] + bench('B')))
        s = self._row(players_view(bs, set(), None), 'P')['s']
        expected = 100 * (20 + 0.44 * 5 + 3) * (240 / 5) / (36 * (80 + 0.44 * 20 + 12))
        self.assertEqual(s['usg_pct'], round(expected, 1))

    def test_traded_player_is_one_row_with_both_teams(self):
        bs = scores(
            game('g1', 1, '2027-10-23', 'A Team', 'C', [line('Mover', pts=10, fga=8, fgm=4)] + bench('A'), [line('c')] + bench('C')),
            game('g2', 5, '2027-10-27', 'B Team', 'C', [line('Mover', pts=14, fga=10, fgm=6)] + bench('B'), [line('c')] + bench('C')))
        rows = [p for p in players_view(bs, set(), None)['players'] if p['name'] == 'Mover']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['teams'], ['A Team', 'B Team'])
        self.assertEqual(rows[0]['team'], 'B Team')
        self.assertEqual(rows[0]['gp'], 2)
        self.assertEqual(rows[0]['s']['pts_tot'], 24)

    def test_zero_attempt_player_has_none_percentages(self):
        bs = scores(game('g1', 1, '2027-10-23', 'A', 'B', [line('Ghost'), line('DNP Guy', min=0)] + bench('A'),
                         [line('Opp')] + bench('B')))
        view = players_view(bs, set(), None)
        s = self._row(view, 'Ghost')['s']
        for key in ('fg_pct', 'ts_pct', 'efg_pct', 'ft_pct', 'ato'):
            self.assertIsNone(s[key], key)
        self.assertFalse(any(p['name'] == 'DNP Guy' for p in view['players']))

    def test_overtime_game_minutes_and_quarters(self):
        # 265 team minutes (one overtime): usage scales with 265/5, not 240/5.
        others = [line(f'O{i}', min=58.75, fga=15, fta=4, to=2) for i in range(4)]
        bs = scores(game('g1', 1, '2027-10-23', 'A', 'B', [line('P', min=30.0, fga=20, fta=5, to=3)] + others,
                         [line('Opp')] + bench('B'), home_q=[20, 20, 20, 20, 10], away_q=[20, 20, 20, 20, 5]))
        s = self._row(players_view(bs, set(), None), 'P')['s']
        expected = 100 * (20 + 0.44 * 5 + 3) * (265 / 5) / (30 * (80 + 0.44 * 21 + 11))
        self.assertEqual(s['usg_pct'], round(expected, 1))

    def test_qualification_and_percentiles(self):
        games = []
        for i in range(10):
            a_lines = [line('Scorer', min=34.0, pts=30, fga=20, fgm=12), line('Second', min=34.0, pts=10, fga=10, fgm=5),
                       line('Short', min=18.0, pts=8, fga=6, fgm=3)]
            if i < 4:
                a_lines.append(line('Rare', min=30.0, pts=40, fga=25, fgm=16))
            games.append(game(f'g{i}', i * 2, '2027-11-%02d' % (i + 1), 'A', 'B', a_lines, [line('Opp', pts=5, fga=40, fgm=2)]))
        view = players_view(scores(*games), set(), None)
        rare, short, scorer, second = (self._row(view, n) for n in ('Rare', 'Short', 'Scorer', 'Second'))
        self.assertFalse(rare['qualified'])
        self.assertFalse(short['qualified'])
        self.assertTrue(scorer['qualified'])
        self.assertTrue(all(v is None for v in rare['pct'].values()))
        self.assertEqual(scorer['pct']['pts_pg'], 100.0)
        self.assertLess(second['pct']['pts_pg'], 100.0)

    def test_player_not_on_any_roster_is_flagged(self):
        bs = scores(game('g1', 1, '2027-10-23', 'A', 'B', [line('Kept Guy'), line('Gone Guy')], [line('Opp')]))
        view = players_view(bs, {'Kept Guy'}, None)
        self.assertTrue(self._row(view, 'Kept Guy')['in_league'])
        self.assertFalse(self._row(view, 'Gone Guy')['in_league'])

    def test_game_score_formula(self):
        bs = scores(game('g1', 1, '2027-10-23', 'A', 'B',
                         [line('G', pts=30, fgm=11, fga=20, fta=8, ftm=6, reb=10, stl=2, ast=7, blk=1, pf=3, to=4)],
                         [line('Opp')]))
        s = self._row(players_view(bs, set(), None), 'G')['s']
        self.assertEqual(s['gmsc'], round(30 + 4.4 - 14 - 0.8 + 0.7 * 2.5 + 0.3 * 7.5 + 2 + 4.9 + 0.7 - 1.2 - 4, 1))


class PerTests(unittest.TestCase):
    def _league(self):
        a = [line('A1', min=40, pts=28, fgm=11, fga=20, tpm=2, tpa=5, ftm=4, fta=5, reb=6, ast=8, stl=2, blk=0, to=3, pf=2),
             line('A2', min=40, pts=12, fgm=5, fga=12, ftm=2, fta=3, reb=11, ast=2, stl=1, blk=2, to=2, pf=4),
             line('A3', min=40, pts=8, fgm=3, fga=10, tpm=2, tpa=6, reb=3, ast=3, stl=0, to=1, pf=3)]
        b = [line('B1', min=40, pts=20, fgm=8, fga=18, tpm=1, tpa=4, ftm=3, fta=4, reb=5, ast=5, stl=1, to=4, pf=2),
             line('B2', min=40, pts=16, fgm=7, fga=13, ftm=2, fta=2, reb=9, ast=1, blk=1, to=2, pf=3),
             line('B3', min=40, pts=6, fgm=2, fga=9, tpm=1, tpa=4, ftm=1, fta=2, reb=4, ast=4, stl=2, to=2, pf=1)]
        return scores(game('g1', 1, '2027-10-23', 'A', 'B', a, b), game('g2', 2, '2027-10-24', 'B', 'A', b, a))

    def test_per_league_average_is_fifteen(self):
        rows = players_view(self._league(), set(), None)['players']
        mins = sum(r['s']['min'] for r in rows)
        avg = sum(r['s']['per'] * r['s']['min'] for r in rows) / mins
        self.assertAlmostEqual(avg, 15.0, delta=0.05)

    def test_per_ranks_better_line_higher(self):
        rows = {r['name']: r['s']['per'] for r in players_view(self._league(), set(), None)['players']}
        self.assertGreater(rows['A1'], rows['A3'])
        self.assertGreater(rows['B1'], rows['B3'])


class TeamsViewTests(unittest.TestCase):
    CONF = {'A': 'East', 'B': 'West'}

    def _one_game(self):
        # A: 100 pts, FGA 80, FTA 25 (0.44*25 = 11), TO 9 -> raw 100. B: 90 pts, FGA 78, FTA 20 (8.8), TO 9.2 -> use TO 9 + extra
        a = [line('a1', min=240, pts=100, fgm=38, fga=80, tpm=8, tpa=24, ftm=16, fta=25, to=9, reb=44, ast=22)]
        b = [line('b1', min=240, pts=90, fgm=34, fga=78, tpm=6, tpa=20, ftm=16, fta=20, to=9, reb=38, ast=18)]
        return scores(game('g1', 1, '2027-10-23', 'A', 'B', a, b, home_q=[25, 25, 25, 25], away_q=[20, 25, 20, 25]))

    def _team(self, view, name):
        return next(t for t in view['teams'] if t['name'] == name)

    def test_team_ratings_from_both_sides(self):
        a = self._team(teams_view(self._one_game(), self.CONF, None), 'A')
        poss = (100 + (78 + 0.44 * 20 + 9)) / 2
        self.assertEqual(a['s']['pace'], round(poss, 1))
        self.assertEqual(a['s']['ortg'], round(100 * 100 / poss, 1))
        self.assertEqual(a['s']['drtg'], round(100 * 90 / poss, 1))
        self.assertEqual(a['s']['net'], round(100 * 100 / poss - 100 * 90 / poss, 1))
        self.assertEqual(a['conference'], 'East')

    def test_four_factors_both_ends(self):
        view = teams_view(self._one_game(), self.CONF, None)
        a, b = self._team(view, 'A')['s'], self._team(view, 'B')['s']
        self.assertEqual(a['efg'], round((38 + 4) / 80 * 100, 1))
        self.assertEqual(a['ft_rate'], round(25 / 80 * 100, 1))
        self.assertEqual(a['tov_pct'], round(9 / 100 * 100, 1))
        for k in ('efg', 'tov_pct', 'ft_rate'):
            self.assertEqual(a['opp_' + k], b[k])
        self.assertEqual(a['reb_diff'], 6.0)

    def test_fit_exponent_recovers_true_value(self):
        teams = []
        for pf, pa in [(110, 100), (105, 101), (100, 100), (98, 104), (95, 106), (108, 99), (102, 103), (99, 97),
                       (101, 108), (104, 96)]:
            teams.append((82 * pf ** 8 / (pf ** 8 + pa ** 8), 82, pf * 82, pa * 82))
        fit = fit_exponent(teams)
        self.assertEqual(fit['value'], 8.0)
        self.assertTrue(fit['fitted'])
        self.assertLess(fit['rmse'], 0.01)

    def test_few_games_use_fallback_exponent(self):
        fit = fit_exponent([(5, 9, 900, 880), (4, 9, 880, 900)])
        self.assertEqual(fit, {'value': 10.0, 'rmse': None, 'fitted': False})
        self.assertFalse(teams_view(self._one_game(), self.CONF, None)['exponent']['fitted'])

    def test_quarter_margins_close_and_home_splits(self):
        a = [line('a1', min=240, pts=103, fga=80, fgm=40)]
        b = [line('b1', min=240, pts=100, fga=80, fgm=40)]
        ot_a = [line('a1', min=265, pts=110, fga=90, fgm=44)]
        ot_b = [line('b1', min=265, pts=104, fga=90, fgm=42)]
        bs = scores(game('g1', 1, '2027-10-23', 'A', 'B', a, b, home_q=[25, 25, 25, 28], away_q=[27, 25, 25, 23]),
                    game('g2', 3, '2027-10-25', 'B', 'A', ot_b, ot_a, home_q=[24, 25, 25, 26, 4], away_q=[25, 25, 25, 25, 10]))
        t = self._team(teams_view(bs, self.CONF, None), 'A')
        self.assertEqual(t['quarters'], [-0.5, 0.0, 0.0, 2.0])
        self.assertEqual(t['close'], [1, 0])
        self.assertEqual(t['home'], [1, 0])
        self.assertEqual(t['away'], [1, 0])

    def test_team_percentiles_invert_low_is_good(self):
        view = teams_view(self._one_game(), self.CONF, None)
        best = min(view['teams'], key=lambda t: t['s']['drtg'])
        self.assertEqual(best['pct']['drtg'], 100.0)
        self.assertEqual(best['pct']['net'], 100.0)

    def test_luck_is_wins_minus_expected(self):
        t = self._team(teams_view(self._one_game(), self.CONF, None), 'A')
        self.assertEqual(t['s']['luck'], round(t['w'] - t['s']['exp_w'], 1))
        self.assertEqual(t['s']['exp_w'], round(100 ** 10 / (100 ** 10 + 90 ** 10), 1))


class LeagueViewTests(unittest.TestCase):
    def _two_months(self):
        return scores(
            game('g1', 1, '2027-10-23', 'A', 'B', [line('a', min=240, pts=100, fga=80, fgm=40, tpa=20, tpm=8, fta=20, ftm=12, to=10)],
                 [line('b', min=240, pts=90, fga=82, fgm=36, tpa=25, tpm=6, fta=16, ftm=12, to=12)]),
            game('g2', 12, '2027-11-03', 'B', 'A', [line('b', min=240, pts=95, fga=80, fgm=38, tpa=22, tpm=7, fta=18, ftm=12, to=11)],
                 [line('a', min=240, pts=99, fga=81, fgm=39, tpa=21, tpm=9, fta=16, ftm=12, to=9)]),
            game('g3', 14, '2027-11-05', 'A', 'B', [line('a', min=240, pts=88, fga=79, fgm=35, tpa=20, tpm=6, fta=14, ftm=12, to=13)],
                 [line('b', min=240, pts=101, fga=80, fgm=41, tpa=24, tpm=9, fta=15, ftm=10, to=8)]))

    def test_league_view_matches_team_view(self):
        bs = self._two_months()
        league = {t['name']: t for t in league_view(bs, None)['teams']}
        for t in teams_view(bs, {}, None)['teams']:
            for k in ('ortg', 'drtg', 'net', 'exp_w', 'luck'):
                self.assertEqual(league[t['name']][k], t['s'][k])
            self.assertEqual(league[t['name']]['w'], t['w'])

    def test_months_and_baseline(self):
        view = league_view(self._two_months(), 'A')
        self.assertEqual([m['label'] for m in view['months']], ['Oct', 'Nov'])
        self.assertEqual([m['games'] for m in view['months']], [1, 2])
        self.assertEqual(view['months'][1]['home_win_pct'], 0.0)
        self.assertEqual(view['months'][0]['ppg'], 95.0)
        self.assertEqual(view['baseline']['ppg'], round((100 + 90 + 95 + 99 + 88 + 101) / 6, 1))
        self.assertEqual(view['baseline']['home_win_pct'], round(100 * 1 / 3, 1))
        self.assertTrue(next(t for t in view['teams'] if t['name'] == 'A')['is_user_team'])

    def test_league_view_empty(self):
        view = league_view({}, None)
        self.assertEqual((view['teams'], view['months']), ([], []))
        self.assertTrue(all(v is None for v in view['baseline'].values()))
        self.assertEqual(view['league_avg'], {'ortg': None, 'drtg': None})


class SplitsViewTests(unittest.TestCase):
    CONF = {'A': 'East', 'B': 'West', 'C': 'East'}

    def _season(self):
        """A plays days 1 (home W vs B), 2 (away L at C), 5 (home W vs B), 6 (away W at B); Star skips day 5."""
        def star(pts):
            return line('Star', min=34, pts=pts, fga=pts // 2 + 4, fgm=pts // 2 - 2, reb=5, ast=6, stl=1)
        return scores(
            game('g1', 1, '2027-10-23', 'A', 'B', [star(30), line('a2', pts=70)], [line('b', pts=90)], [25, 25, 25, 25], [22, 23, 22, 23]),
            game('g2', 2, '2027-10-24', 'C', 'A', [line('c', pts=110)], [star(20), line('a2', pts=80)], [30, 25, 25, 30], [25, 25, 25, 25]),
            game('g3', 5, '2027-11-02', 'A', 'B', [line('a2', pts=99)], [line('b', pts=96)], [25, 25, 25, 24], [24, 24, 24, 24]),
            game('g4', 6, '2027-11-03', 'B', 'A', [line('b', pts=90)], [star(40), line('a2', pts=55)], [20, 25, 20, 25], [25, 25, 25, 20]))

    def test_player_splits_home_away_wins_b2b(self):
        view = splits_view(self._season(), self.CONF, None, player='Star')
        self.assertEqual(view['kind'], 'player')
        self.assertEqual(view['team'], 'A')
        labels = [r['label'] for r in view['splits']]
        self.assertEqual(labels, ['Home', 'Away', 'In wins', 'In losses', 'Back-to-back 2nd night', 'Rested'])
        self.assertEqual([r['gp'] for r in view['splits']], [1, 2, 2, 1, 2, 1])
        self.assertEqual(view['season_line']['gp'], 3)
        self.assertEqual(view['season_line']['pts'], 30.0)

    def test_player_log_has_dnp_rows_inside_stint(self):
        bs = self._season()
        bs['g5'] = game('g5', 9, '2027-11-06', 'A', 'C', [line('a2', pts=100)], [line('c', pts=90)])
        log = splits_view(bs, self.CONF, None, player='Star')['log']
        self.assertEqual([r['game_id'] for r in log], ['g4', 'g3', 'g2', 'g1'])
        dnp = log[1]
        self.assertTrue(dnp['dnp'])
        self.assertIsNone(dnp['pts'])
        self.assertTrue(log[0]['b2b'])
        self.assertEqual((log[0]['opp'], log[0]['home'], log[0]['win'], log[0]['score_for'], log[0]['score_against']),
                         ('B', False, True, 95, 90))

    def test_player_highs_and_months(self):
        view = splits_view(self._season(), self.CONF, None, player='Star')
        highs = {h['stat']: h for h in view['highs']}
        self.assertEqual(list(highs), ['pts', 'reb', 'ast', 'stl', 'gmsc'])
        self.assertEqual((highs['pts']['value'], highs['pts']['opp'], highs['pts']['date'], highs['pts']['game_id']),
                         (40, 'B', '2027-11-03', 'g4'))
        self.assertEqual([m['label'] for m in view['months']], ['Oct', 'Nov'])
        self.assertEqual([m['gp'] for m in view['months']], [2, 1])

    def test_opponent_splits(self):
        view = splits_view(self._season(), self.CONF, None, player='Star')
        self.assertEqual([(r['label'], r['gp']) for r in view['opponents']], [('B', 2), ('C', 1)])

    def test_team_splits_and_quarters(self):
        view = splits_view(self._season(), self.CONF, None, team='A')
        self.assertEqual(view['kind'], 'team')
        labels = [r['label'] for r in view['splits']]
        for want in ('vs East', 'vs West', 'Within 5 pts'):
            self.assertIn(want, labels)
        close = next(r for r in view['splits'] if r['label'] == 'Within 5 pts')
        self.assertEqual((close['w'], close['l'], close['gp']), (2, 0, 2))
        # A's margins per game: g1 [3,2,3,2], g2 [-5,0,0,-5], g3 [1,1,1,0], g4 [5,0,5,-5]
        self.assertEqual(view['quarters'], [1.0, round(3 / 4, 1), round(9 / 4, 1), -2.0])
        first = view['log'][-1]
        self.assertEqual((first['pts'], first['pm'], first['min']), (100, 10, None))
        self.assertEqual(len(view['log']), 4)

    def test_unknown_name_returns_none(self):
        self.assertIsNone(splits_view(self._season(), self.CONF, None, player='Nobody'))
        self.assertIsNone(splits_view(self._season(), self.CONF, None, team='Nowhere'))


class ConfigDrivenTests(unittest.TestCase):
    """Every tunable the page shows or uses comes from CONFIG.ANALYTICS (per-save modding)."""

    def test_meta_carries_display_tunables(self):
        meta = players_view({}, set(), None)['meta']
        self.assertEqual((meta['close_margin'], meta['fta_weight'], meta['per_avg'], meta['leaders_per_tile']), (5, 0.44, 15.0, 3))

    def test_per_follows_fta_weight(self):
        import dataclasses
        import core.analytics_view as av
        bs = PerTests()._league()
        before = {r['name']: r['s']['per'] for r in players_view(bs, set(), None)['players']}
        saved = av.CONFIG
        try:
            av.CONFIG = dataclasses.replace(saved, ANALYTICS=dataclasses.replace(saved.ANALYTICS, FTA_WEIGHT=0.6))
            after = {r['name']: r['s']['per'] for r in players_view(bs, set(), None)['players']}
        finally:
            av.CONFIG = saved
        self.assertNotEqual(before, after)
        # possessions-based stats move too, so the weight is read everywhere, not only in PER
        self.assertTrue(any(before[n] != after[n] for n in before))


class ArchiveLinesTests(unittest.TestCase):
    def _games(self):
        star = dict(pts=20, fgm=8, fga=16, tpm=2, tpa=5, ftm=2, fta=2, to=4, ast=6, plus_minus=3)
        return scores(
            game('g1', 1, '2027-10-23', 'Alpha', 'B', [line('Star', **star)] + bench('Alpha'), [line('Opp')] + bench('B')),
            game('g2', 2, '2027-10-24', 'B', 'Alpha', [line('Opp')] + bench('B'), [line('Star', **star)] + bench('Alpha')))

    def test_archive_lines_keeps_raw_sums(self):
        star = archive_lines(self._games())['Star']
        self.assertEqual(star['gp'], 2)
        self.assertEqual(star['pts'], 40)
        self.assertEqual(star['teams'], ['Alpha'])
        for key in ARCHIVE_KEYS:
            self.assertIn(key, star)
        self.assertIn('per', star)

    def test_archive_counts_only_the_latest_season(self):
        """Auto-sim used to leave last season's box scores in place: they must not leak into this season's line."""
        old = game('old', 1, '2026-11-02', 'Alpha', 'B', [line('Star', pts=50)] + bench('Alpha'), [line('Opp')] + bench('B'))
        bs = dict(self._games(), old=old)
        star = archive_for_rosters(bs, ['Star', 'Opp'])['Star']
        self.assertEqual((star['gp'], star['pts']), (2, 40))

    def test_archive_drops_names_on_two_rosters(self):
        """Two players saved under one name share one box-score line: neither gets it."""
        lines = archive_for_rosters(self._games(), ['Star', 'Star', 'Opp'])
        self.assertNotIn('Star', lines)
        self.assertIn('Opp', lines)

    def test_archive_round_trip_matches_players_view(self):
        bs = self._games()
        live = next(r for r in players_view(bs, {'Star'}, None)['players'] if r['name'] == 'Star')['s']
        rebuilt = player_stats(archive_lines(bs)['Star'])
        for key, value in live.items():
            if key != 'per':
                self.assertEqual(rebuilt[key], value, key)


def series(*sheets):
    return {'s1_nome': 'A', 's2_nome': 'B', 'games': [{'game_num': i + 1, 'result_sheet': s} for i, s in enumerate(sheets)]}


EXTRA = ('oreb', 'dreb', 'ast_fgm', 'rim_fga', 'rim_fgm', 'mid_fga', 'mid_fgm', 'clutch_pts', 'clutch_fga',
         'clutch_fgm', 'clutch_min')


def xline(name, **stats):
    """A box-score line saved since 2026-11-15: it carries the new counters (0 unless given)."""
    out = line(name, **{k: v for k, v in stats.items() if k not in EXTRA})
    for k in EXTRA:
        out[k] = stats.get(k, 0)
    return out


def xbench(team, n=4):
    return [xline(f'{team} Bench {i}', min=52.5, reb=2, dreb=2) for i in range(n)]


class ExtraStatsTests(unittest.TestCase):
    """Offensive/defensive rebounds, assisted makes, shot zones and clutch numbers in League Analytics."""

    def _games(self, old_second_game=False):
        star = dict(pts=20, fgm=8, fga=16, tpm=0, tpa=2, ftm=4, fta=4, reb=10, oreb=4, dreb=6, ast_fgm=5,
                    rim_fga=10, rim_fgm=6, mid_fga=4, mid_fgm=2, clutch_pts=6, clutch_fga=3, clutch_fgm=2, clutch_min=4.0)
        g1 = game('g1', 1, '2027-10-23', 'Alpha', 'B', [xline('Star', **star)] + xbench('Alpha'),
                  [xline('Opp', reb=8, oreb=3, dreb=5)] + xbench('B'))
        second = (game('g2', 2, '2027-10-24', 'B', 'Alpha', [line('Opp', reb=8)] + bench('B'),
                       [line('Star', **{k: v for k, v in star.items() if k not in EXTRA})] + bench('Alpha'))
                  if old_second_game else
                  game('g2', 2, '2027-10-24', 'B', 'Alpha', [xline('Opp', reb=8, oreb=3, dreb=5)] + xbench('B'),
                       [xline('Star', **star)] + xbench('Alpha')))
        return scores(g1, second)

    def _star(self, box_scores):
        return next(r for r in players_view(box_scores, set(), None)['players'] if r['name'] == 'Star')['s']

    def test_new_counters_become_stats(self):
        s = self._star(self._games())
        self.assertEqual((s['oreb_pg'], s['dreb_pg'], s['oreb_tot']), (4.0, 6.0, 8))
        self.assertEqual((s['rim_fg_pct'], s['mid_fg_pct']), (60.0, 50.0))
        self.assertEqual((s['rim_rate'], s['mid_rate']), (62.5, 25.0))
        self.assertEqual(s['ast_fgm_pct'], 62.5)
        self.assertEqual((s['clutch_pts_tot'], s['clutch_fg_pct'], s['clutch_min']), (12, 66.7, 8.0))
        # ORB% = 100 * ORB * (TmMin / 5) / (MP * (TmORB + OppDRB)), two games: 100 * 8 * (480 / 5) / (60 * (8 + 26))
        self.assertEqual(s['orb_pct'], 37.6)
        self.assertIsNotNone(s['drb_pct'])

    def test_clutch_fg_pct_needs_enough_attempts(self):
        import dataclasses
        from unittest import mock
        from core.config import CONFIG
        # Star has 6 clutch attempts over the two games
        stricter = dataclasses.replace(CONFIG, ANALYTICS=dataclasses.replace(CONFIG.ANALYTICS, CLUTCH_FG_MIN_FGA=7))
        with mock.patch('core.analytics_view.CONFIG', stricter):
            self.assertIsNone(self._star(self._games())['clutch_fg_pct'])
        self.assertEqual(CONFIG.ANALYTICS.CLUTCH_FG_MIN_FGA, 5)
        self.assertEqual(self._star(self._games())['clutch_fg_pct'], 66.7)

    def test_old_box_scores_leave_the_new_stats_empty(self):
        s = self._star(scores(game('g1', 1, '2027-10-23', 'Alpha', 'B', [line('Star', pts=20, reb=10)] + bench('Alpha'),
                                   [line('Opp')] + bench('B'))))
        for key in ('oreb_pg', 'orb_pct', 'rim_fg_pct', 'ast_fgm_pct', 'clutch_pts_tot'):
            self.assertIsNone(s[key], key)

    def test_a_season_mixing_old_and_new_games_is_not_half_counted(self):
        s = self._star(self._games(old_second_game=True))
        self.assertIsNone(s['oreb_pg'])
        self.assertEqual(s['reb_pg'], 10.0)

    def test_team_rebound_factors(self):
        rows = {r['name']: r for r in teams_view(self._games(), {'Alpha': 'East', 'B': 'West'}, None)['teams']}
        s = rows['Alpha']['s']
        # Alpha: 4 OREB vs B's 13 DREB, 14 DREB vs B's 3 OREB, in both games
        self.assertEqual((s['oreb_pg'], s['orb_pct'], s['drb_pct']), (4.0, 23.5, 82.4))

    def test_team_rebound_factors_need_counted_games(self):
        rows = {r['name']: r for r in teams_view(self._games(old_second_game=True), {'Alpha': 'East', 'B': 'West'}, None)['teams']}
        self.assertIsNone(rows['Alpha']['s']['orb_pct'])

    def test_archived_line_keeps_the_new_stats(self):
        full = archive_lines(self._games())['Star']
        self.assertEqual(player_stats(full)['rim_fg_pct'], 60.0)


class PlayoffBoxScoreTests(unittest.TestCase):
    """Playoff games keep their box score only in the bracket (series games' result_sheet)."""

    def _games(self):
        g = lambda gid, home, away: game(gid, 0, '', home, away, [line('Star' if home == 'Alpha' else 'Opp', pts=20, fga=10, fgm=8)]
                                         + bench(home), [line('Opp' if home == 'Alpha' else 'Star', pts=10)] + bench(away))
        return g('PO-QF-B@Alpha-G1', 'Alpha', 'B'), g('PO-QF-Alpha@B-G2', 'B', 'Alpha'), g('PO-PI-C@D-G1', 'D', 'C'), \
            g('PO-F-Z@Alpha-G1', 'Alpha', 'Z')

    def test_collects_every_round_play_in_and_finals(self):
        qf1, qf2, pi, fin = self._games()
        bracket = {'east': {'play_in': [None, series(pi), None], 'qf': [series(qf1, qf2)], 'sf': [], 'cf': []},
                   'west': {'play_in': [], 'qf': [], 'sf': [], 'cf': []},
                   'finals': [series(fin, None)]}
        self.assertEqual(set(playoff_box_scores(bracket)), {qf1['game_id'], qf2['game_id'], pi['game_id'], fin['game_id']})

    def test_no_bracket_gives_no_games(self):
        self.assertEqual(playoff_box_scores(None), {})
        self.assertEqual(playoff_box_scores({'east': {}, 'west': {}, 'finals': None}), {})

    def test_archive_season_lines_splits_regular_season_and_playoffs(self):
        qf1, qf2, _pi, _fin = self._games()
        rs = scores(game('g1', 1, '2027-10-23', 'Alpha', 'B', [line('Star', pts=30)] + bench('Alpha'),
                         [line('Opp')] + bench('B')))
        bracket = {'east': {'qf': [series(qf1, qf2)]}, 'west': {}, 'finals': []}
        out = archive_season_lines(rs, bracket, ['Star', 'Opp'])
        self.assertEqual((out['rs']['Star']['gp'], out['rs']['Star']['pts']), (1, 30))
        self.assertEqual((out['po']['Star']['gp'], out['po']['Star']['pts']), (2, 30))  # 20 at home in G1, 10 away in G2
        self.assertIsNotNone(player_stats(out['po']['Star'])['ts_pct'])


if __name__ == '__main__':
    unittest.main()
