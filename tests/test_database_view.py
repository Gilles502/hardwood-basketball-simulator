"""Player Database views (core/database_view.py): pure functions over player_careers.json and the live season."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analytics_view import archive_lines, player_stats
from core import database_view
from core.config import Database
from core.database_view import (STAT_KEYS, career_line, current_records, directory_view, finder_view, merged_careers,
                                player_view, season_line, season_view, slug)
from tests.test_analytics_view import bench, game, line, scores


def rec(season, team='Alpha', name='Star', gp=70, ppg=20.0, rpg=5.0, apg=4.0, po=None, awards=(), champion=False, **extra):
    out = {'stagione': season, 'squadra': team, 'nome': name, 'ruolo': 'SG', 'eta': 20 + season, 'ovr': 80, 'potenziale': 85,
           'is_champion': champion, 'gp': gp, 'gp_po': (po or {}).get('gp', 0),
           'stats_rs': {'ppg': ppg, 'rpg': rpg, 'apg': apg, 'spg': 1.0, 'bpg': 0.5, 'fg_pct': 47.0, 'three_pct': 36.0,
                        'ft_pct': 80.0},
           'stats_po': ({'ppg': po['ppg'], 'rpg': 4.0, 'apg': 3.0, 'spg': 1.0, 'bpg': 0.2, 'fg_pct': 44.0,
                         'three_pct': 33.0, 'ft_pct': 75.0} if po else None),
           'premi': list(awards)}
    out.update(extra)
    return out


def star_games():
    star = dict(pts=20, fgm=8, fga=16, tpm=2, tpa=5, ftm=2, fta=2, to=4, ast=6, reb=7)
    return scores(
        game('g1', 1, '2027-10-23', 'Alpha', 'B', [line('Star', **star)] + bench('Alpha'), [line('Opp')] + bench('B')),
        game('g2', 2, '2027-10-24', 'B', 'Alpha', [line('Opp')] + bench('B'), [line('Star', **star)] + bench('Alpha')))


class SeasonLineTests(unittest.TestCase):
    def test_stat_keys_match_player_stats(self):
        full = archive_lines(star_games())['Star']
        self.assertEqual(set(STAT_KEYS), set(player_stats(full)))

    def test_old_record_line(self):
        ln = season_line(rec(3, gp=70, ppg=20.0), 'rs', 2004)
        self.assertEqual((ln['season'], ln['year'], ln['team'], ln['teams'], ln['gp']), (3, 2004, 'Alpha', ['Alpha'], 70))
        self.assertEqual(ln['s']['pts_pg'], 20.0)
        self.assertEqual(ln['s']['pts_tot'], 1400)
        self.assertEqual((ln['s']['fg_pct'], ln['s']['tp_pct'], ln['s']['ft_pct']), (47.0, 36.0, 80.0))
        self.assertIsNone(ln['s']['ts_pct'])
        self.assertIsNone(ln['s']['mpg'])
        self.assertTrue(ln['est'])
        self.assertFalse(ln['full'])

    def test_totals_format_line(self):
        r = {'stagione': 2, 'squadra': 'Alpha', 'nome': 'Star', 'gp': 50, 'pts': 1000, 'reb': 250, 'ast': 100,
             'stl': 50, 'blk': 25}
        ln = season_line(r, 'rs', 2003)
        self.assertEqual((ln['s']['pts_pg'], ln['s']['reb_pg'], ln['s']['pts_tot']), (20.0, 5.0, 1000))
        self.assertFalse(ln['est'])

    def test_full_line_uses_player_stats(self):
        full = archive_lines(star_games())['Star']
        ln = season_line(rec(5, gp=2, full_rs=full), 'rs', 2006)
        self.assertTrue(ln['full'])
        self.assertFalse(ln['est'])
        self.assertEqual(ln['gp'], 2)
        self.assertEqual(ln['s']['pts_tot'], 40)
        self.assertIsNotNone(ln['s']['ts_pct'])
        self.assertEqual(ln['s']['per'], full['per'])

    def test_playoff_line_and_none_without_playoffs(self):
        ln = season_line(rec(4, po={'gp': 6, 'ppg': 25.0}), 'po', 2005)
        self.assertEqual((ln['gp'], ln['s']['pts_pg'], ln['s']['pts_tot']), (6, 25.0, 150))
        self.assertIsNone(season_line(rec(4), 'po', 2005))

    def test_full_playoff_line_uses_player_stats(self):
        full = archive_lines(star_games())['Star']
        ln = season_line(rec(5, po={'gp': 2, 'ppg': 20.0}, full_po=full), 'po', 2006)
        self.assertTrue(ln['full'])
        self.assertEqual((ln['gp'], ln['s']['pts_tot']), (2, 40))
        self.assertIsNotNone(ln['s']['ts_pct'])
        self.assertIsNotNone(ln['s']['usg_pct'])
        self.assertEqual(ln['s']['per'], full['per'])

    def test_gp_zero_line(self):
        ln = season_line(rec(4, gp=0), 'rs', 2005)
        self.assertEqual(ln['gp'], 0)
        self.assertIsNone(ln['s']['pts_pg'])
        self.assertIsNone(ln['s']['pts_tot'])
        self.assertIsNone(ln['s']['fg_pct'])

    def test_line_carries_awards_and_title(self):
        ln = season_line(rec(4, awards=['MVP'], champion=True), 'rs', 2005)
        self.assertEqual(ln['awards'], ['MVP'])
        self.assertTrue(ln['champion'])
        self.assertEqual((ln['age'], ln['ovr'], ln['pot'], ln['pos']), (24, 80, 85, 'SG'))


class CurrentSeasonTests(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(slug('Zane Castellane'), 'zane-castellane')

    def test_current_records_from_live_players(self):
        players = [{'name': 'Star', 'team': 'Alpha', 'pos': 'SG', 'age': 25, 'ovr': 89, 'pot': 88},
                   {'name': 'Rookie', 'team': 'Alpha', 'pos': 'C', 'age': 19, 'ovr': 60, 'pot': 80}]
        cur = current_records(players, archive_lines(star_games()), 9)
        self.assertEqual(cur['star']['stagione'], 9)
        self.assertEqual(cur['star']['gp'], 2)
        self.assertIn('full_rs', cur['star'])
        self.assertEqual(cur['rookie']['gp'], 0)
        self.assertNotIn('full_rs', cur['rookie'])
        self.assertEqual(season_line(cur['star'], 'rs', 2010)['s']['pts_pg'], 20.0)

    def test_current_records_carry_the_playoffs_being_played(self):
        players = [{'name': 'Star', 'team': 'Alpha', 'pos': 'SG', 'age': 25, 'ovr': 89, 'pot': 88},
                   {'name': 'Rookie', 'team': 'Alpha', 'pos': 'C', 'age': 19, 'ovr': 60, 'pot': 80}]
        cur = current_records(players, {}, 9, po_lines=archive_lines(star_games()))
        self.assertEqual(cur['star']['gp_po'], 2)
        po = season_line(cur['star'], 'po', 2010)
        self.assertEqual(po['s']['pts_pg'], 20.0)
        self.assertIsNotNone(po['s']['ts_pct'])
        self.assertIsNone(season_line(cur['rookie'], 'po', 2010))

    def test_free_agent_takes_his_last_box_score_team(self):
        players = [{'name': 'Star', 'team': None, 'pos': 'SG', 'age': 25, 'ovr': 89, 'pot': 88}]
        cur = current_records(players, archive_lines(star_games()), 9)
        self.assertEqual(cur['star']['squadra'], 'Alpha')

    def test_merge_adds_current_season(self):
        careers = {'star': [rec(2), rec(1)]}
        merged = merged_careers(careers, {'star': rec(3), 'rookie': rec(3, name='Rookie')}, 3)
        self.assertEqual([r['stagione'] for r in merged['star']], [1, 2, 3])
        self.assertIn('rookie', merged)
        self.assertEqual(len(careers['star']), 2)

    def test_merge_skips_when_season_archived(self):
        careers = {'star': [rec(1), rec(2)], 'other': [rec(3, name='Other')]}
        merged = merged_careers(careers, {'star': rec(3)}, 3)
        self.assertEqual([r['stagione'] for r in merged['star']], [1, 2])
        self.assertNotIn('rookie', merged)

    def test_merge_skips_a_season_with_no_games_yet(self):
        # Preseason: the new season is not merged, so the season just played stays the latest one listed.
        careers = {'star': [rec(1), rec(2)]}
        merged = merged_careers(careers, {'star': rec(3, gp=0), 'rookie': rec(3, name='Rookie', gp=0)}, 3)
        self.assertEqual([r['stagione'] for r in merged['star']], [1, 2])
        self.assertNotIn('rookie', merged)
        self.assertEqual(season_view(merged, None, 'rs', {}, 2002, 'Alpha')['season'], 2)

    def test_empty_inputs(self):
        self.assertEqual(merged_careers({}, {}, 1), {})


YEARS = {n: 2001 + n for n in range(1, 30)}


def live(name, status='Active', team='Alpha', ovr=80, **extra):
    out = {'name': name, 'status': status, 'team': team, 'pos': 'SG', 'age': 25, 'ovr': ovr, 'pot': 85,
           'salary': 20.0, 'years': 2}
    out.update(extra)
    return out


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.careers = {
            'star': [rec(1), rec(2, champion=True, awards=['MVP', 'All-Star Starter']), rec(3, awards=['All-Star'])],
            'old-guy': [rec(1, name='Old Guy', team='Beta', ppg=10.0)],
            'free-guy': [rec(2, name='Free Guy', team='Beta')],
            'gone-guy': [rec(1, name='Gone Guy', team='Gamma')],
        }
        self.live = {'star': live('Star', ovr=90), 'free-guy': live('Free Guy', status='Free agent', team=None),
                     'rookie': live('Rookie', ovr=60)}
        self.retired = {'old-guy', 'star'}

    def view(self, **query):
        return directory_view(self.careers, self.live, self.retired, YEARS, 2002, query)

    def test_directory_status_priority(self):
        rows = {r['slug']: r for r in self.view(status='All')['rows']}
        self.assertEqual(rows['star']['status'], 'Active')
        self.assertEqual(rows['free-guy']['status'], 'Free agent')
        self.assertEqual(rows['old-guy']['status'], 'Retired')
        self.assertEqual(rows['gone-guy']['status'], 'Out of league')
        self.assertEqual(rows['old-guy']['team'], 'Beta')
        self.assertIsNone(rows['old-guy']['ovr'])

    def test_directory_default_is_active_by_ovr(self):
        self.assertEqual([r['slug'] for r in self.view()['rows']], ['star', 'rookie'])

    def test_directory_row_career_numbers(self):
        star = next(r for r in self.view()['rows'] if r['slug'] == 'star')
        self.assertEqual((star['seasons'], star['gp'], star['pts_pg'], star['titles'], star['last_year']),
                         (3, 210, 20.0, 1, 2004))
        self.assertEqual(star['highlights'], ['1× Champion', '1× MVP', '2× All-Star'])

    def test_directory_search_and_paging(self):
        self.assertEqual([r['slug'] for r in self.view(status='All', q='GUY', sort='name', desc=False)['rows']],
                         ['free-guy', 'gone-guy', 'old-guy'])
        with mock.patch.object(database_view, 'CONFIG', mock.Mock(DATABASE=Database(PAGE_SIZE=2))):
            page2 = self.view(status='All', sort='name', desc=False, page=2)
        self.assertEqual((page2['total'], page2['page'], page2['pages']), (5, 2, 3))
        self.assertEqual([r['slug'] for r in page2['rows']], ['old-guy', 'rookie'])

    def test_directory_counts(self):
        v = self.view()
        self.assertEqual(v['counts'], {'Active': 2, 'Free agent': 1, 'Retired': 1, 'Out of league': 1})
        self.assertEqual(v['teams'], ['Alpha'])

    def test_empty_directory(self):
        v = directory_view({}, {}, set(), {}, None, {})
        self.assertEqual((v['rows'], v['total'], v['pages']), ([], 0, 1))


class PlayerViewTests(unittest.TestCase):
    def careers(self):
        return {
            'star': [rec(1, ppg=15.0), rec(2, ppg=25.0, champion=True, awards=['MVP', 'All-Star'],
                                          po={'gp': 10, 'ppg': 28.0}),
                     rec(4, ppg=22.0, awards=['All-Star Starter'])],
            'other': [rec(1, name='Other', ppg=30.0, gp=82), rec(2, name='Other', team='Beta', ppg=30.0, gp=82)],
        }

    def view(self, careers=None, slug_='star'):
        return player_view(slug_, careers or self.careers(), {'star': live('Star', ovr=90)}, set(), YEARS, 2002)

    def test_player_view_career_and_best(self):
        v = self.view()
        self.assertEqual((v['name'], v['status'], v['ovr'], v['season_count']), ('Star', 'Active', 90, 3))
        self.assertEqual(v['last_seasons'], 3)
        self.assertEqual(v['career']['gp'], 210)
        self.assertEqual(v['career']['pts_pg'], 20.7)
        self.assertEqual((v['career']['titles'], v['career']['all_star']), (1, 2))
        self.assertEqual(v['career']['awards'], {'MVP': 1, 'All-Star': 2})
        self.assertEqual((v['best']['year'], v['best']['pts_pg'], v['best']['awards']), (2003, 25.0, ['MVP', 'All-Star']))
        self.assertEqual([ln['year'] for ln in v['rs']], [2002, 2003, 2005])
        self.assertEqual([ln['year'] for ln in v['po']], [2003])
        self.assertEqual(v['career_po']['gp'], 10)
        self.assertEqual(v['titles'], [{'year': 2003, 'team': 'Alpha'}])
        self.assertEqual(v['awards'][0], {'year': 2003, 'award': 'MVP', 'team': 'Alpha'})
        self.assertEqual(v['progression'][1]['pts_pg'], 25.0)
        self.assertTrue(v['progression'][1]['champion'])

    def test_player_view_current_season(self):
        self.assertEqual(self.view()['current']['year'], 2005)
        retired = player_view('other', self.careers(), {}, {'other'}, YEARS, 2002)
        self.assertIsNone(retired['current'])
        self.assertEqual((retired['status'], retired['retired_year']), ('Retired', 2003))

    def test_player_view_missing_years(self):
        self.assertEqual(self.view()['missing_years'], [2004])

    def test_player_view_duplicate_season_rows(self):
        careers = self.careers()
        careers['star'].append(rec(4, team='Beta', ppg=5.0, gp=10))
        v = self.view(careers)
        self.assertEqual([(ln['year'], ln['team']) for ln in v['rs']],
                         [(2002, 'Alpha'), (2003, 'Alpha'), (2005, 'Alpha'), (2005, 'Beta')])
        self.assertEqual(v['season_count'], 3)

    def test_player_view_ranks_league_and_franchise(self):
        with mock.patch.object(database_view, 'CONFIG', mock.Mock(DATABASE=Database(RANK_MIN_GP=100))):
            ranks = self.view()['ranks']
        league = {r['stat']: r['rank'] for r in ranks['league']}
        self.assertEqual(league['pts_tot'], 2)
        self.assertEqual(league['gp'], 1)
        self.assertEqual(league['pts_pg'], 2)
        franchise = {(r['team'], r['stat']): r['rank'] for r in ranks['franchise']}
        self.assertEqual(franchise[('Alpha', 'pts_tot')], 1)

    def test_player_view_unknown_slug_none(self):
        self.assertIsNone(self.view(slug_='nobody'))

    def test_career_line_full_seasons_rebuild_advanced(self):
        full = archive_lines(star_games())['Star']
        c = career_line([rec(1, gp=2, full_rs=full), rec(2, gp=2, full_rs=full)], 'rs')
        self.assertTrue(c['full'])
        self.assertEqual((c['gp'], c['s']['pts_tot'], c['s']['pts_pg']), (4, 80, 20.0))
        self.assertIsNotNone(c['s']['ts_pct'])

    def test_career_line_full_line_archived_before_new_counters(self):
        full = archive_lines(star_games())['Star']
        old = {k: v for k, v in full.items() if k != 'xgp' and k not in ('oreb', 'dreb', 'clutch_pts', 'tm_oreb')}
        c = career_line([rec(1, gp=2, full_rs=old), rec(2, gp=2, full_rs=full)], 'rs')
        self.assertTrue(c['full'])
        self.assertEqual((c['gp'], c['s']['pts_tot']), (4, 80))
        self.assertIsNone(c['s']['oreb_tot'])      # older season has no counters: never half counted

    def test_career_line_playoffs_reads_full_po(self):
        full = archive_lines(star_games())['Star']
        c = career_line([rec(1, gp=70, po={'gp': 2, 'ppg': 1.0}, full_po=full)], 'po')
        self.assertTrue(c['full'])
        self.assertEqual((c['gp'], c['s']['pts_tot']), (2, 40))

    def test_career_line_mixed_seasons(self):
        full = archive_lines(star_games())['Star']
        c = career_line([rec(1, gp=10, ppg=10.0), rec(2, gp=2, full_rs=full)], 'rs')
        self.assertFalse(c['full'])
        self.assertTrue(c['est'])
        self.assertEqual((c['gp'], c['s']['pts_tot']), (12, 140))
        self.assertIsNone(c['s']['ts_pct'])
        self.assertIsNone(c['s']['mpg'])


def league():
    full = archive_lines(star_games())['Star']
    return {
        'star': [rec(1, ppg=20.0, eta=22, rpg=11.0), rec(2, ppg=26.0, rpg=10.0, eta=23, champion=True, awards=['All-Star Starter'],
                                                        po={'gp': 12, 'ppg': 30.0}),
                 rec(3, gp=2, full_rs=full)],
        'big': [rec(1, name='Big', team='Beta', ppg=25.0, rpg=12.0, eta=22), rec(2, name='Big', team='Beta', ppg=12.0, eta=23)],
        'bench': [rec(2, name='Bench', team='Alpha', ppg=2.0, gp=10, eta=22)],
    }


class SeasonViewTests(unittest.TestCase):
    def test_season_view_rows_leaders_champion(self):
        v = season_view(league(), 2, 'rs', YEARS, 2002, 'Alpha')
        self.assertEqual((v['season'], v['year'], v['kind'], v['champion'], v['full']), (2, 2003, 'rs', 'Alpha', False))
        self.assertEqual(sorted(r['slug'] for r in v['rows']), ['bench', 'big', 'star'])
        self.assertEqual([x['name'] for x in v['leaders']['pts_pg']], ['Star', 'Big'])   # Bench under half the games
        self.assertEqual(v['leaders']['pts_pg'][0]['value'], 26.0)

    def test_season_view_leaders_ignore_a_merged_name_outlier(self):
        """Two players saved under one name can show ~2x the games; one such row must not hide the real leaders."""
        careers = league()
        careers['dup'] = [rec(2, name='Dup', team='Gamma', gp=145, ppg=1.0)]
        v = season_view(careers, 2, 'rs', YEARS, 2002, None)
        self.assertEqual([x['name'] for x in v['leaders']['pts_pg']], ['Star', 'Big', 'Dup'])

    def test_season_view_lists_seasons_with_full_flag(self):
        v = season_view(league(), None, 'rs', YEARS, 2002, None)
        self.assertEqual(v['season'], 3)
        self.assertTrue(v['full'])
        self.assertEqual(v['seasons'], [{'season': 3, 'year': 2004, 'full': True}, {'season': 2, 'year': 2003, 'full': False},
                                        {'season': 1, 'year': 2002, 'full': False}])
        self.assertTrue(v['rows'][0]['qualified'])
        self.assertIsNone(season_view(league(), 2, 'rs', YEARS, 2002, None)['rows'][0]['qualified'])

    def test_season_view_playoffs(self):
        v = season_view(league(), 2, 'po', YEARS, 2002, None)
        self.assertEqual([r['slug'] for r in v['rows']], ['star'])

    def test_season_view_empty(self):
        v = season_view({}, None, 'rs', {}, None, None)
        self.assertEqual((v['rows'], v['seasons'], v['season']), ([], [], None))


class FinderTests(unittest.TestCase):
    def find(self, **query):
        return finder_view(league(), query, {'star': live('Star')}, {'big'}, YEARS, 2002, 'Alpha')

    def test_finder_seasons_age_and_conditions(self):
        v = self.find(mode='seasons', age_min=22, age_max=22, min_gp=50, rank_by='pts_pg')
        self.assertEqual([(r['name'], r['line']['year']) for r in v['rows']], [('Big', 2002), ('Star', 2002)])
        v = self.find(conditions=[{'stat': 'pts_pg', 'op': '>=', 'value': 25}, {'stat': 'reb_pg', 'op': '>=', 'value': 10}],
                      rank_by='pts_pg')
        self.assertEqual([(r['name'], r['line']['year']) for r in v['rows']], [('Star', 2003), ('Big', 2002)])
        self.assertIsNone(v['note'])
        self.assertTrue(v['desc'])
        self.assertFalse(self.find(desc=False)['desc'])

    def test_finder_careers_sum(self):
        v = self.find(mode='careers', rank_by='pts_tot')
        star = next(r for r in v['rows'] if r['slug'] == 'star')
        self.assertEqual((star['seasons'], star['career']['gp'], star['titles'], star['all_star']), (3, 142, 1, 1))
        self.assertEqual(star['career']['s']['pts_tot'], 1400 + 1820 + 40)
        self.assertEqual((star['first_year'], star['last_year']), (2002, 2004))
        self.assertEqual(self.find(mode='careers', rank_by='all_star')['rows'][0]['slug'], 'star')

    def test_finder_full_only_stat_note(self):
        v = self.find(conditions=[{'stat': 'ts_pct', 'op': '<=', 'value': 99}], rank_by='pts_pg')
        self.assertEqual([r['line']['year'] for r in v['rows']], [2004])
        self.assertEqual(v['full_from'], 2004)
        self.assertEqual(v['note'], 'Only seasons from 2004 have this stat.')
        po = self.find(kind='po', rank_by='ts_pct')
        self.assertEqual(po['note'], 'No season in this save has this stat yet.')

    def test_finder_user_team_preset(self):
        v = self.find(team='__user__', rank_by='pts_pg')
        self.assertEqual({r['line']['team'] for r in v['rows']}, {'Alpha'})

    def test_finder_status_award_champion(self):
        self.assertEqual({r['slug'] for r in self.find(status='Retired')['rows']}, {'big'})
        self.assertEqual([r['line']['year'] for r in self.find(award='All-Star')['rows']], [2003])
        self.assertEqual([r['line']['year'] for r in self.find(champion=True)['rows']], [2003])

    def test_finder_condition_cap(self):
        conds = [{'stat': 'pts_pg', 'op': '>=', 'value': 0}] * 4 + [{'stat': 'pts_pg', 'op': '>=', 'value': 1000}]
        self.assertEqual(len(self.find(conditions=conds)['rows']), 6)

    def test_finder_ignores_bad_conditions(self):
        conds = [{'stat': 'nope', 'op': '>=', 'value': 1}, {'stat': 'pts_pg', 'op': '>=', 'value': 'abc'}]
        self.assertEqual(len(self.find(conditions=conds)['rows']), 6)

    def test_presets_are_valid_queries(self):
        for preset in Database().PRESETS:
            self.assertIn('rows', self.find(**preset['query']), preset['id'])
        self.assertEqual([p['id'] for p in Database().PRESETS],
                         ['best-22', '25-10', '50-40-90', 'best-user-team', 'most-all-star'])


if __name__ == '__main__':
    unittest.main()
