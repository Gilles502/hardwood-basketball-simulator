"""All-Star view (core/all_star_view.py): one season's weekend, played, upcoming or from old history."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.all_star_view import all_star_view, legacy_weekend


def line(name, team='Alpha', **kw):
    out = {'name': name, 'team': team, 'pos': 'SG', 'age': 25, 'ovr': 85, 'gp': 50, 'ppg': 20.0, 'rpg': 5.0,
           'apg': 4.0, 'tpm': 2.0, 'tp_pct': 38.0, 'r3': 80, 'dunk': 70, 'athl': 75.0}
    out.update(kw)
    return out


def box(name, team, pts):
    return {'name': name, 'team': team, 'pts': pts, 'reb': 5, 'ast': 4, 'tpm': 2}


def conference(prefix, user_count):
    """5 starters and 7 reserves; the first `user_count` play for Alpha (the user's team)."""
    players = [line(f'{prefix} Player{i}', 'Alpha' if i < user_count else f'{prefix}Team{i}') for i in range(12)]
    return {'starters': players[:5], 'reserves': players[5:], 'left_out': [line(f'{prefix} Snub', 'Alpha')]}


def snapshot(mvp_name='Quincy Ashgrove', mvp_team='Minnesota Blizzard'):
    return {
        'season': 3, 'host': 'Atlanta',
        'selections': {'east': conference('E', 2), 'west': conference('W', 0)},
        'rookie_challenge': {
            'rookies': [line('Rook One', 'Alpha'), line('Rook Two', 'Beta')],
            'sophomores': [line('Soph One', 'Gamma')],
            'game': {'sides': [{'label': 'Rookies', 'score': 121, 'lines': [box('Rook One', 'Alpha', 30)]},
                               {'label': 'Sophomores', 'score': 128, 'lines': [box('Soph One', 'Gamma', 40)]}],
                     'winner': 'Sophomores',
                     'mvp': {'name': 'Soph One', 'team': 'Gamma', 'label': 'Sophomores', 'pts': 40, 'reb': 5,
                             'ast': 4, 'tpm': 2}}},
        'three_point': {'round1': [{'name': 'Ezra Hollins', 'team': 'Beta', 'tp_pct': 41.0, 'score': 20,
                                    'finalist': True},
                                   {'name': 'Sharp Shooter', 'team': 'Alpha', 'tp_pct': 40.0, 'score': 15,
                                    'finalist': False}],
                        'final': [{'name': 'Ezra Hollins', 'team': 'Beta', 'score': 22}],
                        'winner': 'Ezra Hollins'},
        'dunk': {'round1': [{'name': 'Benedikt Iverley', 'team': 'Alpha', 'total': 140, 'finalist': True,
                             'dunks': [{'name': 'Windmill', 'score': 48}]}],
                 'final': [{'name': 'Benedikt Iverley', 'team': 'Alpha', 'dunk': 'Windmill', 'score': 50}],
                 'winner': 'Benedikt Iverley'},
        'game': {'sides': [{'label': 'East', 'score': 148, 'lines': [box('E Player0', 'Alpha', 30)]},
                           {'label': 'West', 'score': 141, 'lines': [box(mvp_name, mvp_team, 35)]}],
                 'winner': 'East',
                 'mvp': {'name': mvp_name, 'team': mvp_team, 'label': 'East', 'pts': 35, 'reb': 8, 'ast': 4,
                         'tpm': 1}},
    }


SEASONS = [{'season': 1, 'label': '2002-03'}, {'season': 3, 'label': '2004-05'}, {'season': 2, 'label': '2003-04'}]


_PLAYED = object()


def view(weekend=_PLAYED, **kw):
    args = dict(weekend=snapshot() if weekend is _PLAYED else weekend, season=3, label='2004-05',
                status='played', user_team='Alpha', seasons=SEASONS, past_mvps=[], break_info=None)
    args.update(kw)
    return all_star_view(**args)


class PlayedWeekendTests(unittest.TestCase):
    def test_played_weekend_events_and_summaries(self):
        v = view()
        self.assertEqual((v['season'], v['label'], v['host'], v['status']), (3, '2004-05', 'Atlanta', 'played'))
        self.assertEqual([(e['id'], e['night']) for e in v['events']],
                         [('rookie_challenge', 'Friday'), ('selections', 'Friday'), ('three_point', 'Saturday'),
                          ('dunk', 'Saturday'), ('game', 'Sunday')])
        self.assertEqual([e['summary'] for e in v['events']],
                         ['Sophomores 128-121', '24 All-Stars · 2 yours', 'Winner: E. Hollins',
                          'Winner: B. Iverley', 'East 148-141'])
        self.assertTrue(all(e['recorded'] for e in v['events']))
        self.assertTrue(all(e['title'] for e in v['events']))
        no_user = view(user_team='Nobody')
        self.assertEqual(no_user['events'][1]['summary'], '24 All-Stars')

    def test_user_flags_and_you_strip(self):
        v = view()
        east = v['selections']['east']
        self.assertEqual([p['is_user'] for p in east['starters']], [True, True, False, False, False])
        self.assertTrue(east['left_out'][0]['is_user'])
        self.assertEqual([p['is_user'] for p in v['rookie_challenge']['rookies']], [True, False])
        self.assertTrue(v['rookie_challenge']['game']['sides'][0]['lines'][0]['is_user'])
        self.assertEqual([p['is_user'] for p in v['three_point']['round1']], [False, True])
        self.assertTrue(v['dunk']['final'][0]['is_user'])
        self.assertFalse(v['game']['mvp']['is_user'])
        self.assertEqual(v['you'], {'team': 'Alpha', 'all_stars': 2, 'entries': [
            'Sharp Shooter in the 3-Point Contest', 'Benedikt Iverley in the Dunk Contest',
            'Rook One in the Rookie Challenge']})
        # the input snapshot is left alone
        snap = snapshot()
        view(weekend=snap)
        self.assertNotIn('is_user', snap['selections']['east']['starters'][0])

    def test_spectator_has_no_you(self):
        v = view(user_team=None)
        self.assertIsNone(v['you'])
        self.assertFalse(any(p['is_user'] for p in v['selections']['east']['starters']))
        self.assertEqual(v['events'][1]['summary'], '24 All-Stars')
        self.assertIsNone(view(user_team='Nobody')['you'])

    def test_upcoming_has_break_and_no_results(self):
        v = view(weekend=None, status='upcoming', break_info={'day': 110, 'date': '2005-02-18'})
        self.assertEqual(v['break'], {'day': 110, 'date': '2005-02-18'})
        self.assertTrue(v['is_current'])
        self.assertIsNone(v['host'])
        self.assertIsNone(v['you'])
        for key in ('selections', 'rookie_challenge', 'three_point', 'dunk', 'game'):
            self.assertIsNone(v[key])
        self.assertEqual([e['id'] for e in v['events']],
                         ['rookie_challenge', 'selections', 'three_point', 'dunk', 'game'])
        self.assertFalse(any(e['recorded'] for e in v['events']))
        self.assertTrue(all(e['summary'] is None for e in v['events']))
        self.assertFalse(view(season=2, label='2003-04')['is_current'])

    def test_mvp_fact_second_and_first_for_team(self):
        past = [{'season': 1, 'name': 'Quincy Ashgrove', 'team': 'Minnesota Blizzard'},
                {'season': 2, 'name': 'Corwin Draycott', 'team': 'Los Angeles Legends'}]
        self.assertEqual(view(past_mvps=past)['game']['mvp']['fact'], "Quincy Ashgrove's 2nd All-Star MVP")
        third = past + [{'season': 2, 'name': 'Quincy Ashgrove', 'team': 'Minnesota Blizzard'}]
        self.assertEqual(view(past_mvps=third)['game']['mvp']['fact'], "Quincy Ashgrove's 3rd All-Star MVP")
        fresh = view(weekend=snapshot('Benedikt Iverley', 'Toronto Northmen'), past_mvps=past)
        self.assertEqual(fresh['game']['mvp']['fact'], 'First All-Star MVP for the Toronto Northmen')
        same_team = view(weekend=snapshot('Caspian Pembrook', 'Minnesota Blizzard'), past_mvps=past)
        self.assertIsNone(same_team['game']['mvp']['fact'])
        # later seasons do not count
        later = [{'season': 5, 'name': 'Quincy Ashgrove', 'team': 'Minnesota Blizzard'}]
        self.assertEqual(view(past_mvps=later)['game']['mvp']['fact'],
                         'First All-Star MVP for the Minnesota Blizzard')
        self.assertIsNone(view()['rookie_challenge']['game']['mvp']['fact'])

    def test_winner_matching_no_side_has_no_score(self):
        snap = snapshot()
        snap['game']['winner'] = 'Nobody'
        self.assertEqual(view(weekend=snap)['events'][4]['summary'], 'MVP: Q. Ashgrove')

    def test_seasons_newest_first(self):
        self.assertEqual([s['season'] for s in view()['seasons']], [3, 2, 1])
        self.assertEqual(view()['seasons'][0], {'season': 3, 'label': '2004-05'})


PREMI_2024 = {
    'all_star_starters': {'east': ['Yusuf Grisby', 'Dorian Vantreese'], 'west': ['Corwin Draycott']},
    'all_star_reserves': {'east': ['Ulric Dunmore'], 'west': ['Xavi Zellner', 'Quincy Ashgrove']},
    'all_star_mvp': 'Quincy Ashgrove', 'three_point_contest': 'Pax Thackery', 'dunk_contest': 'Benedikt Iverley',
}
PREMI_2025 = {'all_star_starters': {'east': [], 'west': []}, 'all_star_reserves': {'east': [], 'west': []},
              'all_star_mvp': 'N/A', 'three_point_contest': None, 'dunk_contest': None}


class LegacyTests(unittest.TestCase):
    def test_legacy_names_only_entry(self):
        w = legacy_weekend(PREMI_2024, 1)
        self.assertEqual(w['season'], 1)
        self.assertIsNone(w['host'])
        starter = w['selections']['east']['starters'][0]
        self.assertEqual(starter['name'], 'Yusuf Grisby')
        self.assertTrue(all(starter[k] is None for k in starter if k != 'name'))
        self.assertEqual([p['name'] for p in w['selections']['west']['reserves']], ['Xavi Zellner', 'Quincy Ashgrove'])
        self.assertEqual(w['three_point'], {'round1': [], 'final': [], 'winner': 'Pax Thackery'})
        self.assertEqual(w['dunk']['winner'], 'Benedikt Iverley')
        self.assertEqual(w['game']['mvp'], {'name': 'Quincy Ashgrove'})
        self.assertIsNone(w['rookie_challenge'])

        v = all_star_view(weekend=w, season=1, label='2002-03', status='played', user_team='Alpha',
                          seasons=SEASONS, past_mvps=[], break_info=None)
        self.assertEqual([(e['id'], e['recorded']) for e in v['events']],
                         [('rookie_challenge', False), ('selections', True), ('three_point', True), ('dunk', True),
                          ('game', True)])
        self.assertEqual([e['summary'] for e in v['events']],
                         [None, '6 All-Stars', 'Winner: P. Thackery', 'Winner: B. Iverley', 'MVP: Q. Ashgrove'])
        self.assertFalse(v['selections']['east']['starters'][0]['is_user'])
        self.assertIsNone(v['game']['mvp']['fact'])
        self.assertIsNone(v['you'])

    def test_legacy_payload_is_flagged(self):
        # An old save loaded after archiving: the newest season comes from legacy history and is current.
        v = all_star_view(weekend=legacy_weekend(PREMI_2024, 3), season=3, label='2004-05', status='played',
                          user_team='Alpha', seasons=SEASONS, past_mvps=[], break_info=None)
        self.assertTrue(v['is_current'])
        self.assertIs(v['legacy'], True)
        self.assertIs(view()['legacy'], False)
        self.assertIs(view(weekend=None, status='upcoming')['legacy'], False)

    def test_empty_legacy_entry_is_not_recorded(self):
        self.assertIsNone(legacy_weekend(PREMI_2025, 2))
        self.assertIsNone(legacy_weekend({}, 2))
        partial = legacy_weekend(dict(PREMI_2025, dunk_contest='Benedikt Iverley'), 2)
        self.assertIsNone(partial['selections'])
        self.assertIsNone(partial['game'])
        self.assertIsNone(partial['three_point'])
        v = all_star_view(weekend=None, season=2, label='2003-04', status='not_recorded', user_team='Alpha',
                          seasons=SEASONS, past_mvps=[], break_info=None)
        self.assertEqual(v['status'], 'not_recorded')
        self.assertFalse(any(e['recorded'] for e in v['events']))


if __name__ == '__main__':
    unittest.main()
