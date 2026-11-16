# File: core/player_lore.py
"""
Player Lore Engine (Hardwood Basketball Simulator v2.1)
Dynamically generates a contextual, realistic narrative for the player card:
- Role and team hierarchy
- Career phase
- Explanation of statistical slumps, injuries or Day-to-Day status
- Locker-room dynamics (sharing the spotlight with other stars, discontent or breakout)
"""

from typing import Dict, Any, Optional

def generate_player_lore(player: Any, team: Optional[Any] = None) -> Dict[str, str]:
    """
    Analyzes the player's data and returns a dictionary with:
    - role_badge: short descriptive label of the role
    - career_phase: biological career phase
    - status_narrative: detailed explanation of physical condition, form and context
    """
    nome = getattr(player, 'nome', 'Giocatore')
    ovr = getattr(player, 'ovr', 75)
    pot = getattr(player, 'potenziale', 75)
    eta = getattr(player, 'eta', 25)
    ruolo = getattr(player, 'ruolo', 'SG')
    morale = getattr(player, 'morale', 75)
    infortunato = getattr(player, 'infortunato', False)
    is_dtd = getattr(player, 'is_day_to_day', False)
    inf_nome = getattr(player, 'infortunio_nome', None) or getattr(player, 'tipo_infortunio', None)
    inf_giorni = getattr(player, 'giorni_infortunio_rimanenti', 0)
    inf_impatto = getattr(player, 'infortunio_impatto', 0.0)
    stamina_stag = getattr(player, 'stamina_stagionale', 100.0)
    on_block = getattr(player, 'on_trade_block', False)

    # 1. Determina il Role Badge
    abilita = getattr(player, 'abilita', None)
    p3_rating = getattr(abilita, 'three_point_shot_rating', 50) if abilita else 50
    p_def = getattr(abilita, 'perimeter_defense_rating', 50) if abilita else 50
    i_def = getattr(abilita, 'interior_defense_rating', 50) if abilita else 50

    if ovr >= 91:
        role_badge = "🌟 Franchise Superstar"
    elif ovr >= 85:
        role_badge = "⭐ All-Star / 1st Option"
    elif eta <= 22 and pot >= 84:
        role_badge = "💎 Young Prospect"
    elif (p_def >= 84 or i_def >= 84) and ovr < 84:
        role_badge = "🛡️ Defensive Specialist"
    elif p3_rating >= 84 and ovr < 84:
        role_badge = "🎯 Sharpshooter"
    elif ovr >= 78:
        role_badge = "🏀 Solid Starter"
    elif eta >= 33 and ovr >= 74:
        role_badge = "👑 Veteran Leader"
    elif ovr >= 74:
        role_badge = "⚡ Sixth Man / Spark"
    else:
        role_badge = "📋 Bench Rotation"

    # 2. Career phase
    if eta <= 22:
        career_phase = f"{eta}-year-old prospect in the middle of his technical development"
    elif eta <= 28:
        career_phase = f"At the peak of his physical and competitive prime ({eta} years old)"
    elif eta <= 32:
        career_phase = f"Phase of tactical maturity and leadership ({eta} years old)"
    else:
        career_phase = f"Experienced veteran ({eta} years old), minutes carefully managed"

    # 3. Statistical analysis and slumps
    s_stats = getattr(player, 'season_stats', None)
    gp = getattr(s_stats, 'partite_giocate', 0) if s_stats else 0
    t3_att = getattr(s_stats, 'tiri_tentati_3', 0) if s_stats else 0
    t3_made = getattr(s_stats, 'tiri_fatti_3', 0) if s_stats else 0
    t2_att = getattr(s_stats, 'tiri_tentati_2', 0) if s_stats else 0
    t2_made = getattr(s_stats, 'tiri_fatti_2', 0) if s_stats else 0
    tot_att = t2_att + t3_att
    tot_made = t2_made + t3_made

    narrative_pieces = []

    # Injuries & physical condition (high priority)
    if infortunato and inf_nome:
        narrative_pieces.append(f"Currently sidelined because of: {inf_nome}. Return to the court expected in about {inf_giorni} games.")
    elif is_dtd and inf_impatto > 0 and inf_nome:
        narrative_pieces.append(f"Gritting his teeth and playing through a nagging issue ({inf_nome}); mobility and shooting accuracy are limited (-7%).")
    elif stamina_stag < 65.0:
        narrative_pieces.append("Feeling the weight of the tight schedule: accumulated fatigue is costing him sharpness late in games.")

    # Slump / shooting performance
    if gp >= 12 and tot_att >= 40:
        fg_pct = (tot_made / tot_att) * 100.0
        pct_3 = (t3_made / t3_att) * 100.0 if t3_att >= 20 else None

        if pct_3 is not None and pct_3 < 29.0:
            narrative_pieces.append(f"Cold spell from the perimeter ({pct_3:.1f}% from 3): struggling to find a rhythm beyond the arc.")
        elif pct_3 is not None and pct_3 >= 41.0:
            narrative_pieces.append(f"Red hot from long range ({pct_3:.1f}% from 3): a crucial factor for the offensive spacing.")
        elif fg_pct < 39.0:
            narrative_pieces.append(f"Clear shooting slump from the field ({fg_pct:.1f}% FG): percentages below his usual standards.")
        elif fg_pct >= 53.0 and ruolo in ['C', 'PF', 'SF']:
            narrative_pieces.append(f"Great efficiency near the basket ({fg_pct:.1f}% from the field), making the most of the gaps in the paint.")

    # Sezione Breakout o Underperformance (PVS)
    ps = getattr(player, 'performance_scores', None)
    if ps and hasattr(ps, 'total') and gp >= 15:
        pvs = ps.total
        if pvs >= ovr + 4.0:
            narrative_pieces.append("Having a breakout season, with an overall impact clearly above his preseason rating.")
        elif pvs <= ovr - 5.0 and ovr >= 82:
            narrative_pieces.append("Inconsistent so far relative to his status: struggling to assert his statistical leadership.")

    # Cohabitation / team context
    if team and hasattr(team, 'roster'):
        other_stars = [p for p in team.roster if p.nome != nome and getattr(p, 'ovr', 0) >= 86]
        if other_stars and ovr >= 84:
            star_names = ", ".join([s.nome for s in other_stars[:2]])
            narrative_pieces.append(f"Shares possessions and the spotlight with {star_names}, adapting his shot volume to the team's needs.")

    # Market & morale
    if on_block:
        narrative_pieces.append("At the center of persistent trade rumors: the franchise is listening to offers before the deadline.")
    elif morale < 45:
        narrative_pieces.append("The mood in the locker room is gloomy: unhappy with the team's results or the handling of rotations.")
    elif morale >= 92:
        narrative_pieces.append("Great enthusiasm and perfect chemistry with the coaching staff and teammates.")

    # If nothing is out of the ordinary, generate a harmonious standard profile
    if not narrative_pieces:
        if ovr >= 85:
            narrative_pieces.append("A constant reference point of the offense and emotional leader of the starting lineup.")
        elif ovr >= 78:
            narrative_pieces.append("A reliable piece of the system, able to carry out the assigned tactical tasks with discipline.")
        else:
            narrative_pieces.append("Waits for his chances from the bench, ready when his minutes come.")

    return {
        "role_badge": role_badge,
        "career_phase": career_phase,
        "status_narrative": " ".join(narrative_pieces)
    }
