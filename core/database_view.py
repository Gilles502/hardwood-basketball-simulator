# File: core/database_view.py
"""Player Database views: every player and every season in the save.

Pure functions, no Flask. Careers come from player_careers.json ({slug: [season record, ...]}) in any of its formats:
per-game numbers in `stats_rs`/`stats_po` (most saves), season totals `pts`, `reb`, ... (old saves), and from the
2026-10-30 build on a full box-score line in `full_rs` (from 2026-11-15 also `full_po` for the playoffs). Every record becomes one "line" whose stat keys are League
Analytics' (`pts_pg`, `ts_pct`, ...); a stat the record doesn't hold is None, never 0.
"""
from core.analytics_view import ARCHIVE_KEYS, EXTRA_STAT_KEYS, LINE_STATS, player_stats
from core.config import CONFIG
from core.franchise_legacy import career_name
from core.history_view import year_for

STAT_KEYS = (('gp', 'min', 'mpg')
             + tuple(f'{k}_{sfx}' for k in LINE_STATS for sfx in ('tot', 'pg', '36', '100'))
             + ('pm_tot', 'pm_pg', 'fg_pct', 'tp_pct', 'ft_pct', 'two_pct', 'ts_pct', 'efg_pct', 'tpa_rate', 'ft_rate',
                'usg_pct', 'ast_pct', 'ato', 'gmsc', 'per')
             + EXTRA_STAT_KEYS)
# Old per-game record key -> line stat; the counting stats every format holds.
OLD_PER_GAME = {'ppg': 'pts', 'rpg': 'reb', 'apg': 'ast', 'spg': 'stl', 'bpg': 'blk'}
OLD_PCT = {'fg_pct': 'fg_pct', 'three_pct': 'tp_pct', 'ft_pct': 'ft_pct'}
COUNTING = ('pts', 'reb', 'ast', 'stl', 'blk')
PCT_PARTS = {'fg_pct': ('fgm', 'fga'), 'tp_pct': ('tpm', 'tpa'), 'ft_pct': ('ftm', 'fta')}
STATUSES = ('Active', 'Free agent', 'Retired', 'Out of league')
# Award names as saved -> the name they are counted under ("All-Star Starter" is an All-Star selection).
AWARD_ALIASES = {'All-Star Starter': 'All-Star'}
# Directory highlights, in this order: (count key, label); at most HIGHLIGHTS_SHOWN.
HIGHLIGHTS = (('Champion', 'Champion'), ('MVP', 'MVP'), ('Finals MVP', 'Finals MVP'), ('DPOY', 'DPOY'),
              ('All-NBA', 'All-NBA'), ('All-Star', 'All-Star'))
HIGHLIGHTS_SHOWN = 3
ALL_NBA = ('All-NBA 1st', 'All-NBA 2nd', 'All-NBA 3rd')
RANK_TOTALS = ('gp',) + tuple(k + '_tot' for k in COUNTING)
LEADER_STATS = ('pts_pg', 'reb_pg', 'ast_pg', 'stl_pg', 'blk_pg', 'fg_pct')
# Stat Finder: career-mode extras, and the keys every saved season holds (any other key needs a full line).
CAREER_EXTRA = ('seasons', 'titles', 'all_star')
ALWAYS_KEYS = (('gp',) + tuple(f'{k}_{sfx}' for k in COUNTING for sfx in ('tot', 'pg'))
               + tuple(PCT_PARTS) + CAREER_EXTRA)
DIRECTORY_SORTS = ('name', 'status', 'team', 'pos', 'age', 'ovr', 'pot', 'salary', 'seasons', 'gp', 'pts_pg',
                   'reb_pg', 'ast_pg', 'titles', 'last_year')


def slug(name):
    return (name or '').replace(' ', '-').lower()


def _r(value, digits=1):
    return None if value is None else round(value, digits)


def _games(record, kind):
    if kind == 'po':
        return record.get('gp_po') or record.get('partite_giocate_po') or 0
    return record.get('gp') or record.get('partite_giocate_rs') or 0


def _full(record, kind):
    return record.get('full_rs' if kind == 'rs' else 'full_po')


def _stats(record, kind, gp):
    """(stat dict, full, est) for one record, or None when it holds nothing for this kind."""
    s = dict.fromkeys(STAT_KEYS)
    s['gp'] = gp
    full = _full(record, kind)
    if full and full.get('gp'):
        s.update(player_stats(full))
        s['per'] = full.get('per')
        return s, True, False
    if kind == 'rs' and 'pts' in record:
        for k in COUNTING:
            total = record.get(k)
            s[k + '_tot'] = total
            s[k + '_pg'] = _r(total / gp) if gp and total is not None else None
        for old, new in OLD_PCT.items():
            s[new] = record.get(old)
        return s, False, False
    old = record.get('stats_rs' if kind == 'rs' else 'stats_po')
    if not old:
        return (s, False, False) if kind == 'rs' else None
    if gp:
        for old_key, k in OLD_PER_GAME.items():
            per_game = old.get(old_key)
            s[k + '_pg'] = per_game
            s[k + '_tot'] = None if per_game is None else int(round(per_game * gp))
        for old_key, k in OLD_PCT.items():
            s[k] = old.get(old_key)
    return s, False, bool(gp)


def season_line(record, kind, year):
    """One season of one player as a line (see module doc); None when the record has nothing for `kind`."""
    gp = _games(record, kind)
    full = _full(record, kind)
    if full and full.get('gp'):
        gp = full['gp']
    out = _stats(record, kind, gp)
    if out is None:
        return None
    s, is_full, est = out
    team = record.get('squadra')
    teams = list(full['teams']) if is_full and full.get('teams') else ([team] if team else [])
    return {'season': record.get('stagione'), 'year': year, 'team': team, 'teams': teams,
            'pos': record.get('ruolo'), 'age': record.get('eta'), 'ovr': record.get('ovr'),
            'pot': record.get('potenziale'), 'champion': bool(record.get('is_champion')),
            'awards': list(record.get('premi') or record.get('awards') or []),
            'gp': gp, 'full': is_full, 'est': est, 's': s}


def current_records(players, lines, season, po_lines=None):
    """Slug -> a career record for the season being played, from the live players and archive_lines() of the regular
    season (`lines`) and of the playoffs being played (`po_lines`)."""
    out = {}
    po_lines = po_lines or {}
    for p in players:
        ln = lines.get(p['name'])
        po = po_lines.get(p['name'])
        team = p.get('team') or (ln['teams'][-1] if ln and ln.get('teams') else None)
        record = {'stagione': season, 'squadra': team, 'nome': p['name'], 'ruolo': p.get('pos'), 'eta': p.get('age'),
                  'ovr': p.get('ovr'), 'potenziale': p.get('pot'), 'is_champion': False, 'premi': [],
                  'gp': ln['gp'] if ln else 0, 'gp_po': po['gp'] if po else 0, 'stats_rs': None, 'stats_po': None}
        if ln:
            record['full_rs'] = ln
        if po:
            record['full_po'] = po
        out[slug(p['name'])] = record
    return out


def _records(raw):
    return [r for r in raw or [] if isinstance(r, dict)]


def merged_careers(careers, current, season):
    """Careers plus the live season, unless the careers already hold that season (offseason) or nobody has played
    a game of it yet (preseason: an empty season would hide the one just played); records by season."""
    archived = any(r.get('stagione') == season for raw in (careers or {}).values() for r in _records(raw))
    current = {k: r for k, r in (current or {}).items() if r.get('gp') or r.get('gp_po')}
    out = {k: sorted(_records(raw), key=lambda r: r.get('stagione') or 0) for k, raw in (careers or {}).items()}
    if not archived:
        for k, record in (current or {}).items():
            out[k] = out.get(k, []) + [record]
    return {k: v for k, v in out.items() if v}


def _year(record, years, starting_year):
    return year_for(record.get('stagione'), years, starting_year)


def lines_of(records, kind, years, starting_year):
    """Every season line of one player for `kind`, in season order."""
    out = (season_line(r, kind, _year(r, years, starting_year)) for r in _records(records))
    return [ln for ln in out if ln is not None]


def career_line(records, kind):
    """The career row: summed seasons. Full advanced numbers only when every season played has a full line."""
    played = [(r, ln) for r in _records(records) for ln in [season_line(r, kind, None)] if ln and ln['gp']]
    if not played:
        return None
    gp = sum(ln['gp'] for _r, ln in played)
    seasons = len({ln['season'] for _r, ln in played})
    if all(ln['full'] for _r, ln in played):
        # Lines archived before a counter existed (e.g. xgp, 2026-11-15) lack its key: 0, so it is never half counted.
        fulls = [_full(r, kind) for r, _ln in played]
        acc = {k: sum(f.get(k, 0) for f in fulls) for k in ARCHIVE_KEYS}
        s = player_stats(acc)
        minutes = acc['min']
        pers = [(f.get('per'), f.get('min', 0)) for f in fulls]
        s['per'] = (_r(sum(p * m for p, m in pers) / minutes)
                    if minutes and all(p is not None for p, _m in pers) else None)
        return {'gp': gp, 'seasons': seasons, 'full': True, 'est': False, 's': s}
    s = dict.fromkeys(STAT_KEYS)
    s['gp'] = gp
    for k in LINE_STATS:
        totals = [ln['s'][k + '_tot'] for _r, ln in played]
        if all(t is not None for t in totals):
            s[k + '_tot'] = sum(totals)
            s[k + '_pg'] = _r(s[k + '_tot'] / gp)
    for k in PCT_PARTS:
        weighted = [(ln['s'][k], ln['gp']) for _r, ln in played if ln['s'][k] is not None]
        games = sum(g for _v, g in weighted)
        s[k] = _r(sum(v * g for v, g in weighted) / games) if games else None
    return {'gp': gp, 'seasons': seasons, 'full': False, 'est': any(ln['est'] for _r, ln in played), 's': s}


def award_counts(records):
    """Award -> times won ("All-Star Starter" counted as "All-Star"), in first-won order."""
    counts = {}
    for r in _records(records):
        for award in r.get('premi') or r.get('awards') or []:
            name = AWARD_ALIASES.get(award, award)
            counts[name] = counts.get(name, 0) + 1
    return counts


def _titles(records):
    return sum(1 for r in _records(records) if r.get('is_champion'))


def _status(key, live, retired):
    if key in live:
        return live[key].get('status') or 'Active'
    return 'Retired' if key in retired else 'Out of league'


def _highlights(records):
    counts = dict(award_counts(records))
    counts['Champion'] = _titles(records)
    counts['All-NBA'] = sum(counts.get(a, 0) for a in ALL_NBA)
    return [f'{counts[k]}× {label}' for k, label in HIGHLIGHTS if counts.get(k)][:HIGHLIGHTS_SHOWN]


def _identity(key, records, info, status, years, starting_year):
    """Name, status, team and the live-only fields (OVR, POT, contract) shared by the directory and the player page."""
    info = info or {}
    last = records[-1] if records else {}
    active = status in ('Active', 'Free agent')
    return {'slug': key, 'name': info.get('name') or career_name(key, records), 'status': status,
            'team': info.get('team') if active else last.get('squadra'),
            'pos': info.get('pos') or last.get('ruolo'), 'age': info.get('age') or last.get('eta'),
            'ovr': info.get('ovr') if active else None, 'pot': info.get('pot') if active else None,
            'salary': info.get('salary') if active else None, 'years': info.get('years') if active else None,
            'last_year': _year(last, years, starting_year) if records else None}


def _directory_row(key, records, info, status, years, starting_year):
    career = career_line(records, 'rs')
    cs = career['s'] if career else {}
    row = _identity(key, records, info, status, years, starting_year)
    row.update({'seasons': len({r.get('stagione') for r in records}), 'gp': career['gp'] if career else 0,
                'pts_pg': cs.get('pts_pg'), 'reb_pg': cs.get('reb_pg'), 'ast_pg': cs.get('ast_pg'),
                'titles': _titles(records), 'highlights': _highlights(records)})
    return row


def _sorted(rows, key, desc):
    """Rows by `key`; rows without a value always last."""
    have = [r for r in rows if r.get(key) is not None]
    missing = [r for r in rows if r.get(key) is None]
    have.sort(key=lambda r: r['name'])
    have.sort(key=lambda r: r[key].lower() if isinstance(r[key], str) else r[key], reverse=desc)
    return have + sorted(missing, key=lambda r: r['name'])


def _flag(value, default):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() not in ('0', 'false', 'no', '')


def _sorted_records(careers, key):
    return sorted(_records(careers.get(key)), key=lambda r: r.get('stagione') or 0)


def directory_view(careers, live, retired, years, starting_year, query):
    """The Players directory: filtered, sorted and paged on the server."""
    q = query or {}
    careers, live, retired = careers or {}, live or {}, retired or set()
    rows = [_directory_row(key, _sorted_records(careers, key), live.get(key), _status(key, live, retired),
                           years, starting_year)
            for key in sorted(set(careers) | set(live))]
    text = (q.get('q') or '').strip().lower()
    if text:
        rows = [r for r in rows if text in r['name'].lower()]
    if q.get('pos'):
        rows = [r for r in rows if r['pos'] == q['pos']]
    if q.get('team'):
        rows = [r for r in rows if r['team'] == q['team']]
    counts = {status: sum(1 for r in rows if r['status'] == status) for status in STATUSES}
    status = q.get('status') or 'Active'
    if status != 'All':
        rows = [r for r in rows if r['status'] == status]
    sort = q.get('sort') if q.get('sort') in DIRECTORY_SORTS else 'ovr'
    rows = _sorted(rows, sort, _flag(q.get('desc'), True))
    size = CONFIG.DATABASE.PAGE_SIZE
    pages = max(1, -(-len(rows) // size))
    try:
        page = min(max(1, int(q.get('page') or 1)), pages)
    except (TypeError, ValueError):
        page = 1
    teams = sorted({i.get('team') for i in live.values() if i.get('team') and i.get('status') == 'Active'})
    return {'rows': rows[(page - 1) * size: page * size], 'total': len(rows), 'page': page, 'pages': pages,
            'teams': teams, 'counts': counts}


def _played_lines(careers):
    """Slug -> the regular-season lines he played (built once per request: ranks read them per team)."""
    out = {}
    for key, raw in careers.items():
        lines = [ln for ln in (season_line(r, 'rs', None) for r in _records(raw)) if ln and ln['gp']]
        if lines:
            out[key] = lines
    return out


def _totals_by_player(played, team=None):
    """Slug -> {gp, pts_tot, ...} over all seasons (or only those with `team`), from each season's own numbers."""
    out = {}
    for key, all_lines in played.items():
        lines = [ln for ln in all_lines if team is None or ln['team'] == team]
        if not lines:
            continue
        row = {'gp': sum(ln['gp'] for ln in lines)}
        for k in COUNTING:
            row[k + '_tot'] = sum(ln['s'][k + '_tot'] or 0 for ln in lines)
        out[key] = row
    return out


def _ranks(key, table, per_game):
    """[{stat, rank, value}] where the player is in the top RANK_TOP_N of `table`."""
    me = table.get(key)
    if not me:
        return []
    top, min_gp = CONFIG.DATABASE.RANK_TOP_N, CONFIG.DATABASE.RANK_MIN_GP
    out = []
    for stat in RANK_TOTALS:
        rank = 1 + sum(1 for k, row in table.items() if k != key and row[stat] > me[stat])
        if me[stat] and rank <= top:
            out.append({'stat': stat, 'rank': rank, 'value': me[stat]})
    if per_game and me['gp'] >= min_gp:
        pool = [row for k, row in table.items() if k != key and row['gp'] >= min_gp]
        for k in COUNTING:
            mine = me[k + '_tot'] / me['gp']
            rank = 1 + sum(1 for row in pool if row[k + '_tot'] / row['gp'] > mine)
            if rank <= top:
                out.append({'stat': k + '_pg', 'rank': rank, 'value': _r(mine)})
    return out


def latest_season(careers):
    return max((r.get('stagione') or 0 for raw in (careers or {}).values() for r in _records(raw)), default=0)


def player_view(key, careers, live, retired, years, starting_year):
    """Everything the player page shows; None for an unknown player."""
    careers, live, retired = careers or {}, live or {}, retired or set()
    records = _sorted_records(careers, key)
    info = live.get(key)
    if not records and not info:
        return None
    status = _status(key, live, retired)

    def year(r):
        return _year(r, years, starting_year)

    rs = lines_of(records, 'rs', years, starting_year)
    career = career_line(records, 'rs')
    counts = award_counts(records)
    best = max((ln for ln in rs if ln['gp']), key=lambda ln: ln['s']['pts_pg'] or 0, default=None)
    seasons = sorted({r.get('stagione') for r in records if r.get('stagione')})
    missing = [n for n in range(seasons[0], seasons[-1] + 1) if n not in seasons] if seasons else []
    played = _played_lines(careers)
    franchise = []
    for team in dict.fromkeys(r.get('squadra') for r in records if r.get('squadra')):
        franchise += [dict(row, team=team) for row in _ranks(key, _totals_by_player(played, team), False)]
    out = _identity(key, records, info, status, years, starting_year)
    active = status in ('Active', 'Free agent')
    out.update({
        'season_count': len(seasons), 'last_seasons': CONFIG.DATABASE.LAST_SEASONS,
        'retired_year': out['last_year'] if status == 'Retired' else None,
        'career': {'gp': career['gp'] if career else 0, 'pts_pg': career['s']['pts_pg'] if career else None,
                   'reb_pg': career['s']['reb_pg'] if career else None,
                   'ast_pg': career['s']['ast_pg'] if career else None,
                   'titles': _titles(records), 'all_star': counts.get('All-Star', 0), 'awards': counts},
        'rs': rs, 'po': lines_of(records, 'po', years, starting_year),
        'career_rs': career, 'career_po': career_line(records, 'po'),
        'best': ({'season': best['season'], 'year': best['year'], 'pts_pg': best['s']['pts_pg'],
                  'awards': best['awards']} if best else None),
        'current': rs[-1] if active and rs and rs[-1]['season'] == latest_season(careers) else None,
        'progression': [dict({'year': ln['year'], 'age': ln['age'], 'ovr': ln['ovr'], 'pot': ln['pot'],
                              'champion': ln['champion']}, **{k + '_pg': ln['s'][k + '_pg'] for k in COUNTING})
                        for ln in rs],
        'awards': [{'year': year(r), 'award': a, 'team': r.get('squadra')}
                   for r in records for a in (r.get('premi') or r.get('awards') or [])],
        'titles': [{'year': year(r), 'team': r.get('squadra')} for r in records if r.get('is_champion')],
        'ranks': {'league': _ranks(key, _totals_by_player(played), True), 'franchise': franchise},
        'missing_years': [year_for(n, years, starting_year) for n in missing],
    })
    return out


def _seasons_in(careers):
    """Season number -> True when any record of it holds a full line."""
    out = {}
    for raw in careers.values():
        for r in _records(raw):
            n = r.get('stagione')
            if n:
                out[n] = out.get(n, False) or bool(r.get('full_rs'))
    return out


def _games_base(rows):
    """A full season's games for this list: a high percentile of games played, not the maximum (two players saved
    under one name add up to ~2x the games)."""
    games = sorted(r['line']['gp'] for r in rows)
    return games[int(CONFIG.DATABASE.GAMES_BASE_PERCENTILE * (len(games) - 1))] if games else 0


def _leaders(rows):
    """Stat -> top names among players with at least LEADER_GP_SHARE of the most games played that season."""
    most = _games_base(rows)
    pool = [r for r in rows if r['line']['gp'] and r['line']['gp'] >= CONFIG.DATABASE.LEADER_GP_SHARE * most]
    out = {}
    for stat in LEADER_STATS:
        ranked = sorted((r for r in pool if r['line']['s'][stat] is not None),
                        key=lambda r: (-r['line']['s'][stat], r['name']))
        out[stat] = [{'slug': r['slug'], 'name': r['name'], 'value': r['line']['s'][stat]}
                     for r in ranked[:CONFIG.ANALYTICS.LEADERS_PER_TILE]]
    return out


def season_view(careers, season, kind, years, starting_year, user_team):
    """Every player line of one season (None = the latest), with leaders and the champion."""
    careers = careers or {}
    kind = 'po' if kind == 'po' else 'rs'
    full_by_season = _seasons_in(careers)
    seasons = [{'season': n, 'year': year_for(n, years, starting_year), 'full': full_by_season[n]}
               for n in sorted(full_by_season, reverse=True)]
    if season not in full_by_season:
        season = seasons[0]['season'] if seasons else None
    year = year_for(season, years, starting_year)
    rows, champion = [], None
    for key, raw in careers.items():
        for r in _records(raw):
            if r.get('stagione') != season:
                continue
            if r.get('is_champion'):
                champion = r.get('squadra')
            ln = season_line(r, kind, year)
            if ln and ln['gp']:
                rows.append({'slug': key, 'name': r.get('nome') or career_name(key, raw), 'line': ln})
    rows.sort(key=lambda r: (-(r['line']['s']['pts_pg'] or 0), r['name']))
    # League Analytics' qualified rule, with _games_base() standing in for the team's games; only full
    # lines have minutes (None otherwise).
    most = _games_base(rows)
    a = CONFIG.ANALYTICS
    for r in rows:
        mpg = r['line']['s']['mpg']
        r['qualified'] = None if mpg is None else (r['line']['gp'] >= a.QUALIFY_GP_SHARE * most and mpg >= a.QUALIFY_MPG)
    return {'season': season, 'year': year, 'kind': kind, 'seasons': seasons,
            'full': bool(season and full_by_season.get(season) and kind == 'rs'),
            'rows': rows, 'leaders': _leaders(rows), 'champion': champion, 'user_team': user_team}


def _number(value):
    try:
        return None if value is None or value == '' else float(value)
    except (TypeError, ValueError):
        return None


def _conditions(raw, allowed):
    out = []
    for c in (raw or [])[:CONFIG.DATABASE.FINDER_MAX_CONDITIONS]:
        if not isinstance(c, dict) or c.get('stat') not in allowed or c.get('op') not in ('>=', '<='):
            continue
        value = _number(c.get('value'))
        if value is not None:
            out.append((c['stat'], c['op'], value))
    return out


def _passes(value_of, conditions):
    """A None value fails every condition (`<=` included): an unsaved stat never matches."""
    for stat, op, value in conditions:
        v = value_of(stat)
        if v is None or (v < value if op == '>=' else v > value):
            return False
    return True


def _season_filter(q, user_team, years, starting_year):
    team = user_team if q.get('team') == '__user__' else q.get('team')
    year_from, year_to = _number(q.get('year_from')), _number(q.get('year_to'))
    age_min, age_max = _number(q.get('age_min')), _number(q.get('age_max'))
    award = q.get('award')

    def keep(r):
        year = _year(r, years, starting_year)
        age = r.get('eta')
        awards = [AWARD_ALIASES.get(a, a) for a in (r.get('premi') or r.get('awards') or [])]
        return not ((year_from is not None and (year is None or year < year_from))
                    or (year_to is not None and (year is None or year > year_to))
                    or (age_min is not None and (age is None or age < age_min))
                    or (age_max is not None and (age is None or age > age_max))
                    or (team and r.get('squadra') != team)
                    or (q.get('pos') and r.get('ruolo') != q['pos'])
                    or (_flag(q.get('champion'), False) and not r.get('is_champion'))
                    or (award and award not in awards))
    return keep


def _note(keys, kind, careers, years, starting_year):
    """(note, first year with full lines) when a searched stat exists only in full lines."""
    if not any(k not in ALWAYS_KEYS for k in keys):
        return None, None
    full = sorted(n for n, has in _seasons_in(careers).items() if has) if kind == 'rs' else []
    if not full:
        return 'No season in this save has this stat yet.', None
    first = year_for(full[0], years, starting_year)
    return f'Only seasons from {first} have this stat.', first


def finder_view(careers, query, live, retired, years, starting_year, user_team):
    """Stat Finder: matching player-seasons (or careers summed over matching seasons), ranked, top FINDER_LIMIT."""
    q = query or {}
    careers, live, retired = careers or {}, live or {}, retired or set()
    kind = 'po' if q.get('kind') == 'po' else 'rs'
    careers_mode = q.get('mode') == 'careers'
    allowed = STAT_KEYS + CAREER_EXTRA if careers_mode else STAT_KEYS
    conditions = _conditions(q.get('conditions'), allowed)
    rank_by = q.get('rank_by') if q.get('rank_by') in allowed else 'pts_pg'
    min_gp = _number(q.get('min_gp')) or 0
    status = q.get('status')
    keep = _season_filter(q, user_team, years, starting_year)
    rows = []
    for key, raw in careers.items():
        if status and status != 'All' and _status(key, live, retired) != status:
            continue
        records = sorted((r for r in _records(raw) if keep(r)), key=lambda r: r.get('stagione') or 0)
        name = (live.get(key) or {}).get('name') or career_name(key, raw)
        if careers_mode:
            career = career_line(records, kind)
            if not career or career['gp'] < min_gp:
                continue
            numbers = [r.get('stagione') for r in records if r.get('stagione')]
            row = {'slug': key, 'name': name, 'seasons': career['seasons'],
                   'first_year': year_for(min(numbers), years, starting_year) if numbers else None,
                   'last_year': year_for(max(numbers), years, starting_year) if numbers else None,
                   'career': career, 'titles': _titles(records), 'all_star': award_counts(records).get('All-Star', 0)}
            value_of = (lambda stat, row=row: row[stat] if stat in CAREER_EXTRA else row['career']['s'][stat])
            if _passes(value_of, conditions):
                rows.append((value_of(rank_by), row))
            continue
        for r in records:
            ln = season_line(r, kind, _year(r, years, starting_year))
            if not ln or not ln['gp'] or ln['gp'] < min_gp:
                continue
            if _passes(lambda stat, ln=ln: ln['s'][stat], conditions):
                rows.append((ln['s'][rank_by], {'slug': key, 'name': name, 'line': ln}))
    desc = _flag(q.get('desc'), True)
    have = sorted((x for x in rows if x[0] is not None), key=lambda x: x[1]['name'])
    have.sort(key=lambda x: x[0], reverse=desc)
    ordered = [row for _v, row in have] + sorted((row for v, row in rows if v is None), key=lambda row: row['name'])
    note, full_from = _note([s for s, _op, _v in conditions] + [rank_by], kind, careers, years, starting_year)
    return {'mode': 'careers' if careers_mode else 'seasons', 'kind': kind, 'rank_by': rank_by, 'desc': desc,
            'rows': ordered[:CONFIG.DATABASE.FINDER_LIMIT], 'total': len(ordered), 'note': note, 'full_from': full_from}
