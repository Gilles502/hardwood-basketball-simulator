"""All-Star Weekend pure helpers: player lines, exhibition games, dunk scores, sophomores, host city.

No tournament or Flask imports; every tunable lives in CONFIG.ALL_STAR.
"""
from core.config import CONFIG


def player_line(p) -> dict:
    """Display line of a player from the season stats and ratings."""
    st = p.season_stats
    ab = p.abilita
    gp = st.partite_giocate or 0

    def per_game(total):
        return round(total / gp, 1) if gp else 0.0

    att = st.tiri_tentati_3 or 0
    team = getattr(p.squadra, 'nome', None) if getattr(p, 'squadra', None) else None
    athl = (ab.vertical + ab.speed + ab.acceleration) / 3
    return {
        'name': p.nome, 'team': team or 'FA', 'pos': p.ruolo, 'age': p.eta, 'ovr': p.valutazione,
        'gp': gp, 'ppg': per_game(st.punti), 'rpg': per_game(st.rimbalzi), 'apg': per_game(st.assist),
        'tpm': per_game(st.tiri_fatti_3),
        'tp_pct': round(100.0 * st.tiri_fatti_3 / att, 1) if att else None,
        'r3': ab.three_point_shot_rating, 'dunk': ab.dunk_rating, 'athl': round(athl, 1),
    }


def _mean_ovr(lines):
    return sum(x['ovr'] for x in lines) / len(lines) if lines else 0.0


def _play_side(label, lines, total, rng):
    cfg = CONFIG.ALL_STAR
    weights = [max(cfg.MIN_SHARE_WEIGHT,
                   (x['ppg'] + cfg.OVR_SHARE_WEIGHT * x['ovr']) ** cfg.SHARE_POWER * rng.uniform(*cfg.SHARE_NOISE))
               for x in lines]
    wsum = sum(weights) or 1.0
    out = []
    for x, w in zip(lines, weights):
        pts = round(total * w / wsum)

        def box(key):
            return max(0, round(x[key] * cfg.BOX_STAT_SCALE * rng.uniform(*cfg.BOX_NOISE)))
        out.append({'name': x['name'], 'team': x['team'], 'pts': pts, 'reb': box('rpg'),
                    'ast': box('apg'), 'tpm': min(box('tpm'), pts // 3)})
    return {'label': label, 'score': 0, 'lines': out}


def _finish(s):
    s['lines'].sort(key=lambda r: -r['pts'])
    s['score'] = sum(r['pts'] for r in s['lines'])


def exhibition_game(sides, total_range, rng) -> dict:
    """Play a two-side exhibition game; returns box score, winner and MVP. Never a tie."""
    (la, lines_a), (lb, lines_b) = sides
    gap = _mean_ovr(lines_a) - _mean_ovr(lines_b)
    played = []
    for label, lines, sign in ((la, lines_a, 1), (lb, lines_b, -1)):
        total = rng.randint(*total_range) + sign * gap * CONFIG.ALL_STAR.OVR_TOTAL_NUDGE
        played.append(_play_side(label, lines, max(1, round(total)), rng))
    for s in played:
        _finish(s)
    a, b = played
    if a['score'] == b['score']:
        better = a if _mean_ovr(lines_a) >= _mean_ovr(lines_b) else b
        if better['lines']:
            better['lines'][0]['pts'] += CONFIG.ALL_STAR.TIE_BREAK_POINTS
        _finish(better)
    winner = a if a['score'] > b['score'] else b
    top = winner['lines'][0]
    mvp = {'name': top['name'], 'team': top['team'], 'label': winner['label'], 'pts': top['pts'],
           'reb': top['reb'], 'ast': top['ast'], 'tpm': top['tpm']}
    return {'sides': played, 'winner': winner['label'], 'mvp': mvp}


def dunk_score(line: dict, rng) -> int:
    """One judges' score for a dunk, between DUNK_MIN and DUNK_MAX."""
    cfg = CONFIG.ALL_STAR
    skill = cfg.DUNK_RATING_WEIGHT * line['dunk'] + (1 - cfg.DUNK_RATING_WEIGHT) * line['athl']
    raw = cfg.DUNK_BASE + (skill - 50) * cfg.DUNK_SKILL_SCALE + rng.uniform(-cfg.DUNK_NOISE, cfg.DUNK_NOISE)
    return max(cfg.DUNK_MIN, min(cfg.DUNK_MAX, round(raw)))


def pick_sophomores(candidates, last_rookies, n, fallback_age) -> list:
    """Last year's rookies first (best PPG first), topped up by the youngest best scorers."""
    by_name = {c['name']: c for c in candidates}
    known = sorted((by_name[nm] for nm in dict.fromkeys(last_rookies) if nm in by_name),
                   key=lambda c: -c['ppg'])[:n]
    taken = {c['name'] for c in known}
    young = sorted((c for c in candidates if c['age'] <= fallback_age and c['name'] not in taken),
                   key=lambda c: -c['ppg'])
    return known + young[:max(0, n - len(known))]


def pick_host(team_cities, recent_hosts, rng) -> str:
    """A host city not used recently; any city when all were."""
    fresh = [c for c in team_cities if c not in recent_hosts]
    return rng.choice(fresh or list(team_cities))


def _three_point_score(line, score_range, divisor, clamp, rng) -> int:
    cfg = CONFIG.ALL_STAR
    raw = rng.randint(*score_range) + int((line['r3'] - cfg.THREE_PT_RATING_BASE) / divisor)
    return max(clamp[0], min(clamp[1], raw))


def _settle_final(final, round1, shoot):
    """Sort the final; when the top scores tie, the tied leaders go again (`shoot(name)` -> one entry)
    until one is ahead, at most TIEBREAK_MAX_ROUNDS times; still level, the better round-1 rank wins.
    Returns the deciding tiebreak round (winner first) or None."""
    final.sort(key=lambda e: -e['score'])
    if len(final) < 2 or final[0]['score'] != final[1]['score']:
        return None
    rank = {e['name']: i for i, e in enumerate(round1)}
    tied = [e['name'] for e in final if e['score'] == final[0]['score']]
    tiebreak = None
    for _ in range(CONFIG.ALL_STAR.TIEBREAK_MAX_ROUNDS):
        tiebreak = [shoot(nm) for nm in tied]
        tiebreak.sort(key=lambda e: (-e['score'], rank[e['name']]))
        if tiebreak[0]['score'] != tiebreak[1]['score']:
            break
    winner = tiebreak[0]['name']
    final.sort(key=lambda e: (-e['score'], e['name'] != winner))
    return tiebreak


def _three_point_contest(shooters, rng) -> dict:
    cfg = CONFIG.ALL_STAR
    by_name = {x['name']: x for x in shooters}

    def final_score(nm):
        return _three_point_score(by_name[nm], cfg.THREE_PT_FINAL_RANGE, cfg.THREE_PT_FINAL_DIVISOR,
                                  cfg.THREE_PT_FINAL_CLAMP, rng)
    round1 = [{'name': x['name'], 'team': x['team'], 'tp_pct': x['tp_pct'], 'finalist': False,
               'score': _three_point_score(x, cfg.THREE_PT_ROUND1_RANGE, cfg.THREE_PT_ROUND1_DIVISOR,
                                           cfg.THREE_PT_ROUND1_CLAMP, rng)} for x in shooters]
    # Equal round-1 scores (also at the finalist cutoff): the better 3-point rating, then the name.
    round1.sort(key=lambda e: (-e['score'], -by_name[e['name']]['r3'], e['name']))
    final = []
    for e in round1[:cfg.THREE_PT_FINALISTS]:
        e['finalist'] = True
        final.append({'name': e['name'], 'team': e['team'], 'score': final_score(e['name'])})
    tiebreak = _settle_final(final, round1, lambda nm: {'name': nm, 'score': final_score(nm)})
    return {'round1': round1, 'final': final, 'tiebreak': tiebreak,
            'winner': final[0]['name'] if final else None}


def _dunk_contest(dunkers, rng) -> dict:
    cfg = CONFIG.ALL_STAR
    by_name = {x['name']: x for x in dunkers}
    round1 = []
    for x in dunkers:
        names = rng.sample(cfg.DUNK_NAMES, cfg.DUNKS_ROUND1)
        dunks = [{'name': nm, 'score': dunk_score(x, rng)} for nm in names]
        round1.append({'name': x['name'], 'team': x['team'], 'dunks': dunks,
                       'total': sum(d['score'] for d in dunks), 'finalist': False})
    # Equal round-1 totals (also at the finalist cutoff): the better dunk rating, athleticism, then the name.
    round1.sort(key=lambda e: (-e['total'], -by_name[e['name']]['dunk'], -by_name[e['name']]['athl'], e['name']))

    def one_dunk(nm):
        return {'name': nm, 'dunk': rng.choice(cfg.DUNK_NAMES), 'score': dunk_score(by_name[nm], rng)}
    final = []
    for e in round1[:cfg.DUNK_FINALISTS]:
        e['finalist'] = True
        final.append(dict(one_dunk(e['name']), team=e['team']))
    tiebreak = _settle_final(final, round1, one_dunk)
    return {'round1': round1, 'final': final, 'tiebreak': tiebreak,
            'winner': final[0]['name'] if final else None}


def _game_or_none(sides, total_range, rng):
    if any(not lines for _, lines in sides):
        return None
    return exhibition_game(sides, total_range, rng)


def play_weekend(*, season, host, selections, shooters, dunkers, rookies, sophomores, rng) -> dict:
    """Play every event of the weekend; returns one plain, JSON-ready snapshot."""
    cfg = CONFIG.ALL_STAR
    rookie_game = _game_or_none((('Rookies', rookies), ('Sophomores', sophomores)), cfg.ROOKIE_TOTAL_RANGE, rng)
    three_point = _three_point_contest(shooters, rng)
    dunk = _dunk_contest(dunkers, rng)
    sides = tuple((label, selections[key]['starters'] + selections[key]['reserves'])
                  for label, key in (('East', 'east'), ('West', 'west')))
    game = _game_or_none(sides, cfg.ALL_STAR_TOTAL_RANGE, rng)
    return {'season': season, 'host': host, 'selections': selections,
            'rookie_challenge': {'rookies': rookies, 'sophomores': sophomores, 'game': rookie_game},
            'three_point': three_point, 'dunk': dunk, 'game': game}
