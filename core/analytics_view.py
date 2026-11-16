# File: core/analytics_view.py
"""League Analytics views: every number on the page, built from the season's saved box scores.

Pure functions over plain data (no Flask, no tournament objects), so the same box scores always give the same page.
Possessions are estimated as FGA + 0.44*FTA + TOV averaged with the opponent. Box scores saved since 2026-11-15 also
carry offensive/defensive rebounds, assisted makes, shot zones and clutch numbers (EXTRA_STATS); Game Score and PER use
the counted offensive rebounds, and assume CONFIG.ANALYTICS.OREB_SHARE of rebounds are offensive for older games.
"""
from collections import defaultdict

from core.config import CONFIG

LINE_STATS = ('pts', 'reb', 'ast', 'stl', 'blk', 'to', 'pf', 'fgm', 'fga', 'tpm', 'tpa', 'ftm', 'fta')
TEAM_STATS = ('min',) + LINE_STATS
# Counters box scores carry since 2026-11-15 (offensive/defensive rebounds, assisted makes, shot zones, clutch).
# A player's stat from them exists only when every game he played has them (xgp == gp), never half counted.
EXTRA_STATS = ('oreb', 'dreb', 'ast_fgm', 'rim_fga', 'rim_fgm', 'mid_fga', 'mid_fgm', 'clutch_pts', 'clutch_fga',
               'clutch_fgm', 'clutch_min')
EXTRA_TEAM = ('tm_oreb', 'tm_dreb', 'opp_oreb', 'opp_dreb')
# player_stats() keys built from EXTRA_STATS (None without them)
EXTRA_STAT_KEYS = ('oreb_tot', 'oreb_pg', 'dreb_tot', 'dreb_pg', 'orb_pct', 'drb_pct', 'ast_fgm_pct', 'rim_fga_pg',
                   'rim_fg_pct', 'rim_rate', 'mid_fga_pg', 'mid_fg_pct', 'mid_rate', 'clutch_pts_tot', 'clutch_pts_pg',
                   'clutch_fg_pct', 'clutch_min')
# Season sums kept in player_careers.json (`full_rs`): enough for player_stats() to rebuild the whole line.
ARCHIVE_KEYS = (('gp', 'min', 'pm', 'on_poss') + LINE_STATS + ('tm_min', 'tm_fgm', 'tm_fga', 'tm_fta', 'tm_to')
                + ('xgp',) + EXTRA_STATS + EXTRA_TEAM)
PLAYER_PCT_KEYS = ('pts_pg', 'ts_pct', 'usg_pct', 'ast_pct', 'ato', 'reb_pg', 'stl_pg', 'blk_pg', 'gmsc', 'pm_pg')


def _r(value, digits=1):
    return None if value is None else round(value, digits)


def _div(num, den):
    return num / den if den else None


def _pct(num, den):
    return 100.0 * num / den if den else None


def _raw_poss(t):
    return t['fga'] + CONFIG.ANALYTICS.FTA_WEIGHT * t['fta'] + t['to']


def ts_pct(pts, fga, fta):
    return _pct(pts, 2 * (fga + CONFIG.ANALYTICS.FTA_WEIGHT * fta))


def efg_pct(fgm, tpm, fga):
    return _pct(fgm + 0.5 * tpm, fga)


def _orb(s):
    """Offensive rebounds of a line or of summed totals: counted when the data has them, else OREB_SHARE of REB."""
    if 'xgp' in s:
        if s['gp'] and s['xgp'] == s['gp']:
            return s['oreb']
    elif 'oreb' in s:
        return s['oreb']
    return CONFIG.ANALYTICS.OREB_SHARE * s['reb']


def game_score(s):
    """Hollinger Game Score from a line or summed totals (OREB counted, or its share assumed for old box scores)."""
    oreb = _orb(s)
    return (s['pts'] + 0.4 * s['fgm'] - 0.7 * s['fga'] - 0.4 * (s['fta'] - s['ftm']) + 0.7 * oreb
            + 0.3 * (s['reb'] - oreb) + s['stl'] + 0.7 * s['ast'] + 0.7 * s['blk'] - 0.4 * s['pf'] - s['to'])


def percentile(value, values):
    """Share (0-100) of `values` at or below `value`."""
    if value is None or not values:
        return None
    return round(100.0 * sum(1 for v in values if v <= value) / len(values), 1)


def season_label(box_scores):
    dates = sorted(g.get('date') or '' for g in box_scores.values() if g.get('date'))
    if not dates:
        return None
    year, month = int(dates[0][:4]), int(dates[0][5:7])
    start = year if month >= 7 else year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def _meta(box_scores, user_team):
    a = CONFIG.ANALYTICS
    return {'season': season_label(box_scores), 'games': len(box_scores), 'tint_top': a.TINT_TOP_PCT,
            'tint_bottom': a.TINT_BOTTOM_PCT, 'split_tint': a.SPLIT_TINT_SHARE, 'qualify_gp_share': a.QUALIFY_GP_SHARE,
            'qualify_mpg': a.QUALIFY_MPG, 'oreb_share': a.OREB_SHARE, 'close_margin': a.CLOSE_GAME_MARGIN,
            'fta_weight': a.FTA_WEIGHT, 'per_avg': a.PER_LEAGUE_AVG, 'leaders_per_tile': a.LEADERS_PER_TILE,
            'user_team': user_team}


def _played(lines):
    return [p for p in lines if (p.get('min') or 0) > 0]


def _totals(lines):
    tot = dict.fromkeys(TEAM_STATS + ('oreb', 'dreb'), 0)
    for p in lines:
        for k in TEAM_STATS + ('oreb', 'dreb'):
            tot[k] += p.get(k) or 0
    tot['x'] = bool(lines) and all('oreb' in p for p in lines)   # every line carries the new counters
    return tot


def team_games(box_scores):
    """Per team, its games in calendar order, each with both teams' summed totals and the shared possession count."""
    out = defaultdict(list)
    for g in sorted(box_scores.values(), key=lambda g: (g.get('day_index', 0), g.get('game_id', ''))):
        home, away = g['home_team'], g['away_team']
        tots = {'home_team': _totals(home['players']), 'away_team': _totals(away['players'])}
        poss = (_raw_poss(tots['home_team']) + _raw_poss(tots['away_team'])) / 2
        for key, other in (('home_team', 'away_team'), ('away_team', 'home_team')):
            me, them = g[key], g[other]
            out[me['name']].append({
                'game_id': g.get('game_id'), 'date': g.get('date'), 'day': g.get('day_index', 0),
                'home': key == 'home_team', 'opp': them['name'], 'pf': me.get('score', 0), 'pa': them.get('score', 0),
                'quarters': list(me.get('quarters') or []), 'opp_quarters': list(them.get('quarters') or []),
                'players': me['players'], 'opp_players': them['players'],
                'tm': tots[key], 'opp_tm': tots[other], 'poss': poss})
    return dict(out)


def _player_totals(games_by_team):
    """Season sums per player name, with the team totals of the games he played (for USG/AST%/per-100/PER)."""
    acc = {}
    for team, games in games_by_team.items():
        for g in games:
            tm = g['tm']
            for p in _played(g['players']):
                a = acc.get(p['name'])
                if a is None:
                    a = acc[p['name']] = {'name': p['name'], 'first': {}, 'last': (-1, ''), 'pos': p.get('pos'),
                                          'gp': 0, 'min': 0.0, 'pm': 0, 'on_poss': 0.0, 'tm_poss': 0.0,
                                          **dict.fromkeys(LINE_STATS, 0),
                                          **{'tm_' + k: 0 for k in TEAM_STATS},
                                          'xgp': 0, **dict.fromkeys(EXTRA_STATS + EXTRA_TEAM, 0)}
                if team not in a['first']:
                    a['first'][team] = g['day']
                if (g['day'], g['game_id'] or '') >= a['last']:
                    a['last'] = (g['day'], g['game_id'] or '')
                    a['team'], a['pos'] = team, p.get('pos') or a['pos']
                a['gp'] += 1
                a['min'] += p['min']
                a['pm'] += p.get('plus_minus') or 0
                for k in LINE_STATS:
                    a[k] += p.get(k) or 0
                for k in TEAM_STATS:
                    a['tm_' + k] += tm[k]
                opp = g['opp_tm']
                if 'oreb' in p and tm.get('x') and opp.get('x'):
                    a['xgp'] += 1
                    for k in EXTRA_STATS:
                        a[k] += p.get(k) or 0
                    a['tm_oreb'] += tm['oreb']
                    a['tm_dreb'] += tm['dreb']
                    a['opp_oreb'] += opp['oreb']
                    a['opp_dreb'] += opp['dreb']
                share = p['min'] / (tm['min'] / 5) if tm['min'] else 0
                a['on_poss'] += g['poss'] * share
                a['tm_poss'] += g['poss']
    for a in acc.values():
        a['teams'] = sorted(a['first'], key=a['first'].get)   # in the order he played for them
    return acc


def player_stats(a):
    """A player's stat line (per game, totals, per 36/100, shooting, usage) from his season sums (or an archived copy)."""
    gp, mins = a['gp'], a['min']
    s = {'gp': gp, 'min': _r(mins), 'mpg': _r(mins / gp)}
    for k in LINE_STATS:
        s[k + '_tot'] = a[k]
        s[k + '_pg'] = _r(a[k] / gp)
        s[k + '_36'] = _r(_div(a[k] * 36, mins))
        s[k + '_100'] = _r(_div(a[k] * 100, a['on_poss']))
    s['pm_tot'] = a['pm']
    s['pm_pg'] = _r(a['pm'] / gp)
    fga, fta = a['fga'], a['fta']
    s['fg_pct'] = _r(_pct(a['fgm'], fga))
    s['tp_pct'] = _r(_pct(a['tpm'], a['tpa']))
    s['ft_pct'] = _r(_pct(a['ftm'], fta))
    s['two_pct'] = _r(_pct(a['fgm'] - a['tpm'], fga - a['tpa']))
    s['ts_pct'] = _r(ts_pct(a['pts'], fga, fta))
    s['efg_pct'] = _r(efg_pct(a['fgm'], a['tpm'], fga))
    s['tpa_rate'] = _r(_pct(a['tpa'], fga))
    s['ft_rate'] = _r(_pct(fta, fga))
    tm_min = a['tm_min']
    usg_den = mins * _raw_poss({k: a['tm_' + k] for k in ('fga', 'fta', 'to')})
    s['usg_pct'] = _r(_div(100 * _raw_poss(a) * (tm_min / 5), usg_den))
    ast_den = (mins / (tm_min / 5)) * a['tm_fgm'] - a['fgm'] if tm_min else 0
    s['ast_pct'] = _r(_pct(a['ast'], ast_den)) if ast_den > 0 else None
    s['ato'] = _r(_div(a['ast'], a['to']), 2)
    s['gmsc'] = _r(game_score(a) / gp)
    s['per'] = None
    s.update(_extra_stats(a, gp, mins, tm_min))
    return s


def _extra_stats(acc, gp, mins, tm_min):
    """Stats from the counters saved since 2026-11-15; all None unless every game played has them."""
    out = dict.fromkeys(EXTRA_STAT_KEYS)
    if not gp or acc.get('xgp', 0) != gp:
        return out
    fga, fgm = acc['fga'], acc['fgm']
    out['oreb_tot'], out['oreb_pg'] = acc['oreb'], _r(acc['oreb'] / gp)
    out['dreb_tot'], out['dreb_pg'] = acc['dreb'], _r(acc['dreb'] / gp)
    on_court = mins / (tm_min / 5) if tm_min else 0      # share of his team's minutes he played
    out['orb_pct'] = _r(_pct(acc['oreb'], on_court * (acc['tm_oreb'] + acc['opp_dreb']))) if on_court else None
    out['drb_pct'] = _r(_pct(acc['dreb'], on_court * (acc['tm_dreb'] + acc['opp_oreb']))) if on_court else None
    out['ast_fgm_pct'] = _r(_pct(acc['ast_fgm'], fgm))
    out['rim_fga_pg'], out['rim_fg_pct'], out['rim_rate'] = _r(acc['rim_fga'] / gp), _r(_pct(acc['rim_fgm'], acc['rim_fga'])), _r(_pct(acc['rim_fga'], fga))
    out['mid_fga_pg'], out['mid_fg_pct'], out['mid_rate'] = _r(acc['mid_fga'] / gp), _r(_pct(acc['mid_fgm'], acc['mid_fga'])), _r(_pct(acc['mid_fga'], fga))
    out['clutch_pts_tot'], out['clutch_pts_pg'] = acc['clutch_pts'], _r(acc['clutch_pts'] / gp)
    enough = acc['clutch_fga'] >= CONFIG.ANALYTICS.CLUTCH_FG_MIN_FGA
    out['clutch_fg_pct'] = _r(_pct(acc['clutch_fgm'], acc['clutch_fga'])) if enough else None
    out['clutch_min'] = _r(acc['clutch_min'])
    return out


def _per_estimates(accs, games_by_team):
    """Hollinger PER per player name, with counted offensive rebounds (ORB = OREB_SHARE * REB for old box scores),
    pace-adjusted and scaled so the minutes-weighted league average is PER_LEAGUE_AVG. {} if the league can't support it."""
    lg = dict.fromkeys(LINE_STATS, 0)
    lg_min = 0.0
    for a in accs:
        lg_min += a['min']
        for k in LINE_STATS:
            lg[k] += a[k]
    team_game_poss = [g['poss'] for games in games_by_team.values() for g in games]
    share = CONFIG.ANALYTICS.OREB_SHARE
    counted = bool(accs) and all(x['gp'] and x.get('xgp') == x['gp'] for x in accs)
    lg_orb = sum(x['oreb'] for x in accs) if counted else share * lg['reb']
    lg_trb = lg['reb']
    if not (lg['fgm'] and lg['ftm'] and lg['pf'] and lg_trb and lg_min and team_game_poss):
        return {}
    fw = CONFIG.ANALYTICS.FTA_WEIGHT
    vop_den = lg['fga'] - lg_orb + lg['to'] + fw * lg['fta']
    if not vop_den:
        return {}
    factor = 2 / 3 - (0.5 * lg['ast'] / lg['fgm']) / (2 * lg['fgm'] / lg['ftm'])
    vop = lg['pts'] / vop_den
    drbp = (lg_trb - lg_orb) / lg_trb
    pf_cost = lg['ftm'] / lg['pf'] - fw * (lg['fta'] / lg['pf']) * vop
    lg_pace = sum(team_game_poss) / len(team_game_poss)
    aper = {}
    for a in accs:
        if not a['min'] or not a['tm_fgm'] or not a['tm_poss']:
            continue
        orb = a['oreb'] if counted else share * a['reb']
        tm_ast_fg = a['tm_ast'] / a['tm_fgm']
        uper = (a['tpm'] + (2 / 3) * a['ast'] + (2 - factor * tm_ast_fg) * a['fgm']
                + a['ftm'] * 0.5 * (1 + (1 - tm_ast_fg) + (2 / 3) * tm_ast_fg)
                - vop * a['to'] - vop * drbp * (a['fga'] - a['fgm'])
                - vop * fw * (fw + (1 - fw) * drbp) * (a['fta'] - a['ftm'])
                + vop * (1 - drbp) * (a['reb'] - orb) + vop * drbp * orb
                + vop * a['stl'] + vop * drbp * a['blk'] - a['pf'] * pf_cost) / a['min']
        aper[a['name']] = (uper * lg_pace / (a['tm_poss'] / a['gp']), a['min'])
    if not aper:
        return {}
    lg_aper = sum(v * m for v, m in aper.values()) / sum(m for _v, m in aper.values())
    if not lg_aper:
        return {}
    scale = CONFIG.ANALYTICS.PER_LEAGUE_AVG / lg_aper
    return {name: v * scale for name, (v, _m) in aper.items()}


def archive_lines(box_scores):
    """Name -> the season sums player_stats() needs, plus PER and the teams in the order he played for them."""
    games_by_team = team_games(box_scores)
    accs = list(_player_totals(games_by_team).values())
    per = _per_estimates(accs, games_by_team)
    out = {}
    for acc in accs:
        line = {k: (round(acc[k], 3) if isinstance(acc[k], float) else acc[k]) for k in ARCHIVE_KEYS}
        line['per'] = _r(per.get(acc['name']))
        line['teams'] = list(acc['teams'])
        out[acc['name']] = line
    return out

def _season_start(date):
    """2027 for any date of the 2027-28 season ("2027-10-23", "2028-04-14")."""
    year, month = int(date[:4]), int(date[5:7])
    return year if month >= 7 else year - 1


def archive_for_rosters(box_scores, roster_names):
    """archive_lines() for the season being archived: only the latest season's games (auto-sim used to keep older box
    scores), and no line for a name on more than one roster (two players saved under one name share one line)."""
    starts = {gid: _season_start(g['date']) for gid, g in box_scores.items() if g.get('date')}
    latest = max(starts.values(), default=None)
    games = {gid: g for gid, g in box_scores.items() if starts.get(gid, latest) == latest}
    counts = {}
    for name in roster_names:
        counts[name] = counts.get(name, 0) + 1
    return {name: ln for name, ln in archive_lines(games).items() if counts.get(name, 0) <= 1}


PLAYOFF_ROUNDS = ('play_in', 'qf', 'sf', 'cf')


def playoff_box_scores(bracket):
    """Game id -> box score of every playoff game of the season. Playoff and play-in games keep their box score only in
    the bracket (each series' games[i]['result_sheet']), never in the season's box_scores."""
    out = {}
    if not isinstance(bracket, dict):
        return out
    series = []
    for conf in ('east', 'west'):
        rounds = bracket.get(conf) or {}
        for rnd in PLAYOFF_ROUNDS:
            series += list(rounds.get(rnd) or [])
    series += list(bracket.get('finals') or [])
    for s in series:
        for g in (s or {}).get('games') or []:
            sheet = (g or {}).get('result_sheet')
            if sheet and sheet.get('game_id'):
                out[sheet['game_id']] = sheet
    return out


def archive_season_lines(box_scores, bracket, roster_names):
    """The season's full lines to archive: {'rs': regular season, 'po': playoffs}, name -> archive_lines() sums."""
    return {'rs': archive_for_rosters(box_scores or {}, roster_names),
            'po': archive_for_rosters(playoff_box_scores(bracket), roster_names)}


def players_view(box_scores, rostered, user_team):
    games_by_team = team_games(box_scores)
    a = CONFIG.ANALYTICS
    accs = list(_player_totals(games_by_team).values())
    per = _per_estimates(accs, games_by_team)
    rows = []
    for acc in accs:
        s = player_stats(acc)
        s['per'] = _r(per.get(acc['name']))
        team_gp = len(games_by_team.get(acc['team'], []))
        qualified = acc['gp'] >= a.QUALIFY_GP_SHARE * team_gp and s['mpg'] >= a.QUALIFY_MPG
        rows.append({'name': acc['name'], 'team': acc['team'], 'teams': acc['teams'], 'pos': acc['pos'],
                     'gp': acc['gp'], 'team_gp': team_gp, 'qualified': qualified,
                     'in_league': acc['name'] in rostered, 'is_user_team': acc['team'] == user_team, 's': s})
    pool = [r for r in rows if r['qualified']]
    for r in rows:
        r['pct'] = {k: (percentile(r['s'][k], [q['s'][k] for q in pool if q['s'][k] is not None])
                        if r['qualified'] else None) for k in PLAYER_PCT_KEYS}
    rows.sort(key=lambda r: (-(r['s']['pts_pg'] or 0), r['name']))
    return {'meta': _meta(box_scores, user_team), 'players': rows}


TEAM_PCT_KEYS = {'ortg': False, 'efg': False, 'tov_pct': True, 'ft_rate': False, 'drtg': True, 'opp_efg': True,
                 'opp_tov_pct': False, 'reb_diff': False, 'net': False, 'pace': False,
                 'orb_pct': False, 'drb_pct': False}   # key -> lower is better


def fit_exponent(teams):
    """Pythagorean exponent fitted by least squares; teams = [(wins, games, points for, points against)].
    Falls back to CONFIG until every team has played PYTH_MIN_GAMES games."""
    a = CONFIG.ANALYTICS
    if not teams or min(gp for _w, gp, _pf, _pa in teams) < a.PYTH_MIN_GAMES:
        return {'value': a.PYTH_FALLBACK_EXP, 'rmse': None, 'fitted': False}
    best = None
    steps = int(round((a.PYTH_EXP_MAX - a.PYTH_EXP_MIN) / a.PYTH_EXP_STEP))
    for i in range(steps + 1):
        e = round(a.PYTH_EXP_MIN + i * a.PYTH_EXP_STEP, 4)
        err = sum((expected_wins(gp, pf, pa, e) - w) ** 2 for w, gp, pf, pa in teams)
        if best is None or err < best[1]:
            best = (e, err)
    return {'value': best[0], 'rmse': round((best[1] / len(teams)) ** 0.5, 2), 'fitted': True}


def expected_wins(gp, pf, pa, exponent):
    if not gp or (not pf and not pa):
        return gp / 2 if gp else 0.0
    # Ratio form avoids overflow with large totals: 1 / (1 + (pa/pf)^e).
    return gp / (1 + (pa / pf) ** exponent) if pf else 0.0


def _record(games, test):
    picked = [g for g in games if test(g)]
    wins = sum(1 for g in picked if g['pf'] > g['pa'])
    return [wins, len(picked) - wins]


def _team_rows(games_by_team, conferences, user_team):
    """Team rows (stats, records, quarter margins) plus the season's exponent; shared by the Teams and League views."""
    close = CONFIG.ANALYTICS.CLOSE_GAME_MARGIN
    rows = []
    for name, games in games_by_team.items():
        gp = len(games)
        tm = {k: sum(g['tm'][k] for g in games) for k in TEAM_STATS}
        op = {k: sum(g['opp_tm'][k] for g in games) for k in TEAM_STATS}
        pf, pa = sum(g['pf'] for g in games), sum(g['pa'] for g in games)
        poss = sum(g['poss'] for g in games)
        w = sum(1 for g in games if g['pf'] > g['pa'])
        ortg, drtg = _pct(pf, poss), _pct(pa, poss)
        s = {'ppg': _r(pf / gp), 'opp_ppg': _r(pa / gp), 'pace': _r(poss / gp), 'ortg': _r(ortg), 'drtg': _r(drtg),
             'net': _r(ortg - drtg) if ortg is not None else None}
        for prefix, t in (('', tm), ('opp_', op)):
            s[prefix + 'efg'] = _r(efg_pct(t['fgm'], t['tpm'], t['fga']))
            s[prefix + 'tov_pct'] = _r(_pct(t['to'], _raw_poss(t)))
            s[prefix + 'ft_rate'] = _r(_pct(t['fta'], t['fga']))
            s[prefix + 'fg_pct'] = _r(_pct(t['fgm'], t['fga']))
            s[prefix + 'tp_pct'] = _r(_pct(t['tpm'], t['tpa']))
            s[prefix + 'tpa_rate'] = _r(_pct(t['tpa'], t['fga']))
            s[prefix + 'reb_pg'] = _r(t['reb'] / gp)
            s[prefix + 'to_pg'] = _r(t['to'] / gp)
        s['ft_pct'] = _r(_pct(tm['ftm'], tm['fta']))
        s['reb_diff'] = _r((tm['reb'] - op['reb']) / gp)
        s['ast_pg'] = _r(tm['ast'] / gp)
        s['ast_rate'] = _r(_pct(tm['ast'], tm['fgm']))
        s['stl_pg'] = _r(tm['stl'] / gp)
        s['blk_pg'] = _r(tm['blk'] / gp)
        # Rebound factor: only when every game carries the offensive/defensive split (box scores since 2026-11-15)
        counted = all(g['tm'].get('x') and g['opp_tm'].get('x') for g in games)
        t_or, t_dr = sum(g['tm']['oreb'] for g in games), sum(g['tm']['dreb'] for g in games)
        o_or, o_dr = sum(g['opp_tm']['oreb'] for g in games), sum(g['opp_tm']['dreb'] for g in games)
        s['oreb_pg'] = _r(t_or / gp) if counted else None
        s['orb_pct'] = _r(_pct(t_or, t_or + o_dr)) if counted else None
        s['drb_pct'] = _r(_pct(t_dr, t_dr + o_or)) if counted else None
        quarters = []
        for q in range(4):
            margins = [g['quarters'][q] - g['opp_quarters'][q] for g in games
                       if len(g['quarters']) > q and len(g['opp_quarters']) > q]
            quarters.append(_r(sum(margins) / len(margins)) if margins else None)
        rows.append({'name': name, 'conference': conferences.get(name), 'is_user_team': name == user_team,
                     'w': w, 'l': gp - w, 'gp': gp, 's': s, 'quarters': quarters, '_pf': pf, '_pa': pa,
                     'home': _record(games, lambda g: g['home']), 'away': _record(games, lambda g: not g['home']),
                     'close': _record(games, lambda g: abs(g['pf'] - g['pa']) <= close)})
    exponent = fit_exponent([(r['w'], r['gp'], r['_pf'], r['_pa']) for r in rows])
    for r in rows:
        exp_w = expected_wins(r['gp'], r.pop('_pf'), r.pop('_pa'), exponent['value'])
        r['s']['exp_w'] = _r(exp_w)
        r['s']['luck'] = _r(r['w'] - exp_w)
    for r in rows:
        r['pct'] = {}
        for k, low_good in TEAM_PCT_KEYS.items():
            vals = [x['s'][k] for x in rows if x['s'][k] is not None]
            v = r['s'][k]
            r['pct'][k] = (percentile(-v, [-x for x in vals]) if low_good else percentile(v, vals)) if v is not None else None
    rows.sort(key=lambda r: (-(r['s']['net'] or 0), r['name']))
    return rows, exponent


def teams_view(box_scores, conferences, user_team):
    rows, exponent = _team_rows(team_games(box_scores), conferences, user_team)
    return {'meta': _meta(box_scores, user_team), 'exponent': exponent, 'teams': rows}


MONTH_LABELS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _pulse(games):
    """League averages over a set of box scores (per team-game)."""
    n = len(games)
    if not n:
        return None
    tot = dict.fromkeys(LINE_STATS, 0)
    pts = home_wins = 0
    for g in games:
        home_wins += g['home_team'].get('score', 0) > g['away_team'].get('score', 0)
        for key in ('home_team', 'away_team'):
            pts += g[key].get('score', 0)
            for p in g[key]['players']:
                for k in LINE_STATS:
                    tot[k] += p.get(k) or 0
    poss = _raw_poss(tot)
    return {'games': n, 'ppg': _r(pts / (2 * n)), 'pace': _r(poss / (2 * n)), 'ortg': _r(_pct(pts, poss)),
            'efg': _r(efg_pct(tot['fgm'], tot['tpm'], tot['fga'])), 'ts': _r(ts_pct(pts, tot['fga'], tot['fta'])),
            'tov_pct': _r(_pct(tot['to'], poss)), 'tpa_rate': _r(_pct(tot['tpa'], tot['fga'])),
            'home_win_pct': _r(100.0 * home_wins / n)}


def league_view(box_scores, user_team):
    rows, exponent = _team_rows(team_games(box_scores), {}, user_team)
    teams = [{'name': r['name'], 'ortg': r['s']['ortg'], 'drtg': r['s']['drtg'], 'net': r['s']['net'], 'w': r['w'],
              'exp_w': r['s']['exp_w'], 'luck': r['s']['luck'], 'is_user_team': r['is_user_team']} for r in rows]
    by_month = defaultdict(list)
    for g in box_scores.values():
        if g.get('date'):
            by_month[g['date'][:7]].append(g)
    months = []
    for month in sorted(by_month):
        p = _pulse(by_month[month])
        months.append({'month': month, 'label': MONTH_LABELS[int(month[5:7]) - 1], 'games': p['games'], 'ppg': p['ppg'],
                       'pace': p['pace'], 'efg': p['efg'], 'tpa_rate': p['tpa_rate'], 'home_win_pct': p['home_win_pct']})
    base = _pulse(list(box_scores.values())) or {}
    baseline = {k: base.get(k) for k in ('ppg', 'ortg', 'pace', 'efg', 'ts', 'tov_pct', 'tpa_rate', 'home_win_pct')}
    rated = [t for t in teams if t['ortg'] is not None]
    league_avg = {k: (_r(sum(t[k] for t in rated) / len(rated)) if rated else None) for k in ('ortg', 'drtg')}
    return {'meta': _meta(box_scores, user_team), 'exponent': exponent, 'league_avg': league_avg, 'teams': teams,
            'months': months, 'baseline': baseline}


SPLIT_HIGHS = (('pts', 'Points'), ('reb', 'Rebounds'), ('ast', 'Assists'), ('stl', 'Steals'), ('gmsc', 'Game Score'))
LOG_STATS = ('min', 'pts', 'reb', 'ast', 'stl', 'blk', 'to', 'pf', 'fgm', 'fga', 'tpm', 'tpa', 'ftm', 'fta')


def _month_label(date):
    return MONTH_LABELS[int(date[5:7]) - 1] if date and len(date) >= 7 else '?'


def _split_row(label, entries, team_mode):
    """One split line over {g, ln} entries (ln = the player's line, or the team totals in team mode)."""
    n = len(entries)
    if not n:
        return None
    tot = {k: sum(e['ln'][k] for e in entries) for k in ('pts', 'reb', 'ast', 'fga', 'fta')}
    w = sum(1 for e in entries if e['g']['pf'] > e['g']['pa'])
    if team_mode:
        mins, pm = None, _r(sum(e['g']['pf'] - e['g']['pa'] for e in entries) / n)
    else:
        mins = _r(sum(e['ln']['min'] for e in entries) / n)
        pm = _r(sum(e['ln'].get('plus_minus') or 0 for e in entries) / n)
    return {'label': label, 'gp': n, 'min': mins, 'pts': _r(tot['pts'] / n), 'reb': _r(tot['reb'] / n),
            'ast': _r(tot['ast'] / n), 'ts_pct': _r(ts_pct(tot['pts'], tot['fga'], tot['fta'])), 'pm': pm,
            'w': w, 'l': n - w}


def _log_row(g, ln, b2b, team_mode):
    row = {'game_id': g['game_id'], 'date': g['date'], 'home': g['home'], 'opp': g['opp'], 'win': g['pf'] > g['pa'],
           'score_for': g['pf'], 'score_against': g['pa'], 'b2b': b2b, 'dnp': ln is None}
    for k in LOG_STATS:
        row[k] = None if ln is None else (_r(ln[k]) if k == 'min' else ln[k])
    if ln is None:
        row['pm'] = row['gmsc'] = None
        return row
    row['gmsc'] = _r(game_score(ln))
    if team_mode:
        row['min'] = None
        row['pm'] = g['pf'] - g['pa']
    else:
        row['pm'] = ln.get('plus_minus') or 0
    return row


def _player_entries(games_by_team, days, player):
    """The player's games (entries) and log rows; log covers each stint from his first to last game for that team,
    so games he missed in between show as 'did not play'."""
    entries, log = [], []
    for t, games in games_by_team.items():
        rows = [(g, next((p for p in _played(g['players']) if p['name'] == player), None)) for g in games]
        played = [i for i, (_g, ln) in enumerate(rows) if ln is not None]
        if not played:
            continue
        for g, ln in rows[played[0]:played[-1] + 1]:
            b2b = g['day'] - 1 in days[t]
            log.append(_log_row(g, ln, b2b, False))
            if ln is not None:
                entries.append({'g': g, 'ln': ln, 'b2b': b2b, 'team': t})
    return entries, log


def splits_view(box_scores, conferences, user_team, player=None, team=None):
    """Splits, monthly lines, opponents, season highs and the game log of one player or team; None if no games."""
    games_by_team = team_games(box_scores)
    team_mode = player is None
    days = {t: {g['day'] for g in games} for t, games in games_by_team.items()}
    if team_mode:
        games = games_by_team.get(team)
        if not games:
            return None
        entries, log = [], []
        for g in games:
            b2b = g['day'] - 1 in days[team]
            ln = {**g['tm'], 'pts': g['pf']}
            entries.append({'g': g, 'ln': ln, 'b2b': b2b, 'team': team})
            log.append(_log_row(g, ln, b2b, True))
    else:
        entries, log = _player_entries(games_by_team, days, player)
        if not entries:
            return None
    entries.sort(key=lambda e: (e['g']['day'], e['g']['game_id'] or ''))
    log.sort(key=lambda r: (r['date'] or '', r['game_id'] or ''), reverse=True)
    last = entries[-1]

    def row(label, picked):
        return _split_row(label, picked, team_mode)

    groups = [('Home', lambda e: e['g']['home']), ('Away', lambda e: not e['g']['home']),
              ('In wins', lambda e: e['g']['pf'] > e['g']['pa']), ('In losses', lambda e: e['g']['pf'] <= e['g']['pa']),
              ('Back-to-back 2nd night', lambda e: e['b2b']), ('Rested', lambda e: not e['b2b'])]
    if team_mode:
        margin = CONFIG.ANALYTICS.CLOSE_GAME_MARGIN
        groups += [('vs East', lambda e: conferences.get(e['g']['opp']) == 'East'),
                   ('vs West', lambda e: conferences.get(e['g']['opp']) == 'West'),
                   (f'Within {margin} pts', lambda e: abs(e['g']['pf'] - e['g']['pa']) <= margin)]
    splits = [r for r in (row(label, [e for e in entries if test(e)]) for label, test in groups) if r]

    months = [row(_month_label(m), [e for e in entries if (e['g']['date'] or '')[:7] == m])
              for m in sorted({(e['g']['date'] or '')[:7] for e in entries if e['g']['date']})]
    by_opp = defaultdict(list)
    for e in entries:
        by_opp[e['g']['opp']].append(e)
    opponents = sorted((row(o, es) for o, es in by_opp.items()), key=lambda r: (-r['gp'], r['label']))

    highs = []
    for stat, label in SPLIT_HIGHS:
        def value_of(e, stat=stat):
            return game_score(e['ln']) if stat == 'gmsc' else e['ln'][stat]
        best = max(entries, key=value_of)   # earliest game wins ties
        v = value_of(best)
        highs.append({'stat': stat, 'label': label, 'value': _r(v) if stat == 'gmsc' else v, 'opp': best['g']['opp'],
                      'home': best['g']['home'], 'date': best['g']['date'], 'game_id': best['g']['game_id']})

    quarters = _team_rows({team: games_by_team[team]}, {}, None)[0][0]['quarters'] if team_mode else None
    return {'meta': _meta(box_scores, user_team), 'kind': 'team' if team_mode else 'player',
            'name': team if team_mode else player, 'team': last['team'],
            'pos': None if team_mode else last['ln'].get('pos'), 'season_line': row('Season', entries),
            'splits': splits, 'months': months, 'opponents': opponents, 'quarters': quarters, 'highs': highs, 'log': log}
