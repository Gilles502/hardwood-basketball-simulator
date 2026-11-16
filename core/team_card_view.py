# File: core/team_card_view.py
"""Team card: the quick look any team name opens (record, seed, payroll against the tax, rotation, picks, last seasons).

Pure function over plain dicts built by server.py, no Flask, no tournament objects.
"""
from core.history_view import playoff_label

NO_PROTECTION = (None, '', 'None', 'Unprotected')
PLAYOFF_RESULTS = ('Playoffs', 'Lost Finals', 'Champions')


def _seed(league, name):
    """The team's place in its conference by record (wins, then fewer losses, then name); None if unknown."""
    me = next((t for t in league if t['name'] == name), None)
    if me is None:
        return None
    conf = sorted((t for t in league if t.get('conference') == me.get('conference')),
                  key=lambda t: (-t['wins'], t['losses'], t['name']))
    return 1 + [t['name'] for t in conf].index(name)


def _picks(future_picks):
    out = []
    for year in future_picks or []:
        for p in year.get('owned', []):
            out.append({'year': year['year'], 'round': p['round'], 'kind': 'own' if p.get('is_own') else 'via',
                        'team': None if p.get('is_own') else p.get('original_owner'),
                        'protection': None if p.get('protection') in NO_PROTECTION else p['protection']})
        for p in year.get('traded', []):
            out.append({'year': year['year'], 'round': p['round'], 'kind': 'to', 'team': p.get('current_owner'),
                        'protection': None if p.get('protection') in NO_PROTECTION else p['protection']})
    return out


def _seasons(history, shown):
    rows = sorted((h for h in history or [] if isinstance(h, dict)), key=lambda h: h.get('season') or 0)[-shown:]
    out = []
    for h in rows:
        result = 'Champions' if h.get('is_champion') else playoff_label(h.get('playoff_round'))
        out.append({'year': h.get('year'), 'wins': h.get('wins', 0), 'losses': h.get('losses', 0),
                    'seed': h.get('conf_seed'), 'champion': result == 'Champions', 'result': result,
                    'playoffs': result in PLAYOFF_RESULTS})
    return out


def team_card_view(team, league, lines, roster_limit, rotation_size, seasons_shown, user_team):
    """team: {name, conference, wins, losses, payroll, roster: [player dicts], future_picks, standings_history};
    league: every team's {name, conference, wins, losses}; lines: this season's CBA lines (luxury_tax may be None)."""
    roster = sorted(team.get('roster') or [], key=lambda p: (-(p.get('ovr') or 0), p['name']))
    tax = (lines or {}).get('luxury_tax')
    payroll = round(team.get('payroll') or 0.0, 2)
    return {
        'name': team['name'], 'conference': team.get('conference'), 'wins': team.get('wins', 0),
        'losses': team.get('losses', 0), 'seed': _seed(league or [], team['name']),
        'is_user': bool(user_team) and team['name'] == user_team,
        'payroll': payroll, 'tax_line': tax, 'over_tax': None if tax is None else round(payroll - tax, 2),
        'roster_count': len(roster), 'roster_limit': roster_limit,
        'roster': [dict(p, rotation=i < rotation_size) for i, p in enumerate(roster)],
        'picks': _picks(team.get('future_picks')),
        'seasons': _seasons(team.get('standings_history'), seasons_shown),
    }
