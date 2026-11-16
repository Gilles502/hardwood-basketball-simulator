"""AI GM layer 3: the owner's verdict on the GM (core/front_office/owners.py)."""
import dataclasses
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONFIG
from core.front_office import owners
from core.front_office.models import CpuGM, TeamPlan
from core.front_office.owners import fire_gm_roll, gm_fire_reason
from core.front_office.state import FrontOfficeState

FO = CONFIG.FRONT_OFFICE


class Fixed:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def row(year, wins, expected=45, coach_fired=False, champion=False, plan="CONTENDER", plan_start=None):
    out = {"year": year, "wins": wins, "losses": 82 - wins, "expected": expected, "playoffs": False,
           "champion": champion, "plan": plan, "gm_id": "g1", "coach_fired": coach_fired}
    if plan_start is not None:
        out["plan_start"] = plan_start
    return out


def rebuild(year, wins):
    return row(year, wins, plan="REBUILDER")


BAD, FINE = 35, 46


def setup(rows, plan="CONTENDER", held=1, tenure=5, owner="Bilanciato", user_role="spectator", interim=False):
    team = SimpleNamespace(nome="A", personalita_proprietario=owner)
    user = team if user_role in ("gm_coach", "only_gm") else None
    torneo = SimpleNamespace(squadre=[team], campione=None, user_role=user_role, squadra_giocatore=user,
                             anno_corrente=2010, starting_year=2002, season_number=9)
    fo = FrontOfficeState()
    gm = CpuGM(gm_id="g1", name="G", age=50, years_as_gm=5, traits=[], skills={}, team="A", tenure=tenure,
               interim=interim)
    fo.gms["g1"] = gm
    fo.seats["A"] = "g1"
    fo.plans["A"] = TeamPlan(state=plan, since_year=2000, seasons_held=held, reason="t", history=[])
    fo.records["A"] = rows
    torneo.front_office = fo
    return torneo, fo, team, gm


def verdict(*args, coach_only=False, **kw):
    torneo, fo, team, gm = setup(*args, **kw)
    return gm_fire_reason(torneo, fo, team, gm, coach_only)


class OwnerTests(unittest.TestCase):
    def test_new_gm_never_fired(self):
        rows = [row(2007 + i, BAD) for i in range(4)]
        self.assertIsNone(verdict(rows, tenure=1))

    def test_interim_never_fired(self):
        rows = [row(2007 + i, BAD) for i in range(4)]
        self.assertIsNone(verdict(rows, interim=True))

    def test_champion_never_fired(self):
        rows = [row(2007 + i, BAD) for i in range(3)] + [row(2010, BAD, champion=True)]
        self.assertIsNone(verdict(rows))
        torneo, fo, team, gm = setup([row(2007 + i, BAD) for i in range(4)])
        torneo.campione = team
        self.assertIsNone(gm_fire_reason(torneo, fo, team, gm, False))

    def test_after_coach_change_rule(self):
        rows = [row(2008, FINE, coach_fired=True), row(2009, BAD), row(2010, BAD)]
        self.assertIn("coaching change", verdict(rows))
        rows[1] = row(2009, FINE + 5)
        self.assertIsNone(verdict(rows))

    def test_reason_text_singular_and_plural(self):
        rows = [row(2009, FINE, coach_fired=True), row(2010, BAD)]
        with mock.patch.object(owners, "CONFIG", dataclasses.replace(
                CONFIG, FRONT_OFFICE=dataclasses.replace(FO, GM_FIRE_AFTER_COACH_SEASONS=1))):
            self.assertEqual(verdict(rows), "1 season below expectations after the coaching change")
        rows = [row(2008, FINE, coach_fired=True), row(2009, BAD), row(2010, BAD)]
        self.assertEqual(verdict(rows), "2 seasons below expectations after the coaching change")

    def test_long_run_rule(self):
        rows = [row(2007 + i, BAD) for i in range(4)]
        self.assertIn("4 straight seasons", verdict(rows))
        rows[1] = row(2008, FINE)
        self.assertIsNone(verdict(rows))

    def test_rebuilder_on_schedule_kept(self):
        rows = [rebuild(2008, 20), rebuild(2009, 18), rebuild(2010, 15)]
        self.assertIsNone(verdict(rows, plan="REBUILDER", held=2))

    def test_stalled_rebuild_fired(self):
        rows = [rebuild(2008, 20), rebuild(2009, 22), rebuild(2010, 19)]
        self.assertIn("rebuild", verdict(rows, plan="REBUILDER", held=9))
        rows = [rebuild(2008, 20), rebuild(2009, 22), rebuild(2010, 28)]
        self.assertIsNone(verdict(rows, plan="REBUILDER", held=9))

    def test_stalled_rebuild_needs_three_seasons(self):
        self.assertIsNone(verdict([rebuild(2009, 22), rebuild(2010, 19)], plan="REBUILDER", held=9))

    def test_stalled_rebuild_needs_rebuild_seasons(self):
        rows = [row(2008, 20, expected=21), rebuild(2009, 22), rebuild(2010, 19)]   # 2008 was a win-now season
        self.assertIsNone(verdict(rows, plan="REBUILDER", held=9))

    def test_deadline_collapsed_contender_judged_as_win_now(self):
        # Every season started as a contender and collapsed into a (fresh, on-schedule) rebuild at the deadline.
        collapsed = dict(plan="REBUILDER", plan_start="CONTENDER")
        rows = [row(2007 + i, BAD, **collapsed) for i in range(4)]
        self.assertIn("4 straight seasons", verdict(rows, plan="REBUILDER", held=1))
        rows = [row(2008, FINE, coach_fired=True), row(2009, BAD, **collapsed), row(2010, BAD, **collapsed)]
        self.assertIn("coaching change", verdict(rows, plan="REBUILDER", held=1))

    def test_rebuild_seasons_never_feed_the_win_now_rules(self):
        # A rebuild that surprised into a playoff plan: its rebuild seasons are not win-now failures.
        rows = [row(2007 + i, BAD, plan_start="REBUILDER") for i in range(4)]
        self.assertIsNone(verdict(rows, plan="PLAYOFF", held=1))
        rows = [row(2008, FINE, coach_fired=True), row(2009, BAD, plan_start="REBUILDER"),
                row(2010, BAD, plan_start="REBUILDER")]
        self.assertIsNone(verdict(rows, plan="PLAYOFF", held=1))

    def test_coach_only_team_stalled_rebuild_kept(self):
        rows = [rebuild(2008, 20), rebuild(2009, 22), rebuild(2010, 19)]
        self.assertIsNone(verdict(rows, plan="REBUILDER", held=9, coach_only=True, user_role="only_coach"))

    def test_ricostruttore_waits_a_season_longer_after_coach_change(self):
        two_bad = [row(2008, FINE, coach_fired=True), row(2009, BAD), row(2010, BAD)]
        self.assertIsNone(verdict(two_bad, owner="Ricostruttore"))
        three_bad = [row(2007, FINE, coach_fired=True), row(2008, BAD), row(2009, BAD), row(2010, BAD)]
        self.assertEqual(verdict(three_bad, owner="Ricostruttore"),
                         "3 seasons below expectations after the coaching change")

    def test_coach_only_team_long_run_only(self):
        rows = [row(2008, FINE, coach_fired=True), row(2009, BAD), row(2010, BAD)]
        self.assertIsNone(verdict(rows, coach_only=True, user_role="only_coach"))
        rows = [row(2007 + i, BAD) for i in range(4)]
        self.assertIsNotNone(verdict(rows, coach_only=True, user_role="only_coach"))

    def test_esigente_fires_a_season_earlier(self):
        rows = [row(2007 + i, BAD) for i in range(3)]
        self.assertIsNone(verdict(rows, owner="Bilanciato"))
        self.assertIn("3 straight seasons", verdict(rows, owner="Esigente"))
        self.assertIsNone(verdict(rows, owner="Ricostruttore"))

    def test_user_team_never_judged(self):
        rows = [row(2007 + i, BAD) for i in range(4)]
        self.assertIsNone(verdict(rows, user_role="gm_coach"))

    def test_other_tenure_rows_ignored(self):
        rows = [dict(row(2007 + i, BAD), gm_id="old") for i in range(4)]
        self.assertIsNone(verdict(rows))

    def test_fire_roll(self):
        self.assertTrue(fire_gm_roll("reason", Fixed(0.69)))
        self.assertFalse(fire_gm_roll("reason", Fixed(0.71)))
        self.assertFalse(fire_gm_roll(None, Fixed(0.0)))


if __name__ == "__main__":
    unittest.main()
