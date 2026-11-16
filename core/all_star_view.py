"""All-Star page view: one season's weekend (played, upcoming or from old history) for the page.

Pure functions over plain dicts (the weekend snapshot of core/all_star_weekend.py, league_history.json `premi`),
no Flask, no tournament objects.
"""
import copy

LINE_KEYS = ('name', 'team', 'pos', 'age', 'ovr', 'gp', 'ppg', 'rpg', 'apg', 'tpm', 'tp_pct', 'r3', 'dunk', 'athl')
CONFERENCES = ('east', 'west')

EVENTS = (  # id, night, title — in the order the weekend plays them
    ('rookie_challenge', 'Friday', 'Rookie Challenge'),
    ('selections', 'Friday', 'All-Star Selections'),
    ('three_point', 'Saturday', '3-Point Contest'),
    ('dunk', 'Saturday', 'Dunk Contest'),
    ('game', 'Sunday', 'All-Star Game'),
)
YOU_COPY = (('three_point', '3-Point Contest'), ('dunk', 'Dunk Contest'))


def season_label(year):
    """"2027-28" from 2027; None without a year."""
    return f"{year}-{(year + 1) % 100:02d}" if year else None


def _name(value):
    """A saved name, or None for "N/A", empty or non-text values."""
    if not value or not isinstance(value, str) or value.strip().upper() == 'N/A':
        return None
    return value


def short_name(name):
    """"K. Smith" from "Kris Smith"; one-word names stay as they are."""
    first, _, rest = (name or '').partition(' ')
    return f"{first[0]}. {rest}" if first and rest else name


def _ordinal(n):
    suffix = 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"


def legacy_weekend(premi, season):
    """A weekend from an old history entry (names only, `legacy` True); None when the entry records nothing."""
    premi = premi or {}

    def names_line(nm):
        return {k: (nm if k == 'name' else None) for k in LINE_KEYS}

    selections = {}
    for conf in CONFERENCES:
        selections[conf] = {
            'starters': [names_line(n) for n in (premi.get('all_star_starters') or {}).get(conf) or [] if _name(n)],
            'reserves': [names_line(n) for n in (premi.get('all_star_reserves') or {}).get(conf) or [] if _name(n)],
            'left_out': [],
        }
    if not any(selections[c]['starters'] or selections[c]['reserves'] for c in CONFERENCES):
        selections = None

    def contest(key):
        winner = _name(premi.get(key))
        return {'round1': [], 'final': [], 'winner': winner} if winner else None

    mvp = _name(premi.get('all_star_mvp'))
    out = {'season': season, 'host': None, 'legacy': True, 'selections': selections, 'rookie_challenge': None,
           'three_point': contest('three_point_contest'), 'dunk': contest('dunk_contest'),
           'game': {'sides': [], 'winner': None, 'mvp': {'name': mvp}} if mvp else None}
    if not any(out[k] for k in ('selections', 'three_point', 'dunk', 'game')):
        return None
    return out


def _flag(lines, user_team):
    for x in lines or []:
        x['is_user'] = bool(user_team) and x.get('team') == user_team


def _flag_game(game, user_team):
    if not game:
        return
    for side in game.get('sides') or []:
        _flag(side.get('lines'), user_team)
    if game.get('mvp'):
        _flag([game['mvp']], user_team)


def _all_stars(selections):
    return [x for conf in CONFERENCES for part in ('starters', 'reserves')
            for x in ((selections or {}).get(conf) or {}).get(part) or []]


def _score(game):
    sides = (game or {}).get('sides') or []
    if len(sides) != 2 or not game.get('winner'):
        return None
    win = next((s for s in sides if s['label'] == game['winner']), None)
    lose = next((s for s in sides if s is not win), None)
    if not win or not lose:
        return None
    return f"{win['label']} {win['score']}-{lose['score']}"


def _game_summary(game):
    if not game:
        return None
    score = _score(game)
    if score:
        return score
    mvp = _name((game.get('mvp') or {}).get('name'))
    return f"MVP: {short_name(mvp)}" if mvp else None


def _mvp_fact(mvp, season, past_mvps):
    """"<Name>'s 2nd All-Star MVP", else "First All-Star MVP for the <team>", else None."""
    if not mvp or not mvp.get('name'):
        return None
    past = [m for m in past_mvps or [] if (m.get('season') or 0) < season]
    wins = sum(1 for m in past if m.get('name') == mvp['name'])
    if wins:
        return f"{mvp['name']}'s {_ordinal(wins + 1)} All-Star MVP"
    team = mvp.get('team')
    if team and team != 'FA' and not any(m.get('team') == team for m in past):
        return f"First All-Star MVP for the {team}"
    return None


def _events(w, user_count):
    rookie_game = (w.get('rookie_challenge') or {}).get('game')
    all_stars = _all_stars(w.get('selections'))
    selections = None
    if all_stars:
        selections = f"{len(all_stars)} All-Stars" + (f" · {user_count} yours" if user_count else '')

    def contest(key):
        winner = (w.get(key) or {}).get('winner')
        return f"Winner: {short_name(winner)}" if winner else None

    summaries = {'rookie_challenge': _score(rookie_game), 'selections': selections,
                 'three_point': contest('three_point'), 'dunk': contest('dunk'),
                 'game': _game_summary(w.get('game'))}
    return [{'id': eid, 'night': night, 'title': title, 'summary': summaries[eid],
             'recorded': summaries[eid] is not None} for eid, night, title in EVENTS]


def _you(w, user_team):
    if not user_team:
        return None
    count = sum(1 for x in _all_stars(w.get('selections')) if x['is_user'])
    entries = [f"{x['name']} in the {title}" for key, title in YOU_COPY
               for x in (w.get(key) or {}).get('round1') or [] if x['is_user']]
    rc = w.get('rookie_challenge') or {}
    entries += [f"{x['name']} in the Rookie Challenge"
                for x in (rc.get('rookies') or []) + (rc.get('sophomores') or []) if x['is_user']]
    if not count and not entries:
        return None
    return {'team': user_team, 'all_stars': count, 'entries': entries}


def all_star_view(*, weekend, season, label, status, user_team, seasons, past_mvps, break_info):
    """The page payload for one season; `weekend` is a snapshot, a legacy_weekend or None."""
    w = copy.deepcopy(weekend) or {}
    for conf in CONFERENCES:
        for lines in ((w.get('selections') or {}).get(conf) or {}).values():
            _flag(lines, user_team)
    rc = w.get('rookie_challenge')
    if rc:
        _flag(rc.get('rookies'), user_team)
        _flag(rc.get('sophomores'), user_team)
        _flag_game(rc.get('game'), user_team)
        if (rc.get('game') or {}).get('mvp'):
            rc['game']['mvp']['fact'] = None
    for key in ('three_point', 'dunk'):
        if w.get(key):
            _flag(w[key].get('round1'), user_team)
            _flag(w[key].get('final'), user_team)
    game = w.get('game')
    _flag_game(game, user_team)
    if game and game.get('mvp'):
        game['mvp']['fact'] = _mvp_fact(game['mvp'], season, past_mvps)

    you = _you(w, user_team) if w else None
    newest = sorted({s['season']: s for s in seasons or []}.values(), key=lambda s: -s['season'])
    is_current = status == 'upcoming' or bool(newest and newest[0]['season'] == season)
    return {
        'season': season, 'label': label, 'host': w.get('host'), 'status': status, 'is_current': is_current,
        'legacy': bool(w.get('legacy')),
        'break': break_info if is_current else None, 'you': you,
        'events': _events(w, you['all_stars'] if you else 0),
        'selections': w.get('selections'), 'rookie_challenge': rc, 'three_point': w.get('three_point'),
        'dunk': w.get('dunk'), 'game': game,
        'seasons': [{'season': s['season'], 'label': s['label']} for s in newest],
    }
