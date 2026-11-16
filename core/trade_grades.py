# File: core/trade_grades.py
"""
Trade Grades Hub (Hardwood Basketball Simulator v2.1)
Replaces the old Delta Win% / Net Rating with an immediate editorial evaluation (Day-1 Trade Grades),
from A+ to F for every franchise involved in the trade, complete with Trade Value and an editorial verdict.
"""

from typing import Dict, Any, Tuple, Optional

def _evaluate_player_asset(player_info: Any, tournament: Optional[Any] = None) -> Tuple[float, str, int]:
    """
    Computes the Trade Value of a traded player considering OVR, age and potential.
    Returns: (value, name, ovr)
    """
    if isinstance(player_info, dict):
        p_name = player_info.get('name', 'Giocatore')
        ovr = player_info.get('ovr', 75)
        eta = player_info.get('eta', 26)
        pot = player_info.get('pot', ovr)
    else:
        p_name = str(player_info)
        ovr = 75
        eta = 26
        pot = 75

    # If we have the tournament, look up the real player for accurate data
    if tournament and hasattr(tournament, 'squadre'):
        found = next((p for s in tournament.squadre for p in s.roster if p.nome.lower() == p_name.lower()), None)
        if not found and hasattr(tournament, 'free_agents_pool'):
            found = next((p for p in tournament.free_agents_pool if p.nome.lower() == p_name.lower()), None)
        if found:
            ovr = found.ovr
            eta = found.eta
            pot = found.potenziale

    # Non-linear OVR valuation (superstars are worth exponentially more)
    if ovr >= 92:
        val = 110.0 + (ovr - 92) * 15.0
    elif ovr >= 87:
        val = 75.0 + (ovr - 87) * 7.0
    elif ovr >= 82:
        val = 45.0 + (ovr - 82) * 6.0
    elif ovr >= 77:
        val = 24.0 + (ovr - 77) * 4.0
    elif ovr >= 72:
        val = 12.0 + (ovr - 72) * 2.4
    else:
        val = max(4.0, (ovr - 65) * 1.2)

    # Age and potential modifier
    if eta <= 22:
        val *= 1.30
        if pot >= 84:
            val += (pot - 80) * 3.0
    elif eta <= 25:
        val *= 1.15
    elif eta <= 29:
        val *= 1.05 # Prime
    elif eta <= 32:
        val *= 0.90
    else:
        val *= 0.68 # Declining veteran

    return round(val, 1), p_name, ovr

def _evaluate_pick_asset(pick_desc: Any) -> Tuple[float, str]:
    """
    Computes the Trade Value of a draft pick.
    """
    desc = str(pick_desc)
    val = 15.0
    if "1° Giro" in desc or "1st" in desc or "Round 1" in desc or "1st Round" in desc or "R1" in desc:
        val = 42.0
        if "protetta" in desc.lower() or "protected" in desc.lower():
            val = 32.0
    elif "2° Giro" in desc or "2nd" in desc or "Round 2" in desc or "2nd Round" in desc or "R2" in desc:
        val = 12.0

    return val, desc

def calculate_trade_grades(trade_entry: Dict[str, Any], tournament: Optional[Any] = None) -> Dict[str, Any]:
    """
    Computes the grade from A+ to F for each team in the trade and determines the winner, if any.
    """
    teams_data = trade_entry.get('teams', [])
    if not teams_data:
        return trade_entry

    graded_teams = []
    best_score = -999.0
    winner_name = None

    for t_entry in teams_data:
        t_name = t_entry.get('team_name', 'Franchise')
        
        # 1. Evaluate the assets received
        rec_players = t_entry.get('players_received', [])
        rec_picks = t_entry.get('picks_received', [])
        
        val_rec_players = 0.0
        highest_ovr_rec = 0
        names_rec = []
        for p in rec_players:
            p_val, p_name, p_ovr = _evaluate_player_asset(p, tournament)
            val_rec_players += p_val
            names_rec.append(p_name)
            if p_ovr > highest_ovr_rec:
                highest_ovr_rec = p_ovr

        val_rec_picks = 0.0
        for pk in rec_picks:
            pk_val, _ = _evaluate_pick_asset(pk)
            val_rec_picks += pk_val

        total_value_received = round(val_rec_players + val_rec_picks, 1)

        # 2. Evaluate the assets sent
        sent_players = t_entry.get('players_sent', [])
        sent_picks = t_entry.get('picks_sent', [])

        val_sent_players = 0.0
        highest_ovr_sent = 0
        names_sent = []
        for p in sent_players:
            p_val, p_name, p_ovr = _evaluate_player_asset(p, tournament)
            val_sent_players += p_val
            names_sent.append(p_name)
            if p_ovr > highest_ovr_sent:
                highest_ovr_sent = p_ovr

        val_sent_picks = 0.0
        for pk in sent_picks:
            pk_val, _ = _evaluate_pick_asset(pk)
            val_sent_picks += pk_val

        total_value_sent = round(val_sent_players + val_sent_picks, 1)

        # 3. Value balance (net difference)
        net_diff = total_value_received - total_value_sent

        # 4. Grade assignment from A+ to F
        if net_diff >= 32.0:
            grade = "A+"
            grade_color = "#10b981" # Emerald
        elif net_diff >= 18.0:
            grade = "A"
            grade_color = "#34d399"
        elif net_diff >= 9.0:
            grade = "A-"
            grade_color = "#38bdf8" # Sky blue
        elif net_diff >= 3.0:
            grade = "B+"
            grade_color = "#60a5fa"
        elif net_diff >= -3.0:
            grade = "B"
            grade_color = "#a78bfa" # Purple / Neutral win-win
        elif net_diff >= -9.0:
            grade = "B-"
            grade_color = "#facc15" # Amber
        elif net_diff >= -18.0:
            grade = "C+"
            grade_color = "#fb923c" # Orange
        elif net_diff >= -28.0:
            grade = "C"
            grade_color = "#f87171" # Light red
        elif net_diff >= -40.0:
            grade = "C-"
            grade_color = "#ef4444"
        elif net_diff >= -55.0:
            grade = "D"
            grade_color = "#dc2626"
        else:
            grade = "F"
            grade_color = "#991b1b"

        # 5. Editorial verdict (Editorial Analysis)
        if highest_ovr_rec >= 90 and net_diff >= 10:
            editorial = f"Title-contending coup: adds a superstar ({highest_ovr_rec} OVR) while keeping the roster structure."
        elif highest_ovr_rec >= 88:
            editorial = f"Top-tier addition ({highest_ovr_rec} OVR) to immediately challenge for the top spots."
        elif len(rec_picks) >= 2 and not rec_players:
            editorial = "Strategic teardown: present sacrificed in exchange for a sizable haul of future picks."
        elif len(rec_picks) >= 1 and val_rec_players > 0 and net_diff >= 12:
            editorial = "Excellent deal: lands immediate talent and protects the future with draft picks."
        elif net_diff >= 25:
            editorial = "Crushing win at the negotiating table: net value clearly in its favor."
        elif abs(net_diff) <= 6:
            editorial = "Balanced, pragmatic trade (Win-Win): precisely answers each side's rotation needs."
        elif net_diff <= -25 and highest_ovr_sent >= 88:
            editorial = f"Painful departure ({highest_ovr_sent} OVR): the return in assets looks inadequate for the caliber of the talent sent away."
        elif net_diff <= -15:
            editorial = "Clear overpay: the price paid on the market far exceeds the expected impact of the new addition."
        elif len(sent_picks) >= 2:
            editorial = "Risky all-in: mortgaged the franchise's future to chase immediate results."
        else:
            editorial = "Rotation adjustment with a limited margin of risk."

        # Winner tracking
        if net_diff > best_score:
            best_score = net_diff
            winner_name = t_name

        graded_teams.append({
            **t_entry,
            "trade_grade": grade,
            "grade_color": grade_color,
            "grade_score": round(net_diff, 1),
            "value_received": total_value_received,
            "value_sent": total_value_sent,
            "editorial_verdict": editorial
        })

    # If the gap between the top two is minimal (<= 6 points), consider it a Win-Win
    if len(graded_teams) == 2:
        diff_spread = abs(graded_teams[0]['grade_score'] - graded_teams[1]['grade_score'])
        if diff_spread <= 8.0:
            winner_name = None # No clear winner, balanced trade

    return {
        **trade_entry,
        "teams": graded_teams,
        "winner_team_name": winner_name,
        "is_win_win": winner_name is None
    }
