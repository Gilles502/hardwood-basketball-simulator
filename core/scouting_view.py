"""What the user's scouts know about the draft class: the masked values the Scouting page and the draft room show.

Moved unchanged out of server.get_scouting_state so both places use the same rules. Pure: no Flask.
"""
from typing import Dict, List


def grade(val) -> str:
    """Letter grade of a 0-100 rating, as the Scouting page shows it."""
    if val >= 95: return "A+"
    elif val >= 90: return "A"
    elif val >= 85: return "A-"
    elif val >= 80: return "B+"
    elif val >= 75: return "B"
    elif val >= 70: return "B-"
    elif val >= 65: return "C+"
    elif val >= 60: return "C"
    elif val >= 55: return "C-"
    elif val >= 50: return "D+"
    else: return "D"


def scouted_prospects(draft_class, fog_of_war: bool, scout_staff: list) -> List[Dict]:
    """Every prospect as the user's scouts see them (exact, a range or '?' by scouting progress), by mock-draft rank."""
    get_grade = grade

    # Determine the Mock Draft order by sorting by potential + draft_stock_mod
    mock_order = sorted(draft_class, key=lambda p: p.potenziale + getattr(p, 'draft_stock_mod', 0.0), reverse=True)
    mock_positions = {p.nome: idx + 1 for idx, p in enumerate(mock_order)}
    
    prospects_list = []
    for prospect in draft_class:
        progress = 100.0 if not fog_of_war else getattr(prospect, 'scouting_progress', 10.0)
        pos = mock_positions.get(prospect.nome, 60)
        
        # Map of the draft projection based on the position in the Big Board
        if pos <= 5: projection = "Top 5"
        elif pos <= 14: projection = "Lottery"
        elif pos <= 30: projection = "1st Round (Mid)"
        elif pos <= 45: projection = "2nd Round (Early)"
        elif pos <= 60: projection = "2nd Round (Late)"
        else: projection = "Undrafted"
        
        # Obfuscation based on the scouting percentage
        actual_ovr = prospect.valutazione
        actual_pot = prospect.potenziale
        
        # Find whether some scout is assigned to him
        assigned_scout = None
        for s in scout_staff:
            if s.get("assigned_to") == prospect.nome:
                assigned_scout = s.get("name")
                break
                
        # Compute estimated ranges/grades
        if progress >= 90.0:
            ovr_display = f"{actual_ovr}"
            pot_display = get_grade(actual_pot)
            archetype = prospect.pedigree
            attributes = {
                "Close Shot": get_grade(prospect.abilita.close_shot_rating),
                "Mid-Range Shot": get_grade(prospect.abilita.mid_range_shot_rating),
                "Three-Point Shot": get_grade(prospect.abilita.three_point_shot_rating),
                "Passing Vision": get_grade(prospect.abilita.passing_vision),
                "Interior Defense": get_grade(prospect.abilita.interior_defense_rating),
                "Perimeter Defense": get_grade(prospect.abilita.perimeter_defense_rating),
                "Rebounds": get_grade(prospect.abilita.defensive_rebound_rating),
                "Speed": get_grade(prospect.abilita.speed)
            }
        elif progress >= 60.0:
            ovr_display = f"{actual_ovr - 2} - {actual_ovr + 2}"
            pot_display = f"{get_grade(actual_pot - 3)} to {get_grade(actual_pot + 3)}"
            archetype = prospect.pedigree
            attributes = {
                "Close Shot": f"{get_grade(prospect.abilita.close_shot_rating - 4)} to {get_grade(prospect.abilita.close_shot_rating + 4)}",
                "Mid-Range Shot": f"{get_grade(prospect.abilita.mid_range_shot_rating - 4)} to {get_grade(prospect.abilita.mid_range_shot_rating + 4)}",
                "Three-Point Shot": f"{get_grade(prospect.abilita.three_point_shot_rating - 4)} to {get_grade(prospect.abilita.three_point_shot_rating + 4)}",
                "Passing Vision": f"{get_grade(prospect.abilita.passing_vision - 5)} to {get_grade(prospect.abilita.passing_vision + 5)}",
                "Interior Defense": f"{get_grade(prospect.abilita.interior_defense_rating - 5)} to {get_grade(prospect.abilita.interior_defense_rating + 5)}",
                "Perimeter Defense": f"{get_grade(prospect.abilita.perimeter_defense_rating - 5)} to {get_grade(prospect.abilita.perimeter_defense_rating + 5)}",
                "Rebounds": f"{get_grade(prospect.abilita.defensive_rebound_rating - 5)} to {get_grade(prospect.abilita.defensive_rebound_rating + 5)}",
                "Speed": f"{get_grade(prospect.abilita.speed - 5)} to {get_grade(prospect.abilita.speed + 5)}"
            }
        elif progress >= 30.0:
            ovr_display = f"{actual_ovr - 5} - {actual_ovr + 5}"
            pot_display = f"{get_grade(actual_pot - 6)} to {get_grade(actual_pot + 6)}"
            archetype = prospect.pedigree
            attributes = {
                "Close Shot": "C to B",
                "Mid-Range Shot": "C to B",
                "Three-Point Shot": "C to B",
                "Passing Vision": "C to B",
                "Interior Defense": "C to B",
                "Perimeter Defense": "C to B",
                "Rebounds": "C to B",
                "Speed": "C to B"
            }
        else:
            ovr_display = "55 - 80"
            pot_display = "D to A+"
            archetype = "?"
            attributes = {
                "Close Shot": "?",
                "Mid-Range Shot": "?",
                "Three-Point Shot": "?",
                "Passing Vision": "?",
                "Interior Defense": "?",
                "Perimeter Defense": "?",
                "Rebounds": "?",
                "Speed": "?"
            }
            
        prospects_list.append({
            "name": prospect.nome,
            "role": prospect.ruolo,
            "age": prospect.eta,
            "provenance": prospect.provenance,
            "college_stats": getattr(prospect, 'college_stats', {}),
            "scouting_progress": round(progress, 1),
            "assigned_scout": assigned_scout,
            "projection": projection,
            "pos": pos,
            "ovr_display": ovr_display,
            "pot_display": pot_display,
            "archetype": archetype,
            "attributes": attributes
        })

    return sorted(prospects_list, key=lambda x: x["pos"])
