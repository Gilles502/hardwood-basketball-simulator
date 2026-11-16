"""Team card (core/team_card_view.py): the quick look a team name opens."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.team_card_view import team_card_view


def player(name, ovr, pos='SG', age=25, ppg=10.0, salary=10.0, years=2, injured=False):
    return {'name': name, 'pos': pos, 'age': age, 'ovr': ovr, 'pot': ovr + 2, 'ppg': ppg, 'salary': salary,
            'years': years, 'injured': injured}


def team(name='Alpha', conference='East', wins=50, losses=20, roster=None, **extra):
    out = {'name': name, 'conference': conference, 'wins': wins, 'losses': losses,
           'payroll': sum(p['salary'] for p in roster or []), 'roster': roster or [], 'future_picks': [],
           'standings_history': []}
    out.update(extra)
    return out


LEAGUE = [team('Alpha', 'East', 50, 20), team('Beta', 'East', 55, 15), team('Gamma', 'West', 60, 10),
          team('Delta', 'East', 40, 30)]
LINES = {'luxury_tax': 100.0, 'salary_cap': 80.0}


def card(t, **kw):
    args = dict(league=LEAGUE, lines=LINES, roster_limit=18, rotation_size=2, seasons_shown=3, user_team='Alpha')
    args.update(kw)
    return team_card_view(t, **args)


class TeamCardTests(unittest.TestCase):
    def test_header_record_seed_and_user_team(self):
        c = card(team('Alpha', 'East', 50, 20))
        self.assertEqual((c['name'], c['wins'], c['losses'], c['conference'], c['seed'], c['is_user']),
                         ('Alpha', 50, 20, 'East', 2, True))
        self.assertFalse(card(team('Gamma', 'West', 60, 10))['is_user'])

    def test_payroll_against_the_tax(self):
        roster = [player('A', 90, salary=70.0), player('B', 80, salary=37.5)]
        c = card(team(roster=roster))
        self.assertEqual((c['payroll'], c['tax_line'], c['over_tax']), (107.5, 100.0, 7.5))
        under = card(team(roster=[player('A', 90, salary=60.0)]))
        self.assertEqual(under['over_tax'], -40.0)
        self.assertIsNone(card(team(roster=roster), lines={'luxury_tax': None})['over_tax'])

    def test_roster_sorted_with_rotation_flag(self):
        roster = [player('Low', 70), player('Top', 92, injured=True), player('Mid', 85)]
        c = card(team(roster=roster))
        self.assertEqual([p['name'] for p in c['roster']], ['Top', 'Mid', 'Low'])
        self.assertEqual([p['rotation'] for p in c['roster']], [True, True, False])
        self.assertTrue(c['roster'][0]['injured'])
        self.assertEqual((c['roster_count'], c['roster_limit']), (3, 18))

    def test_picks_owned_and_traded_away(self):
        picks = [{'year': 2028, 'owned': [{'round': 1, 'original_owner': 'Alpha', 'is_own': True, 'protection': 'Unprotected'},
                                          {'round': 2, 'original_owner': 'Memphis Blues', 'is_own': False, 'protection': 'None'}],
                  'traded': [{'round': 1, 'current_owner': 'Boston Minutemen', 'protection': 'Top-10'}]}]
        c = card(team(future_picks=picks))
        self.assertEqual(c['picks'], [
            {'year': 2028, 'round': 1, 'kind': 'own', 'team': None, 'protection': None},
            {'year': 2028, 'round': 2, 'kind': 'via', 'team': 'Memphis Blues', 'protection': None},
            {'year': 2028, 'round': 1, 'kind': 'to', 'team': 'Boston Minutemen', 'protection': 'Top-10'},
        ])

    def test_last_seasons_in_english(self):
        history = [{'season': n, 'year': 2001 + n, 'conf_seed': n, 'wins': 40 + n, 'losses': 42 - n,
                    'is_champion': n == 3, 'playoff_round': 'Campione NBA 🏆' if n == 3 else ('Lottery' if n == 1 else 'Playoffs')}
                   for n in (4, 1, 2, 3)]
        c = card(team(standings_history=history))
        self.assertEqual([s['year'] for s in c['seasons']], [2003, 2004, 2005])
        self.assertEqual([s['result'] for s in c['seasons']], ['Playoffs', 'Champions', 'Playoffs'])
        self.assertEqual([s['champion'] for s in c['seasons']], [False, True, False])
        self.assertEqual(c['seasons'][0], {'year': 2003, 'wins': 42, 'losses': 40, 'seed': 2, 'champion': False,
                                           'result': 'Playoffs', 'playoffs': True})

    def test_lottery_season_is_not_playoffs(self):
        c = card(team(standings_history=[{'season': 1, 'year': 2002, 'conf_seed': 12, 'wins': 20, 'losses': 62,
                                          'is_champion': False, 'playoff_round': 'Lottery'}]))
        self.assertFalse(c['seasons'][0]['playoffs'])

    def test_empty_team(self):
        c = card(team('Nobody', 'East', 0, 0), league=[])
        self.assertEqual((c['roster'], c['picks'], c['seasons'], c['seed']), ([], [], [], None))


if __name__ == '__main__':
    unittest.main()


class TeamCardRouteTests(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        import server
        self.server = server
        self._saved = server.SIMULATION_TOURNAMENT

        def p(name, ovr, pts, gp, salary):
            return SimpleNamespace(nome=name, ruolo='SG', eta=25, ovr=ovr, potenziale=ovr, infortunato=False,
                                   season_stats=SimpleNamespace(punti=pts, partite_giocate=gp),
                                   contract=SimpleNamespace(salario_annuale=salary, anni_rimanenti=2))
        alpha = SimpleNamespace(nome='Alpha', conference='East', vittorie=10, sconfitte=5, payroll=50.0,
                                roster=[p('Star', 90, 200, 10, 30.0), p('Rookie', 60, 0, 0, 1.0)], standings_history=[])
        beta = SimpleNamespace(nome='Beta', conference='East', vittorie=12, sconfitte=3, payroll=40.0, roster=[],
                               standings_history=[])
        server.SIMULATION_TOURNAMENT = SimpleNamespace(
            squadre=[alpha, beta], squadra_giocatore=alpha, season_number=3, starting_year=2002,
            pick_ownership={}, pick_protections={}, luxury_tax_threshold=45.0, salary_cap=40.0)
        self.client = server.app.test_client()

    def tearDown(self):
        self.server.SIMULATION_TOURNAMENT = self._saved

    def test_route_builds_the_card(self):
        c = self.client.get('/api/team-card/Alpha').get_json()
        self.assertEqual((c['seed'], c['is_user'], c['over_tax'], c['roster_count']), (2, True, 5.0, 2))
        self.assertEqual([(p['name'], p['ppg']) for p in c['roster']], [('Star', 20.0), ('Rookie', None)])
        self.assertEqual(len(c['picks']), 0)

    def test_unknown_team_404(self):
        self.assertEqual(self.client.get('/api/team-card/Nobody').status_code, 404)
