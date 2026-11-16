"""Rotations > Roles: the user moves a player to another role (Giocatore.change_role, /api/team-manager/change-roles)."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock

from core.config import CONFIG
from core.models import Giocatore
from tests.trade_fixtures import make_player

# Ratings relative to a player whose original role is PF: base OVR + D[role] - D[original role].
D = {"PG": -15, "SG": -6, "SF": 2, "PF": 0, "C": -5}


def fake_ratings(self):
    origin = getattr(self, "ruolo_originale", None) or self.ruolo
    base = self.valutazione - int(getattr(self, "role_ovr_shift", 0) or 0)
    return {r: base + D[r] - D[origin] for r in D}


def player(role="PF", ovr=85, pot=88):
    p = make_player("Kirilenko", ovr=ovr, age=22, role=role, pot=pot)
    p._trade_value_cache = None
    return p


class ChangeRoleTests(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(Giocatore, "_role_ratings", autospec=True, side_effect=fake_ratings)
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_ovr_becomes_his_rating_at_the_new_role_and_potential_follows(self):
        p = player()
        p.change_role("PG")
        self.assertEqual((p.ruolo, p.ovr, p.potenziale, p.ruolo_originale), ("PG", 70, 73, "PF"))

    def test_a_role_change_raises_the_ovr_at_most_by_the_cap(self):
        p = player()
        with mock.patch.dict(D, {"SF": 6}):
            p.change_role("SF")
        self.assertEqual(p.ovr, 85 + CONFIG.POSITIONS.ROLE_CHANGE_MAX_GAIN)

    def test_moving_him_back_gives_exactly_the_old_numbers(self):
        p = player()
        p.change_role("C")
        p.change_role("PF")
        self.assertEqual((p.ruolo, p.ovr, p.potenziale, p.ruolo_originale, p.role_ovr_shift), ("PF", 85, 88, None, 0))

    def test_the_original_role_is_kept_over_several_moves(self):
        p = player()
        p.change_role("SF")
        p.change_role("C")
        self.assertEqual((p.ruolo, p.ovr, p.ruolo_originale), ("C", 80, "PF"))

    def test_progression_after_a_move_carries_over_when_he_goes_back(self):
        p = player()
        p.change_role("SF")             # 87
        p.valutazione += 1              # a good summer at SF: 88
        p.change_role("PF")
        self.assertEqual(p.ovr, 86)     # his PF OVR grew by the same point

    def test_ovr_at_role_previews_the_change(self):
        p = player()
        self.assertEqual({r: p.ovr_at_role(r) for r in D}, {"PG": 70, "SG": 79, "SF": 87, "PF": 85, "C": 80})

    def test_same_role_changes_nothing_and_an_unknown_role_is_refused(self):
        p = player()
        p.change_role("PF")
        self.assertEqual((p.ovr, getattr(p, "ruolo_originale", None)), (85, None))
        with self.assertRaises(ValueError):
            p.change_role("XX")

    def test_italian_codes_are_accepted(self):
        p = player()
        p.change_role("AP")   # legacy Italian small forward
        self.assertEqual(p.ruolo, "SF")


class CalibrationTests(unittest.TestCase):
    """Real ratings from the abilities: a big man is no point guard any more."""
    def big_man(self):
        from tests.trade_fixtures import abilities
        abil = abilities(70, strength=88, interior_defense_rating=88, block_rating=85, defensive_rebound_rating=88,
                         offensive_rebound_rating=85, post_control_rating=82, close_shot_rating=80,
                         ball_handling=55, speed=55, three_point_shot_rating=40, perimeter_defense_rating=55,
                         passing_vision=65, passing_accuracy=65, shot_iq=75, offensive_iq_rating=75,
                         mid_range_shot_rating=60, defensive_iq_rating=78, stamina=70)
        p = make_player("Big", ovr=85, role="C", abil=abil)
        p.valutazioni_posizionali = {}
        p._calibra_e_calcola_posizioni()
        return p

    def test_the_original_role_keeps_his_ovr_and_guards_rate_far_lower(self):
        p = self.big_man()
        r = p.valutazioni_posizionali
        self.assertEqual(r["C"], 85)
        self.assertLess(r["PG"], 75)
        self.assertLess(r["SG"], 75)
        self.assertGreaterEqual(r["PF"], 80)

    def test_moving_a_big_man_to_point_guard_costs_him(self):
        p = self.big_man()
        p.change_role("PG")
        self.assertLess(p.ovr, 75)
        p.change_role("C")
        self.assertEqual(p.ovr, 85)


class ChangeRolesRouteTests(unittest.TestCase):
    def setUp(self):
        import contextlib
        import io
        patch = mock.patch.object(Giocatore, "_role_ratings", autospec=True, side_effect=fake_ratings)
        patch.start()
        self.addCleanup(patch.stop)
        with contextlib.redirect_stdout(io.StringIO()):
            import server
        self.server = server
        self._saved = server.SIMULATION_TOURNAMENT
        self.p = player()
        self.calls = []
        team = SimpleNamespace(nome="Utah Summit", roster=[self.p], scegli_quintetto_iniziale=lambda: self.calls.append(1))
        server.SIMULATION_TOURNAMENT = SimpleNamespace(squadra_giocatore=team)
        self.client = server.app.test_client()

    def tearDown(self):
        self.server.SIMULATION_TOURNAMENT = self._saved

    def test_it_changes_the_role_and_picks_the_five_again(self):
        data = self.client.post('/api/team-manager/change-roles', json={"roles": {"Kirilenko": "SF"}}).get_json()
        self.assertTrue(data["success"])
        self.assertEqual([(c["nome"], c["ruolo"], c["ovr"], c["ruolo_originale"]) for c in data["changed"]],
                         [("Kirilenko", "SF", 87, "PF")])
        self.assertEqual(self.calls, [1])

    def test_a_player_not_on_the_roster_or_a_bad_role_is_refused(self):
        r = self.client.post('/api/team-manager/change-roles', json={"roles": {"Nobody": "SF"}})
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/team-manager/change-roles', json={"roles": {"Kirilenko": "Wing"}})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.p.ruolo, "PF")


class SaveRoundTripTests(unittest.TestCase):
    @mock.patch.object(Giocatore, "_role_ratings", autospec=True, side_effect=fake_ratings)
    def test_the_original_role_survives_a_save(self, _r):
        from core.save_manager import serialize_player
        p = player()
        p.change_role("SF")
        data = serialize_player(p)
        self.assertEqual((data["ruolo"], data["valutazione"], data["ruolo_originale"], data["role_ovr_shift"]),
                         ("SF", 87, "PF", 2))


if __name__ == "__main__":
    unittest.main()
