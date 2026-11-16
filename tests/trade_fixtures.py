"""Shared builders for trade tests: players, teams, GMs, a fake tournament and a TradeFinder."""
from types import SimpleNamespace

from core.config import CONFIG
from core.front_office.era_lines import EraLines
from core.front_office.models import CpuGM, TeamPlan
from core.front_office.state import FrontOfficeState
from core.models import Giocatore
from trades.trade_finder import TradeFinder

FO = CONFIG.FRONT_OFFICE


def abilities(value=60, **over):
    names = {a for attrs in FO.COACH_STYLE_ATTRIBUTES.values() for a in attrs}
    names |= {a for attrs in FO.PROFILE_ATTRIBUTES.values() for a in attrs}
    values = {n: value for n in names}
    values.update(over)
    return SimpleNamespace(**values)


def make_player(name, ovr=70, age=27, salary=5.0, years=2, role="SG", pot=None, team_years=1, abil=None):
    p = Giocatore.__new__(Giocatore)
    p.nome, p.valutazione, p.eta, p.ruolo = name, ovr, age, role  # ovr is an alias of valutazione
    p.potenziale = pot if pot is not None else ovr
    p.morale, p.anni_nella_squadra, p.giorni_cooldown_scambio, p.is_untouchable = 80, team_years, 0, False
    p.abilita = abil if abil is not None else abilities()
    p.contract = SimpleNamespace(salario_annuale=salary, anni_rimanenti=years, player_option=False, team_option=False)
    return p


def make_team(name, ovrs=None, wins=0, losses=0, style=None):
    ovrs = ovrs if ovrs is not None else [70] * 13
    team = SimpleNamespace(nome=name, roster=[make_player(f"{name}-{i}", ovr=o) for i, o in enumerate(ovrs)],
                           vittorie=wins, sconfitte=losses, payroll=50.0, salary_cap_space=0.0,
                           coach=SimpleNamespace(stile_gioco=style) if style else None,
                           scegli_quintetto_iniziale=lambda: None, log_financial_event=lambda *a, **k: None)
    team.ha_bisogno_di_ruolo = lambda role: False
    team.check_trade_salary_match = lambda incoming, outgoing: (True, "")
    team.analizza_roster_per_upgrade = lambda: []
    return team


def make_gm(gm_id, traits=(), trade=60):
    return CpuGM(gm_id=gm_id, name=gm_id, age=45, years_as_gm=3, traits=list(traits),
                 skills={"trade": trade, "contracts": 60, "draft": 60})


def make_torneo(teams, user_team=None, plans=None, gms=None, role=None, statuses=None, with_fo=True):
    """`gms`: team name -> CpuGM seated there. `statuses`: what _determina_stato_squadra answers."""
    torneo = SimpleNamespace(
        squadre=teams, season_number=2, starting_year=2002, anno_corrente=2003, fase_torneo="SEASON",
        user_role=role or ("gm_coach" if user_team else "spectator"),
        squadra_giocatore=next((t for t in teams if t.nome == user_team), None),
        pick_ownership={1: {}, 2: {}}, pick_protections={1: {}, 2: {}}, offseason_log_data={},
        trade_difficulty="realistic", salary_cap=100.0,
        luxury_tax_threshold=119.4, min_salary=2.3, mle_value=8.1,   # main.py ratios at a 100 cap
    )
    if with_fo:
        fo = FrontOfficeState()
        for name, state in (plans or {}).items():
            fo.plans[name] = TeamPlan(state=state, since_year=2002, seasons_held=1, reason="", history=[])
        for name, gm in (gms or {}).items():
            gm.team = name
            fo.gms[gm.gm_id] = gm
            fo.seats[name] = gm.gm_id
        torneo.front_office = fo
    statuses = statuses or {}
    torneo._determina_stato_squadra = lambda s: statuses.get(s.nome, "Mediocre")
    return torneo


def finder(torneo):
    return TradeFinder(torneo, torneo.squadre, torneo.squadra_giocatore)


def era_of(star=85, core=80, starter=75, rotation=70, bench=65, cap=40.27, tax=60.0, pick_scale=1.0, year=2003):
    """Era lines of a 2002-like league by default (star 85, core 80): every old threshold maps to itself."""
    t = CONFIG.TRADES
    return EraLines(year=year, cap=cap, tax=tax, minimum=0.9, mle=3.2, no_cap=False, star=star, core=core,
                    starter=starter, rotation=rotation, bench=bench,
                    salary_pcts={t.MID_SALARY_PCT: 3.0, t.HIGH_SALARY_PCT: 8.0}, pick_scale=pick_scale)


def roster_team(name, spec):
    """A team whose roster is [(role, ovr), ...]."""
    team = make_team(name, ovrs=[])
    team.roster = [make_player(f"{name}-{role}{i}", ovr=ovr, role=role) for i, (role, ovr) in enumerate(spec)]
    return team


# The realistic price the hand-set values of engine and regression tests were written against (the pre-gate
# calibration). Gate tuning of CONFIG.TRADES.DIFFICULTY (the volume knob) must not move them: the multiplier itself
# is covered by the acceptance tests that read CONFIG.
PINNED_DIFFICULTY = {"easy": (0.80, 0.65), "realistic": (0.94, 0.82), "hardcore": (1.22, 1.05)}


def pin_difficulty(test):
    """Patches the trade finder's CONFIG with PINNED_DIFFICULTY for the rest of `test`."""
    import dataclasses
    from unittest import mock
    import trades.trade_finder as trade_finder_module
    config = dataclasses.replace(CONFIG, TRADES=dataclasses.replace(CONFIG.TRADES, DIFFICULTY=dict(PINNED_DIFFICULTY)))
    patch = mock.patch.object(trade_finder_module, "CONFIG", config)
    patch.start()
    test.addCleanup(patch.stop)
