# core/board_engine.py
"""
Engine for managing Board of Directors (Ownership), Board Objectives,
Job Security (Approval Rating), GM Contracts, GM Badges & Achievements,
and GM Firing/Job Market transitions.
"""

import random
import logging
from dataclasses import asdict
from typing import List, Dict, Optional, Any
from core.config import CONFIG, normalize_owner_personality
from core.front_office.state import ensure_front_office
from core.models import (
    Squadra, BoardProfile, BoardObjective,
    UserProfileGM, GMContract, GMBadge, GMAchievement
)

logger = logging.getLogger(__name__)

def board_profile_to_dict(profile: BoardProfile) -> dict:
    if not profile:
        return {}
    return {
        "owner_name": profile.owner_name,
        "personality": profile.personality,
        "patience_level": profile.patience_level,
        "spending_attitude": profile.spending_attitude,
        "approval_rating": round(profile.approval_rating, 1),
        "status_label": profile.status_label,
        "objectives": [asdict(obj) for obj in profile.objectives],
        "board_messages": profile.board_messages,
        "seasons_with_team": profile.seasons_with_team
    }

def user_gm_profile_to_dict(gm: UserProfileGM) -> dict:
    if not gm:
        return {}
    return {
        "name": gm.name,
        "reputation_style": gm.reputation_style,
        "contract": asdict(gm.contract) if hasattr(gm, 'contract') and gm.contract else {},
        "badges": [asdict(b) if hasattr(b, '__dataclass_fields__') else b for b in gm.badges],
        "achievements": [asdict(a) if hasattr(a, '__dataclass_fields__') else a for a in gm.achievements],
        "career_wins": gm.career_wins,
        "career_losses": gm.career_losses,
        "titles_won": gm.titles_won,
        "seasons_managed": gm.seasons_managed,
        "teams_managed_history": gm.teams_managed_history,
        "current_team_name": gm.current_team_name,
        "season_reports": getattr(gm, 'season_reports', []),
        "rpg_xp": getattr(gm, 'rpg_xp', 0),
        "rpg_level": getattr(gm, 'rpg_level', 1),
        "skill_points": getattr(gm, 'skill_points', 2),
        "unlocked_nodes": getattr(gm, 'unlocked_nodes', []),
        "prestige_score": getattr(gm, 'prestige_score', 65.0)
    }


# --- Preset Lists & Constants ---

PERSONALITY_TYPES = list(CONFIG.ECONOMY.OWNER_TYPES)

DEFAULT_GM_BADGES = [
    GMBadge(
        id="calmezza",
        name="Composure",
        description="The owner's approval drops 25% more slowly during periods of crisis.",
        icon="Shield",
        level=1
    ),
    GMBadge(
        id="diplomatico",
        name="Diplomat",
        description="Provides greater tolerance on spending limits and the Luxury Tax.",
        icon="Handshake",
        level=1
    ),
    GMBadge(
        id="master_trader",
        name="Master Trader",
        description="+5% instant approval from the Presidency when you complete favorable trades.",
        icon="TrendingUp",
        level=1
    )
]

DEFAULT_GM_ACHIEVEMENTS = [
    GMAchievement(id="win_title", title="NBA Champion", description="Win your first NBA title as General Manager.", icon="Trophy"),
    GMAchievement(id="win_70_games", title="Absolute Dominance", description="Win at least 70 games in a single Regular Season.", icon="Zap"),
    GMAchievement(id="lottery_winner", title="Lucky Charm", description="Win the number one overall pick in the Draft Lottery.", icon="Sparkles"),
    GMAchievement(id="blockbuster_trade", title="Ninety Strike", description="Acquire a Superstar-level player (OVR 90+) via trade.", icon="ArrowLeftRight"),
    GMAchievement(id="cap_wizard", title="Cap Wizard", description="Get the payroll under the Cap while keeping a winning record.", icon="Landmark"),
    GMAchievement(id="dynasty_builder", title="Dynasty", description="Win 3 NBA titles in your career as General Manager.", icon="Award"),
    GMAchievement(id="playoff_berth", title="Ticket to the Postseason", description="Bring your franchise to the NBA Playoffs.", icon="Target"),
    GMAchievement(id="century_club", title="100 Club", description="Reach 100 total career wins as General Manager.", icon="Shield"),
    GMAchievement(id="draft_gem", title="Keen Eye", description="Develop or acquire a young talent and take him to 85+ OVR.", icon="Sparkles")
]

# --- Helper Functions ---

def add_board_message(profile: BoardProfile, message: Dict) -> bool:
    """Puts a message on top of the owner's board unless the same one (date, title, content) is already there."""
    key = (message.get("date"), message.get("title"), message.get("content"))
    if any((m.get("date"), m.get("title"), m.get("content")) == key for m in profile.board_messages):
        return False
    profile.board_messages.insert(0, message)
    return True


def init_board_profile_for_team(squadra: Squadra, force_reset: bool = False) -> BoardProfile:
    """Generates or initializes the Board of Directors profile for a team."""
    if not force_reset and hasattr(squadra, 'board_profile') and squadra.board_profile is not None:
        return squadra.board_profile

    # Determine personality based on the existing or a random owner
    personality = normalize_owner_personality(getattr(squadra, 'personalita_proprietario', None))
    if not personality:
        personality = random.choice(PERSONALITY_TYPES)

    # The active league's owner names (league file staff.owner_names), else the invented CONFIG list
    from core.league.registry import staff_names
    owner_name = random.choice(staff_names("owner_names", CONFIG.ECONOMY.OWNER_NAMES))
    
    patience_map = CONFIG.ECONOMY.OWNER_BOARD_PATIENCE
    spending_map = CONFIG.ECONOMY.OWNER_BOARD_SPENDING

    profile = BoardProfile(
        owner_name=owner_name,
        personality=personality,
        patience_level=patience_map.get(personality, 3),
        spending_attitude=spending_map.get(personality, 3),
        approval_rating=75.0,
        status_label="Stable",
        objectives=[],
        board_messages=[],
        seasons_with_team=1
    )

    # Generate initial messages and objectives
    generate_seasonal_objectives(squadra, profile)

    squadra.board_profile = profile
    return profile

def init_user_gm_profile(team_name: str) -> UserProfileGM:
    """Initializes the career profile of the user's GM."""
    gm = UserProfileGM(
        name="General Manager",
        reputation_style="Balanced Builder",
        contract=GMContract(salary_per_year=4.5, years_remaining=4, total_years=4),
        badges=[b for b in DEFAULT_GM_BADGES],
        achievements=[a for a in DEFAULT_GM_ACHIEVEMENTS],
        career_wins=0,
        career_losses=0,
        titles_won=0,
        seasons_managed=0,
        teams_managed_history=[{"team": team_name, "start_season": 1, "titles": 0}],
        current_team_name=team_name
    )
    return gm

def generate_seasonal_objectives(squadra: Squadra, profile: Optional[BoardProfile] = None) -> List[BoardObjective]:
    """Generates 3-4 seasonal objectives consistent with the roster and the Owner's personality."""
    if profile is None:
        profile = getattr(squadra, 'board_profile', None)
    if not profile:
        profile = init_board_profile_for_team(squadra)

    objectives = []
    
    # Calc team strength
    roster_ovrs = [g.ovr for g in squadra.roster] if squadra.roster else [75]
    max(roster_ovrs) if roster_ovrs else 75
    avg_top5 = sum(sorted(roster_ovrs, reverse=True)[:5]) / max(1, min(5, len(roster_ovrs)))
    
    # Target Wins calculation calibrated by team tier
    if avg_top5 < 76:
        # Rebuilding Team (20-34 wins)
        expected_wins = max(20, min(34, int((avg_top5 - 68) * 1.6 + 22)))
    elif avg_top5 < 83:
        # Playoff Contender (35-48 wins)
        expected_wins = max(35, min(48, int((avg_top5 - 76) * 1.8 + 36)))
    else:
        # Championship / Elite Team (49-64 wins)
        expected_wins = max(49, min(65, int((avg_top5 - 83) * 2.2 + 50)))
        
    squadra.vittorie_attese = float(expected_wins)

    # 1. Competitive objective
    if expected_wins >= 50:
        obj_comp = BoardObjective(
            id="obj_comp_playoffs",
            title="Compete for the Title",
            description=f"Reach at least the Conference Semifinals (Target: {expected_wins} Wins).",
            category="Competitive",
            target_value=float(expected_wins),
            current_value=0.0,
            impact_approval=20.0
        )
    elif expected_wins >= 40:
        obj_comp = BoardObjective(
            id="obj_comp_playoffs",
            title="Playoff Berth",
            description=f"Qualify directly for the Playoffs (Target: {expected_wins} Wins).",
            category="Competitive",
            target_value=float(expected_wins),
            current_value=0.0,
            impact_approval=15.0
        )
    else:
        obj_comp = BoardObjective(
            id="obj_comp_rebuild",
            title="Development and Growth",
            description=f"Win at least {expected_wins} games while keeping the young core competitive.",
            category="Competitive",
            target_value=float(expected_wins),
            current_value=0.0,
            impact_approval=10.0
        )
    objectives.append(obj_comp)

    # 2. Financial objective (depends on the Owner's personality)
    tax_threshold = getattr(squadra.torneo, 'luxury_tax_threshold', 170.0) if squadra.torneo else 170.0
    if profile.personality == "Risparmiatore":
        obj_fin = BoardObjective(
            id="obj_fin_tax",
            title="Avoid the Luxury Tax",
            description=f"Keep the total Payroll below the Luxury Tax (${tax_threshold:.1f}M).",
            category="Financial",
            target_value=tax_threshold,
            current_value=round(squadra.payroll, 1),
            impact_approval=15.0
        )
    elif profile.personality == "Spendaccione":
        obj_fin = BoardObjective(
            id="obj_fin_star",
            title="Keep the Roster at the Top",
            description="Make sure you have at least 2 players with OVR 85+ on the roster.",
            category="Roster",
            target_value=2.0,
            current_value=float(len([g for g in squadra.roster if g.ovr >= 85])),
            impact_approval=10.0
        )
    else:
        obj_fin = BoardObjective(
            id="obj_fin_budget",
            title="Balanced Fiscal Management",
            description=f"Do not exceed the 1st Apron limit (${tax_threshold + 7.0:.1f}M).",
            category="Financial",
            target_value=tax_threshold + 7.0,
            current_value=round(squadra.payroll, 1),
            impact_approval=10.0
        )
    objectives.append(obj_fin)

    # 3. Young players / Draft objective
    young_players = [g for g in squadra.roster if g.eta <= 23]
    if young_players and normalize_owner_personality(profile.personality) in ["Ricostruttore", "Bilanciato"]:
        best_young = max(young_players, key=lambda g: g.ovr)
        target_ovr = min(99, best_young.ovr + 3)
        obj_youth = BoardObjective(
            id="obj_youth_dev",
            title=f"Development of {best_young.nome}",
            description=f"Grow {best_young.nome} (currently {best_young.ovr} OVR) up to {target_ovr} OVR.",
            category="Roster",
            target_value=float(target_ovr),
            current_value=float(best_young.ovr),
            impact_approval=10.0
        )
        objectives.append(obj_youth)
    else:
        obj_draft = BoardObjective(
            id="obj_draft_picks",
            title="Draft Capital",
            description="Keep all your first-round Draft picks for the next 2 years.",
            category="Draft",
            target_value=2.0,
            current_value=2.0,
            impact_approval=10.0
        )
        objectives.append(obj_draft)

    profile.objectives = objectives
    
    # Send the Presidency's inaugural letter
    # The season number keeps letters of different seasons apart (same team and target can repeat).
    season_number = getattr(getattr(squadra, 'torneo', None), 'season_number', None)
    welcome_letter = {
        "date": f"Season {season_number} Start" if season_number else "Season Start",
        "sender": f"{profile.owner_name} ({profile.personality})",
        "title": "Official Directive Letter from the Presidency",
        "content": (
            f"Dear General Manager, welcome to this season with the {squadra.nome}. "
            f"Our expectations are clear: we are aiming for about {expected_wins} wins. "
            f"We ask you to monitor the budget carefully and to follow the attached directives."
        ),
        "type": "info"
    }
    # init_board_profile_for_team already sends it and several callers regenerate the objectives right after:
    # the same letter must not land twice.
    add_board_message(profile, welcome_letter)

    return objectives

def sync_board_objectives(squadra: Squadra, torneo: object, profile: Optional[BoardProfile] = None) -> List[BoardObjective]:
    """
    Syncs in real time the current values and the status of the seasonal objectives
    based on the current data of the tournament and the roster.
    """
    if profile is None:
        profile = getattr(squadra, 'board_profile', None)
    if not profile or not profile.objectives:
        return []

    for obj in profile.objectives:
        # 1. Competitive objective (Wins)
        if obj.category == "Competitive" or "obj_comp" in obj.id:
            obj.current_value = float(squadra.vittorie)
            total_games = squadra.vittorie + squadra.sconfitte
            if total_games >= 80:
                if squadra.vittorie >= obj.target_value:
                    obj.status = "Completed"
                else:
                    obj.status = "Failed"

        # 2. Financial objective (Payroll / Tax)
        elif obj.category == "Financial" or "obj_fin" in obj.id:
            obj.current_value = round(float(squadra.payroll), 1)
            total_games = squadra.vittorie + squadra.sconfitte
            if total_games >= 80:
                if squadra.payroll <= obj.target_value:
                    obj.status = "Completed"
                else:
                    obj.status = "Failed"

        # 3. Young players / Roster objective (OVR development or stars on the roster)
        elif obj.category == "Roster":
            if "star" in obj.id:
                count_stars = len([g for g in squadra.roster if g.ovr >= 85])
                obj.current_value = float(count_stars)
                if count_stars >= obj.target_value:
                    obj.status = "Completed"
            else:
                target_name = obj.title
                for prefix in ("Development of ", "Sviluppo di "):  # the Italian prefix is kept for old saves
                    target_name = target_name.replace(prefix, "")
                target_name = target_name.strip()
                matched_player = next((g for g in squadra.roster if target_name.lower() in g.nome.lower()), None)
                if not matched_player:
                    young_players = [g for g in squadra.roster if g.eta <= 24]
                    if young_players:
                        matched_player = max(young_players, key=lambda g: g.ovr)
                
                if matched_player:
                    obj.current_value = float(matched_player.ovr)
                    if matched_player.ovr >= obj.target_value:
                        obj.status = "Completed"

        # 4. Draft objective (future pick capital)
        elif obj.category == "Draft" or "obj_draft" in obj.id:
            picks_owned = 0
            if hasattr(torneo, 'pick_ownership') and torneo.pick_ownership:
                for yr in range(1, 3):
                    yr_picks = torneo.pick_ownership.get(yr, {})
                    for pick_key, owner in yr_picks.items():
                        if owner == squadra.nome and "R1" in pick_key:
                            picks_owned += 1
            else:
                picks_owned = int(obj.target_value)
            
            obj.current_value = float(picks_owned)
            if picks_owned >= obj.target_value:
                obj.status = "Completed"

    return profile.objectives

def update_approval_rating(squadra: Squadra, user_gm: UserProfileGM, event_type: str, payload: Optional[Dict] = None) -> float:
    """Recomputes the Owner's approval (0-100%) based on in-game events."""
    profile = getattr(squadra, 'board_profile', None)
    if not profile:
        profile = init_board_profile_for_team(squadra)

    has_calmezza = any(b.id == "calmezza" for b in user_gm.badges)
    has_diplomatico = any(b.id == "diplomatico" for b in user_gm.badges)

    delta = 0.0

    if event_type == "weekly_check":
        # Compare expected vs actual wins
        pg = max(1, squadra.vittorie + squadra.sconfitte)
        win_pct = squadra.vittorie / pg
        expected_win_pct = max(0.2, min(0.85, squadra.vittorie_attese / 82.0))
        
        diff = (win_pct - expected_win_pct) * 8.0
        if diff < 0 and has_calmezza:
            diff *= 0.75 # Calm temperament dampens the drop by 25%
        
        delta += diff

        # Check payroll for a Frugal owner
        if profile.personality == "Risparmiatore":
            tax_threshold = getattr(squadra.torneo, 'luxury_tax_threshold', 170.0) if squadra.torneo else 170.0
            if squadra.payroll > tax_threshold:
                tax_penalty = -2.0 if not has_diplomatico else -1.0
                delta += tax_penalty

    elif event_type == "trade_executed":
        # If the trade takes on a lot of salary and the owner is frugal
        added_salary = payload.get("added_salary", 0.0) if payload else 0.0
        if profile.personality == "Risparmiatore" and added_salary > 5.0:
            delta -= 5.0 if not has_diplomatico else 2.5
            msg = {
                "date": "Trade Market",
                "sender": profile.owner_name,
                "title": "Concern Over the Payroll",
                "content": f"The Presidency expresses concern over the ${added_salary:.1f}M increase in payroll caused by the latest trade.",
                "type": "warning"
            }
            profile.board_messages.insert(0, msg)
        elif payload and payload.get("star_acquired"):
            has_master_trader = any(b.id == "master_trader" for b in user_gm.badges)
            trader_bonus = 8.0 if has_master_trader else 5.0
            delta += trader_bonus
            msg = {
                "date": "Trade Market",
                "sender": profile.owner_name,
                "title": "Congratulations on the Acquisition!",
                "content": "The Presidency applauds the arrival of the new star. A great coup in both media and sporting terms!",
                "type": "success"
            }
            profile.board_messages.insert(0, msg)

    elif event_type in ["season_end", "playoffs_end"]:
        # Evaluate completion of ALL objectives
        torneo_obj = getattr(squadra, 'torneo', None)
        sync_board_objectives(squadra, torneo_obj, profile)
        
        completed_count = 0
        failed_count = 0

        for obj in profile.objectives:
            if obj.category == "Competitive" or "obj_comp" in obj.id:
                if squadra.vittorie >= obj.target_value:
                    obj.status = "Completed"
                    delta += obj.impact_approval
                    completed_count += 1
                else:
                    obj.status = "Failed"
                    loss_impact = -obj.impact_approval
                    if has_calmezza: loss_impact *= 0.75
                    delta += loss_impact
                    failed_count += 1

            elif obj.category == "Financial" or "obj_fin" in obj.id:
                if squadra.payroll <= obj.target_value:
                    obj.status = "Completed"
                    delta += obj.impact_approval
                    completed_count += 1
                else:
                    obj.status = "Failed"
                    delta += -obj.impact_approval
                    failed_count += 1

            elif obj.category == "Roster":
                if obj.current_value >= obj.target_value:
                    obj.status = "Completed"
                    delta += obj.impact_approval
                    completed_count += 1
                else:
                    obj.status = "Failed"
                    delta += - (obj.impact_approval * 0.5)
                    failed_count += 1

            elif obj.category == "Draft":
                if obj.current_value >= obj.target_value:
                    obj.status = "Completed"
                    delta += obj.impact_approval
                    completed_count += 1
                else:
                    obj.status = "Failed"
                    delta += - (obj.impact_approval * 0.5)
                    failed_count += 1

        # Generate the Board's end-of-season letter
        eval_type = "success" if completed_count >= failed_count else "warning"
        eval_msg = {
            "date": "End of Season",
            "sender": f"{profile.owner_name} ({profile.personality})",
            "title": f"Official Board Report Card: {completed_count} Objectives Met",
            "content": (
                f"The Presidency has reviewed the annual results. You completed {completed_count} objectives "
                f"out of {len(profile.objectives)}. Final record: {squadra.vittorie}-{squadra.sconfitte}."
            ),
            "type": eval_type
        }
        profile.board_messages.insert(0, eval_msg)

    # Apply the change
    profile.approval_rating = max(0.0, min(100.0, profile.approval_rating + delta))

    # Update the status label
    if profile.approval_rating >= 85:
        profile.status_label = "Untouchable"
    elif profile.approval_rating >= 65:
        profile.status_label = "Stable"
    elif profile.approval_rating >= 45:
        profile.status_label = "Under Review"
    elif profile.approval_rating >= 25:
        profile.status_label = "Hot Seat"
    else:
        profile.status_label = "Fired"

    return profile.approval_rating

def evaluate_gm_contract_and_renewal(squadra: Squadra, user_gm: UserProfileGM) -> Dict:
    """Evaluates the GM's contract at the end of the season (renewals or firing)."""
    profile = getattr(squadra, 'board_profile', None)
    if not profile:
        profile = init_board_profile_for_team(squadra)

    contract = user_gm.contract
    contract.years_remaining -= 1
    profile.seasons_with_team += 1
    user_gm.seasons_managed += 1

    result = {
        "status": "normal", # "normal", "extension_offered", "fired", "contract_expired"
        "message": "",
        "extension": None
    }

    # Case 1: Fired due to low approval rating (< 25%)
    if profile.approval_rating < 25.0:
        result["status"] = "fired"
        result["message"] = f"You have been fired by the {squadra.nome}! President {profile.owner_name} ended your tenure due to the organization's low approval ({profile.approval_rating:.1f}%)."
        profile.board_messages.insert(0, {
            "date": "End of Season",
            "sender": profile.owner_name,
            "title": "Official Statement: Contract Termination",
            "content": result["message"],
            "type": "danger"
        })
        return result

    # Case 2: Extension offer (Approval >= 60% and 1 or 2 years left)
    if profile.approval_rating >= 60.0 and contract.years_remaining <= 2 and not contract.extension_offered:
        new_salary = round(contract.salary_per_year * 1.3, 1)
        ext = {
            "years": 3,
            "salary": new_salary,
            "team_name": squadra.nome
        }
        contract.can_extend = True
        contract.extension_offered = ext
        result["status"] = "extension_offered"
        result["extension"] = ext
        result["message"] = f"The {squadra.nome} Presidency offers you a 3-year contract extension at ${new_salary}M/year!"
        profile.board_messages.insert(0, {
            "date": "End of Season",
            "sender": profile.owner_name,
            "title": "Contract Renewal Offer",
            "content": result["message"],
            "type": "success"
        })
        return result

    # Case 3: Contract expired
    if contract.years_remaining <= 0:
        if profile.approval_rating >= 50.0:
            # Automatic renewal for high-performing GM
            new_salary = round(contract.salary_per_year * 1.3, 1)
            contract.years_remaining = 3
            contract.total_years = 3
            contract.salary_per_year = new_salary
            contract.can_extend = False
            contract.extension_offered = None
            result["status"] = "normal"
            result["message"] = f"Contract renewed with the {squadra.nome} for 3 years at ${new_salary}M/year thanks to the results achieved ({profile.approval_rating:.1f}% approval)!"
            profile.board_messages.insert(0, {
                "date": "End of Season",
                "sender": profile.owner_name,
                "title": "Official Presidency Reconfirmation",
                "content": result["message"],
                "type": "success"
            })
            return result
        else:
            result["status"] = "contract_expired"
            result["message"] = f"Your contract with the {squadra.nome} has expired. You are a free-agent General Manager!"
            return result

    return result

def check_gm_achievements(user_gm: UserProfileGM, torneo: object, payload: Optional[Dict] = None) -> List[GMAchievement]:
    """Checks and unlocks achievements for the GM's career."""
    if not user_gm:
        return []
    
    unlocked_new = []
    season_num = getattr(torneo, 'season_number', 1)
    starting_yr = getattr(torneo, 'starting_year', 2002)
    current_year_str = f"Year {starting_yr + season_num - 1}"
    
    user_team = getattr(torneo, 'squadra_giocatore', None)

    for ach in user_gm.achievements:
        if ach.unlocked:
            continue

        unlocked = False

        # 1. NBA Champion
        if ach.id == "win_title":
            if user_gm.titles_won >= 1 or (torneo and getattr(torneo, 'campione', None) and user_team and torneo.campione.nome == user_team.nome):
                unlocked = True

        # 2. Absolute Dominance (70+ wins)
        elif ach.id == "win_70_games":
            season_wins = payload.get("season_wins", 0) if payload else (user_team.vittorie if user_team else 0)
            if season_wins >= 70:
                unlocked = True

        # 3. Lucky Charm (Draft Lottery #1)
        elif ach.id == "lottery_winner":
            if payload and payload.get("won_lottery"):
                unlocked = True
            elif torneo and user_team:
                lottery_order = getattr(torneo, 'draft_lottery_order', getattr(torneo, 'ordine_draft', []))
                if lottery_order and lottery_order[0] == user_team.nome:
                    unlocked = True

        # 4. Ninety Strike (Superstar 90+ OVR acquisition via trade)
        elif ach.id == "blockbuster_trade":
            if payload and payload.get("acquired_ovr", 0) >= 90:
                unlocked = True

        # 5. Cap Wizard (Under the Cap with a winning record)
        elif ach.id == "cap_wizard":
            if payload and payload.get("under_cap_and_winning"):
                unlocked = True
            elif user_team:
                cap = getattr(torneo, 'salary_cap', 136.0) if torneo else 136.0
                if user_team.payroll <= cap and user_team.vittorie > 41 and (user_team.vittorie + user_team.sconfitte >= 80):
                    unlocked = True

        # 6. Dynasty (3 titles won)
        elif ach.id == "dynasty_builder":
            if user_gm.titles_won >= 3:
                unlocked = True

        # 7. Ticket to the Postseason
        elif ach.id == "playoff_berth":
            if user_team:
                if (user_team.vittorie + user_team.sconfitte >= 80) and user_team.vittorie >= 42:
                    unlocked = True
                elif torneo and hasattr(torneo, 'playoff_bracket_data') and torneo.playoff_bracket_data:
                    unlocked = True

        # 8. 100 Club (100 wins)
        elif ach.id == "century_club":
            if user_gm.career_wins >= 100:
                unlocked = True

        # 9. Keen Eye (Talent developed to 85+ OVR)
        elif ach.id == "draft_gem":
            if user_team:
                for p in user_team.roster:
                    if p.eta <= 24 and p.ovr >= 85:
                        unlocked = True
                        break

        if unlocked:
            ach.unlocked = True
            ach.date_unlocked = current_year_str
            unlocked_new.append(ach)
            
            # Add a celebration message
            if user_team and hasattr(user_team, 'board_profile') and user_team.board_profile:
                user_team.board_profile.board_messages.insert(0, {
                    "date": "Achievement Unlocked",
                    "sender": "Hall of Fame Commission",
                    "title": f"🏆 Milestone Unlocked: {ach.title}!",
                    "content": f"Congratulations to the GM for unlocking the achievement '{ach.title}': {ach.description}",
                    "type": "success"
                })

    return unlocked_new

def generate_annual_season_report(squadra: Squadra, torneo: object, user_gm: UserProfileGM, is_live: bool = False) -> Dict:
    """
    Builds and formats the Annual Report of the executive career path for the current or a past season.
    """
    season_number = getattr(torneo, 'season_number', 1)
    starting_year = getattr(torneo, 'starting_year', 2002)
    year = starting_year + season_number - 1

    profile = getattr(squadra, 'board_profile', None)
    if not profile:
        profile = init_board_profile_for_team(squadra)

    # Sync live objectives
    sync_board_objectives(squadra, torneo, profile)

    total_games = max(1, squadra.vittorie + squadra.sconfitte)
    win_pct = round(squadra.vittorie / total_games, 3)

    # Conference Rank
    all_teams_conf = [s for s in getattr(torneo, 'squadre', []) if s.conference == squadra.conference]
    sorted_conf = sorted(all_teams_conf, key=lambda s: s.vittorie, reverse=True)
    rank_idx = next((i + 1 for i, s in enumerate(sorted_conf) if s.nome == squadra.nome), 1)
    conf_rank_str = f"#{rank_idx} in the {squadra.conference}"

    # Playoff Result
    playoff_result = "Not Qualified"
    campione = getattr(torneo, 'campione', None)
    if campione and campione.nome == squadra.nome:
        playoff_result = "NBA Champions 🏆"
    elif getattr(torneo, 'playoff_bracket_data', None):
        # Determine how deep the team went
        playoff_result = "Playoff Qualified"
        # Check finals MVP or finals runner up
        finals_series = getattr(torneo, 'finals_series_log', [])
        if finals_series:
            playoff_result = "NBA Finals (Runner-up)"
    elif rank_idx <= 8:
        playoff_result = "Playoff Qualified"
    elif rank_idx <= 10:
        playoff_result = "Play-In Stage"

    # Objectives breakdown
    objs_summary = []
    completed_count = 0
    for obj in profile.objectives:
        is_done = obj.status == "Completed" or (obj.current_value >= obj.target_value and obj.category != "Financial")
        if is_done:
            completed_count += 1
        objs_summary.append({
            "title": obj.title,
            "category": obj.category,
            "description": obj.description,
            "target": obj.target_value,
            "current": obj.current_value,
            "status": "Completed" if is_done else ("Pending" if is_live else "Failed"),
            "impact": obj.impact_approval
        })

    # Team leaders
    top_scorers = []
    if squadra.roster:
        sorted_by_pts = sorted(squadra.roster, key=lambda p: (p.season_stats.punti / max(1, p.season_stats.partite_giocate)), reverse=True)[:3]
        for p in sorted_by_pts:
            pg = max(1, p.season_stats.partite_giocate)
            top_scorers.append({
                "name": p.nome,
                "role": p.ruolo,
                "ovr": p.ovr,
                "ppg": round(p.season_stats.punti / pg, 1),
                "rpg": round(p.season_stats.rimbalzi / pg, 1),
                "apg": round(p.season_stats.assist / pg, 1)
            })

    # Team Awards and Accolades
    awards_won = []
    if getattr(torneo, 'regular_season_mvp', None) and torneo.regular_season_mvp.squadra and torneo.regular_season_mvp.squadra.nome == squadra.nome:
        awards_won.append(f"League MVP ({torneo.regular_season_mvp.nome})")
    if getattr(torneo, 'finals_mvp', None) and torneo.finals_mvp.squadra and torneo.finals_mvp.squadra.nome == squadra.nome:
        awards_won.append(f"Finals MVP ({torneo.finals_mvp.nome})")

    # Owner review letter
    if profile.approval_rating >= 80:
        tone_title = "Official Commendation Letter from the Presidency"
        tone_text = (
            f"Dear General Manager, the Presidency expresses its highest praise for the impeccable management shown during the {year} season. "
            f"The {squadra.vittorie}-{squadra.sconfitte} record and the solidity of the group testify to the soundness of your executive choices. "
            f"You have our full confidence to keep leading the {squadra.nome} toward new prestigious goals."
        )
    elif profile.approval_rating >= 50:
        tone_title = "Annual Board of Directors Evaluation"
        tone_text = (
            f"Dear General Manager, the {year} season ends with an overall balanced result ({squadra.vittorie}-{squadra.sconfitte}). "
            f"The organization recognizes the effort put in, but expects a further step up in quality and careful payroll management going forward."
        )
    else:
        tone_title = "Official Presidency Warning for Insufficient Performance"
        tone_text = (
            f"Dear General Manager, the results of the {year} season were well below the expectations set by the Board. "
            f"The final record of {squadra.vittorie}-{squadra.sconfitte} and the failure to reach the key objectives seriously jeopardize your position at the helm of the franchise."
        )

    # Narrative story paragraph
    star_name = top_scorers[0]['name'] if top_scorers else "the team"
    narrative_story = (
        f"The {year} season for the {squadra.nome} was marked by a run of {squadra.vittorie} wins and {squadra.sconfitte} losses "
        f"({conf_rank_str}). Led on the court by {star_name}, the team reached the milestone: '{playoff_result}'. "
        f"On the corporate side, {completed_count} objectives out of {len(objs_summary)} were met, "
        f"closing with a management approval rating of {profile.approval_rating:.1f}%."
    )

    report_dict = {
        "season_number": season_number,
        "year": year,
        "team_name": squadra.nome,
        "record": f"{squadra.vittorie}-{squadra.sconfitte}",
        "win_pct": win_pct,
        "conference_rank": conf_rank_str,
        "playoff_result": playoff_result,
        "approval_rating": round(profile.approval_rating, 1),
        "status_label": profile.status_label,
        "owner_name": profile.owner_name,
        "owner_personality": profile.personality,
        "owner_letter_title": tone_title,
        "owner_letter_content": tone_text,
        "objectives_completed_count": completed_count,
        "objectives_total_count": len(objs_summary),
        "objectives": objs_summary,
        "top_players": top_scorers,
        "awards": awards_won,
        "narrative_story": narrative_story,
        "is_live": is_live,
        "created_at": f"Season {year}"
    }

    return report_dict

def generate_gm_job_offers(torneo: object, user_gm: UserProfileGM) -> List[Dict]:
    """Generates job offers from other franchises when the user is fired or at the end of the contract."""
    all_teams = getattr(torneo, 'squadre', [])
    if not all_teams:
        return []

    offers = []

    # If the user was with a team and has good approval, the current team offers a renewal
    current_team = next((s for s in all_teams if s.nome == user_gm.current_team_name), None)
    if current_team:
        curr_prof = getattr(current_team, 'board_profile', None)
        if not curr_prof:
            curr_prof = init_board_profile_for_team(current_team)
        if curr_prof.approval_rating >= 35.0:
            roster_ovrs = [g.ovr for g in current_team.roster] if current_team.roster else [75]
            avg_top5 = sum(sorted(roster_ovrs, reverse=True)[:5]) / max(1, min(5, len(roster_ovrs)))
            offers.append({
                "team_name": current_team.nome,
                "owner_name": curr_prof.owner_name,
                "personality": curr_prof.personality,
                "salary": round(user_gm.contract.salary_per_year * 1.3, 1) if user_gm.contract else 5.5,
                "years": 4,
                "roster_avg_ovr": round(avg_top5, 1),
                "payroll": round(current_team.payroll, 1),
                "expectation": "Renewal & Dynasty" if avg_top5 >= 83 else "Playoff"
            })

    # Select other teams
    available_teams = [s for s in all_teams if s.nome != user_gm.current_team_name]
    random.shuffle(available_teams)

    selected = available_teams[:3]

    for team in selected:
        prof = getattr(team, 'board_profile', None)
        if not prof:
            prof = init_board_profile_for_team(team)

        base_salary = round(random.uniform(3.5, 7.5), 1)
        years = random.choice([3, 4, 5])
        
        roster_ovrs = [g.ovr for g in team.roster] if team.roster else [75]
        avg_top5 = sum(sorted(roster_ovrs, reverse=True)[:5]) / max(1, min(5, len(roster_ovrs)))
        
        if avg_top5 >= 83:
            expectation = "NBA Title"
        elif avg_top5 >= 78:
            expectation = "Playoff"
        else:
            expectation = "Young Rebuild"

        offers.append({
            "team_name": team.nome,
            "owner_name": prof.owner_name,
            "personality": prof.personality,
            "salary": base_salary,
            "years": years,
            "roster_avg_ovr": round(avg_top5, 1),
            "payroll": round(team.payroll, 1),
            "expectation": expectation
        })

    return offers


# =====================================================================
# --- PRE-SEASON GM & HEAD COACH SUMMIT SYSTEM ---
# =====================================================================

def get_or_create_summit_data(squadra: Squadra, torneo: Any) -> Dict[str, Any]:
    """
    Retrieves the state or generates the proposal of the Pre-Season Summit between the GM and the Head Coach.
    """
    if not squadra or not torneo:
        return {"available": False, "reason": "No active team or tournament"}

    current_season = getattr(torneo, 'season_number', 1)
    existing_summit = getattr(squadra, 'front_office_summit', None)

    # If the summit for this season has already been completed
    if isinstance(existing_summit, dict) and existing_summit.get('completed') and existing_summit.get('season') == current_season:
        return {
            "available": True,
            "completed": True,
            "summit": existing_summit
        }

    # The user is the GM, so the summit uses the user's profile name; a coach-only user meets the team's CPU GM.
    gm_name = getattr(getattr(torneo, 'user_gm_profile', None), 'name', None) or "General Manager"
    if getattr(torneo, 'user_role', 'gm_coach') == 'only_coach':
        cpu_gm = ensure_front_office(torneo).seated_gm(squadra.nome)
        if cpu_gm is not None:
            gm_name = cpu_gm.name

    roster = getattr(squadra, 'roster', [])
    [g.ovr for g in roster] if roster else [75]
    sorted_roster = sorted(roster, key=lambda p: getattr(p, 'ovr', 0), reverse=True)
    
    top5_ovrs = sorted_roster[:5]
    avg_top5 = sum(p.ovr for p in top5_ovrs) / max(1, len(top5_ovrs)) if top5_ovrs else 75.0
    star_player = top5_ovrs[0] if top5_ovrs else None
    star_name = getattr(star_player, 'nome', 'Star Player')
    star_ovr = getattr(star_player, 'ovr', 80)
    
    young_core = [p for p in roster if getattr(p, 'eta', 25) <= 24 and getattr(p, 'potenziale', getattr(p, 'pot', 75)) >= 80]
    young_core_names = [p.nome for p in young_core[:3]]

    enable_play_in = getattr(torneo, 'enable_play_in', True)

    # Determine the GM's proposal
    if avg_top5 >= 83.5:
        proposed_goal = "CHAMPIONSHIP"
        target_wins = max(52, min(63, int(50 + (avg_top5 - 83.5) * 2.5)))
        gm_statement = (
            f"Coach, looking at this locker room led by {star_name} (OVR {star_ovr}): we have a real contender on our hands. "
            f"The ownership and the front office expect a deep Playoff run and a push for the Finals. "
            f"Our baseline goal for this season is to compete for the NBA Title (Target: {target_wins} W)."
        )
    elif avg_top5 >= 79.5:
        proposed_goal = "PLAYOFFS"
        target_wins = max(42, min(50, int(42 + (avg_top5 - 79.5) * 2.0)))
        gm_statement = (
            f"Coach, our rotation has the quality to secure a guaranteed spot in the top 6 seeds. "
            f"With {star_name} at the helm and an organized defense, our seasonal goal is direct access to the Playoffs (Target: {target_wins} W)."
        )
    elif avg_top5 >= 75.5 and enable_play_in:
        proposed_goal = "PLAY_IN"
        target_wins = max(36, min(41, int(35 + (avg_top5 - 75.5) * 1.5)))
        gm_statement = (
            f"Coach, the Conference is competitive and our roster is in a transition phase. "
            f"I believe that with your tactical work we can snatch a ticket to the Play-In Tournament (Seeds 7-10, Target: {target_wins} W)."
        )
    elif avg_top5 >= 76.5 and not enable_play_in:
        proposed_goal = "PLAYOFF_HUNT"
        target_wins = max(38, min(43, int(37 + (avg_top5 - 76.5) * 1.5)))
        gm_statement = (
            f"Coach, without the Play-In shortcut we are in for a tight battle to grab the classic eighth spot. "
            f"We aim to stay in the Playoff race until the last game day (Target: {target_wins} W)."
        )
    else:
        proposed_goal = "TANKING"
        target_wins = max(20, min(32, int(20 + max(0, avg_top5 - 70) * 1.5)))
        young_mention = f" and on the progress of youngsters like {', '.join(young_core_names)}" if young_core_names else ""
        gm_statement = (
            f"Coach, we must be frank and clear-headed: the team is in a rebuilding and asset-accumulation phase. "
            f"The absolute priority this year is the development of the young core{young_mention} and the protection of the Draft picks. "
            f"We want constant effort on the court, but we are not under pressure to chase the postseason (Target: {target_wins} W)."
        )

    # Options for the Head Coach
    # 1. Consensus
    opt_consensus = {
        "key": "consensus",
        "label": "Full Agreement & Alignment",
        "coach_speech": "I fully agree with the Front Office's analysis. I will set minutes and schemes to achieve exactly this goal.",
        "target_wins": target_wins,
        "resulting_goal": proposed_goal,
        "board_impact": "+10 GM Trust, aligned expectations",
        "deadline_posture": "Aligned with the Plan"
    }

    # 2. Ambitious Challenge
    if proposed_goal == "TANKING":
        ambitious_goal = "PLAY_IN" if enable_play_in else "PLAYOFFS"
        ambitious_wins = target_wins + 8
        ambitious_speech = "You are underestimating the grit of this group. I'll work on chemistry and defensive intensity: we can fight for the Play-In / Playoffs!"
    elif proposed_goal in ["PLAY_IN", "PLAYOFF_HUNT"]:
        ambitious_goal = "PLAYOFFS"
        ambitious_wins = target_wins + 6
        ambitious_speech = "The Play-In isn't enough for me. This group can avoid the lottery and qualify directly among the top 6!"
    elif proposed_goal == "PLAYOFFS":
        ambitious_goal = "CHAMPIONSHIP"
        ambitious_wins = target_wins + 5
        ambitious_speech = "We're not extras. If we protect home-court advantage we can aim for the NBA Title or the Finals!"
    else: # CHAMPIONSHIP
        ambitious_goal = "DOMINANCE"
        ambitious_wins = min(66, target_wins + 4)
        ambitious_speech = "We're aiming for the league's absolute first place (60+ Wins) and to dominate the postseason from start to finish!"

    opt_ambitious = {
        "key": "ambitious",
        "label": "Ambitious Challenge: Let's Raise the Bar",
        "coach_speech": ambitious_speech,
        "target_wins": ambitious_wins,
        "resulting_goal": ambitious_goal,
        "board_impact": "+5 Esteem for the leadership, but greater pressure on results",
        "deadline_posture": "Aggressive Buyer (Hunt for Veterans / Reinforcements)"
    }

    # 3. Patient Development / Cautious
    if proposed_goal in ["CHAMPIONSHIP", "PLAYOFFS"]:
        dev_goal = "SUSTAINABLE_CONTENDER"
        dev_wins = max(38, target_wins - 5)
        dev_speech = "Let's not waste energy chasing fleeting regular-season wins. Let's manage the stars' workloads and grow the bench so we arrive at the postseason healthy."
    else:
        dev_goal = "ASSET_GROWTH"
        dev_wins = max(18, target_wins - 4)
        dev_speech = "Let's protect the future: I want to give real minutes to our rookies and sophomores without burning them out. Draft picks and individual growth are worth more than a few short-term wins."

    opt_patient = {
        "key": "patient_dev",
        "label": "Patience & Load Management",
        "coach_speech": dev_speech,
        "target_wins": dev_wins,
        "resulting_goal": dev_goal,
        "board_impact": "Reduced pressure on the Head Coach, contractual protection",
        "deadline_posture": "Pick Accumulator / Young Player Development"
    }

    proposal = {
        "season": current_season,
        "gm_name": gm_name,
        "team_name": squadra.nome,
        "avg_top5_ovr": round(avg_top5, 1),
        "star_player": {"name": star_name, "ovr": star_ovr},
        "young_core": young_core_names,
        "proposed_goal": proposed_goal,
        "proposed_wins": target_wins,
        "gm_statement": gm_statement,
        "enable_play_in": enable_play_in,
        "options": [opt_consensus, opt_ambitious, opt_patient]
    }

    return {
        "available": True,
        "completed": False,
        "proposal": proposal
    }

def submit_summit_decision(squadra: Squadra, torneo: Any, choice_key: str) -> Dict[str, Any]:
    """
    Applies the resolution of the Pre-Season Summit between the GM and the Coach.
    """
    current_data = get_or_create_summit_data(squadra, torneo)
    if not current_data.get("available") or current_data.get("completed"):
        return current_data

    proposal = current_data.get("proposal", {})
    options = proposal.get("options", [])
    selected_option = next((opt for opt in options if opt["key"] == choice_key), None)
    if not selected_option:
        selected_option = options[0] # Default to consensus

    current_season = getattr(torneo, 'season_number', 1)
    agreed_goal = selected_option["resulting_goal"]
    target_wins = selected_option["target_wins"]
    gm_name = proposal.get("gm_name", "General Manager")

    # Apply the targets to the team
    squadra.vittorie_attese = float(target_wins)
    squadra.team_goal = agreed_goal

    # Update the Board Profile and relationships
    board_prof = getattr(squadra, 'board_profile', None)
    if not board_prof:
        board_prof = init_board_profile_for_team(squadra)

    if choice_key == "consensus":
        board_prof.approval_rating = min(100.0, board_prof.approval_rating + 8.0)
        feedback_msg = f"GM {gm_name} appreciated the total tactical harmony and the alignment with the presidency."
    elif choice_key == "ambitious":
        board_prof.approval_rating = min(100.0, board_prof.approval_rating + 5.0)
        feedback_msg = f"GM {gm_name} is energized by your ambition, but warns that expectations are now significantly higher."
    else:
        feedback_msg = f"GM {gm_name} took note of the caution: the minutes of the young players and load management will be priorities."

    # Sync the Board's primary objective
    for obj in getattr(board_prof, 'objectives', []):
        if getattr(obj, 'category', '') == "Competitive":
            obj.target_value = float(target_wins)
            obj.description = f"Goal agreed at the GM Summit: {agreed_goal} (Target: {target_wins} Wins)."

    # Save the summit record
    summit_record = {
        "completed": True,
        "season": current_season,
        "gm_name": gm_name,
        "proposed_goal": proposal.get("proposed_goal"),
        "proposed_wins": proposal.get("proposed_wins"),
        "agreed_goal": agreed_goal,
        "target_wins": target_wins,
        "choice": choice_key,
        "coach_speech": selected_option["coach_speech"],
        "feedback_msg": feedback_msg,
        "deadline_posture": selected_option["deadline_posture"]
    }
    squadra.front_office_summit = summit_record

    # Generate a news item for the News Feed
    try:
        from core.news_generator import add_news
        goal_labels = {
            "CHAMPIONSHIP": "NBA Title Run",
            "DOMINANCE": "Absolute Regular Season Dominance",
            "PLAYOFFS": "Direct Playoff Berth",
            "PLAY_IN": "Corsa al Play-In Tournament",
            "PLAYOFF_HUNT": "Hunt for the 8th Playoff Seed",
            "TANKING": "Youth Development & Future Rebuild",
            "SUSTAINABLE_CONTENDER": "Load Management & Playoff Push",
            "ASSET_GROWTH": "Sustainable Growth & Future Assets"
        }
        goal_label = goal_labels.get(agreed_goal, agreed_goal)
        season_num = getattr(torneo, 'stagione', getattr(torneo, 'season_number', 1))
        add_news(
            "team",
            f"{squadra.nome} Front Office Summit: Official Goal {goal_label}",
            f"At the end of the annual pre-season conference between GM {gm_name} and the Head Coach, "
            f"the course was announced for Season {season_num}: target set at {target_wins} wins ({goal_label}).",
            teams=[squadra.nome],
            is_breaking=True
        )
    except Exception as e:
        print(f"Warning: could not add summit news: {e}")

    return {
        "available": True,
        "completed": True,
        "summit": summit_record
    }


# =====================================================================
# BOARD CONCERN DIALOGUES (OWNERSHIP ACCOUNTABILITY & COACH PROTECTION)
# =====================================================================

def check_board_concern_trigger(squadra: Any, torneo: Any = None, user_gm: Any = None) -> Optional[Dict[str, Any]]:
    """
    Checks if ownership has concerns regarding head coach performance.
    Instead of firing the coach behind the GM's back, this presents an interactive dialogue.
    """
    if user_gm is None and torneo is not None and (hasattr(torneo, 'current_team_name') or hasattr(torneo, 'prestige_score') or hasattr(torneo, 'owner_approval')):
        user_gm = torneo
        torneo = None

    if not squadra or not getattr(squadra, 'coach', None) or not user_gm:
        return None

    coach = squadra.coach
    profile = getattr(squadra, 'board_profile', None)
    if not profile:
        profile = init_board_profile_for_team(squadra)
        squadra.board_profile = profile

    total_games = squadra.vittorie + squadra.sconfitte
    if total_games < 20:
        return None

    win_rate = squadra.vittorie / max(1, total_games)
    expected_wins = getattr(squadra, 'vittorie_attese', 41.0)
    expected_pct = expected_wins / 82.0

    is_underperforming = (expected_pct - win_rate) >= 0.20 and win_rate < 0.42
    if not is_underperforming and profile.approval_rating > 35.0:
        return None

    active_concern = getattr(squadra, 'pending_board_concern', None)
    if active_concern and not active_concern.get("resolved"):
        return active_concern

    concern_dialogue = {
        "id": f"concern_season_{getattr(torneo, 'season_number', 1)}_game_{total_games}",
        "date": f"Gameday {total_games}",
        "resolved": False,
        "owner_name": profile.owner_name,
        "coach_name": coach.nome,
        "title": f"⚠️ URGENT BOARD SUMMIT: Concerns Regarding Head Coach {coach.nome}",
        "message": (
            f"General Manager, the Board has summoned this emergency meeting. "
            f"Our record stands at a disappointing {squadra.vittorie}-{squadra.sconfitte} despite our expectations. "
            f"Several board members are demanding the dismissal of coach {coach.nome}. "
            f"As General Manager, the decision rests in your hands. How do you respond?"
        ),
        "options": [
            {
                "key": "protect",
                "label": "🛡️ 'He is our guy for the long haul. I stake my own reputation on him.'",
                "description": "You guarantee coach immunity for the season. Transfer accountability to yourself (-12% GM approval, +20 Coach Loyalty).",
                "gm_impact": -12.0,
                "coach_loyalty_boost": 20
            },
            {
                "key": "mandate_tactics",
                "label": "📋 'We will mandate immediate tactical and rotational changes.'",
                "description": "Hold a tactical review with the coach. Forces an adjustment in pace and shot distribution without firing (-4% GM approval).",
                "gm_impact": -4.0,
                "coach_loyalty_boost": 0
            },
            {
                "key": "authorize_firing",
                "label": "🚪 'I agree. It is time to part ways and find a new voice.'",
                "description": "Authorize the head coach's dismissal. You enter the coaching carousel to hire a successor (+6% Board relief).",
                "gm_impact": 6.0,
                "coach_loyalty_boost": -50
            }
        ]
    }

    squadra.pending_board_concern = concern_dialogue
    return concern_dialogue


def resolve_board_concern(squadra: Any, arg2: Any, arg3: Any = None, torneo: Any = None) -> Dict[str, Any]:
    """
    Executes the GM's response to the Board Concern dialogue.
    Supports both:
      resolve_board_concern(squadra, "protect", user_gm)
      resolve_board_concern(squadra, user_gm, "protect", torneo)
    """
    if isinstance(arg2, str):
        decision_key = arg2
    elif isinstance(arg3, str):
        decision_key = arg3
    else:
        decision_key = str(arg2)

    concern = getattr(squadra, 'pending_board_concern', None)
    if not concern:
        return {"success": False, "message": "No pending board concern dialogue found."}

    profile = getattr(squadra, 'board_profile', None)
    coach = getattr(squadra, 'coach', None)

    if decision_key == "protect":
        if profile:
            profile.approval_rating = max(10.0, profile.approval_rating - 12.0)
        if coach:
            coach.job_security = 90.0
        concern["resolved"] = True
        concern["resolution"] = f"GM backed Coach {coach.nome if coach else ''} unconditionally."
        squadra.pending_board_concern = None
        return {
            "success": True,
            "decision": "protect",
            "message": f"You stood firmly behind coach {coach.nome if coach else ''}. The Board agreed to grant him time, but your own seat will warm up if results do not turn around soon."
        }

    elif decision_key == "mandate_tactics":
        if profile:
            profile.approval_rating = max(10.0, profile.approval_rating - 4.0)
        if coach:
            coach.job_security = 60.0
        concern["resolved"] = True
        concern["resolution"] = "Mandated tactical review."
        squadra.pending_board_concern = None
        return {
            "success": True,
            "decision": "mandate_tactics",
            "message": "You ordered an immediate review of defensive schemes and substitution patterns with the coaching staff."
        }

    elif decision_key == "authorize_firing":
        fired_coach_name = coach.nome if coach else "Coach"
        squadra.coach = None
        if profile:
            profile.approval_rating = min(99.0, profile.approval_rating + 6.0)
        concern["resolved"] = True
        concern["resolution"] = f"Dismissed coach {fired_coach_name}."
        squadra.pending_board_concern = None
        return {
            "success": True,
            "decision": "authorize_firing",
            "message": f"Coach {fired_coach_name} has been relieved of his duties. Head to the Coaching Office to hire your next head coach."
        }

    return {"success": False, "message": "Invalid decision key."}


# =====================================================================
# FRANCHISE JOB CAROUSEL & TEAM SWITCHING
# =====================================================================

def generate_job_carousel_offers(torneo: Any, user_gm: Any) -> List[Dict[str, Any]]:
    """
    Generates dynamic franchise job vacancies and offers across the 30 NBA franchises.
    Available during the Offseason or whenever the user resigns/explores market.
    """
    all_teams = getattr(torneo, 'squadre', [])
    if not all_teams:
        return []

    current_team_name = getattr(user_gm, 'current_team_name', "")

    other_teams = [t for t in all_teams if t.nome != current_team_name]
    random.shuffle(other_teams)

    num_openings = min(len(other_teams), random.randint(4, 6))
    suitor_teams = other_teams[:num_openings]

    offers = []
    gm_prestige = getattr(user_gm, 'prestige_score', 65.0)

    for team in suitor_teams:
        roster = getattr(team, 'roster', [])
        roster_ovrs = [g.ovr for g in roster] if roster else [75]
        top5 = sorted(roster_ovrs, reverse=True)[:5]
        avg_top5 = round(sum(top5) / max(1, len(top5)), 1)
        stars = [g.nome for g in roster if getattr(g, 'ovr', 0) >= 84]

        if avg_top5 >= 83.5:
            expectation = "Championship Contention"
            min_salary = 6.0
            max_salary = 9.5
            patience = 2
            personality = "Spendaccione"
            req_prestige = 75.0
        elif avg_top5 >= 78.5:
            expectation = "Direct Playoff Berth"
            min_salary = 4.5
            max_salary = 7.0
            patience = 3
            personality = "Bilanciato"
            req_prestige = 60.0
        else:
            expectation = "Youth Rebuild & Draft Assets"
            min_salary = 3.5
            max_salary = 5.5
            patience = 5
            personality = "Ricostruttore"
            req_prestige = 45.0

        contract_years = random.choice([3, 4, 4, 5])
        offered_salary = round(random.uniform(min_salary, max_salary), 1)
        team_payroll = round(getattr(team, 'payroll', 140.0), 1)
        cap_space = round(max(0.0, 155.0 - team_payroll), 1)
        owner_name = getattr(getattr(team, 'board_profile', None), 'owner_name', 'Ownership Group') or 'Ownership Group'

        offers.append({
            "team_name": team.nome,
            "conference": getattr(team, 'conference', 'East'),
            "owner_name": owner_name,
            "owner_personality": personality,
            "patience_level": patience,
            "roster_avg_top5": avg_top5,
            "roster_ovr": int(round(avg_top5)),
            "stars": stars[:2],
            "payroll": team_payroll,
            "cap_space": cap_space,
            "expectation": expectation,
            "offered_years": contract_years,
            "years": contract_years,
            "offered_salary": offered_salary,
            "salary_per_year": offered_salary,
            "prestige_required": req_prestige,
            "min_prestige": req_prestige,
            "is_eligible": gm_prestige >= req_prestige,
            "prestige_match": "High" if gm_prestige >= req_prestige else "Low"
        })

    return offers


def switch_user_franchise(torneo: Any, user_gm: Any, target_team_name: str, offer_or_years: Any = 4, salary: float = 5.0) -> Dict[str, Any]:
    """
    Executes a front office franchise switch:
    - Moves user to the target franchise.
    - Records old tenure in GM history.
    - Updates contracts and board profiles.
    """
    if isinstance(offer_or_years, dict):
        years = offer_or_years.get("offered_years", offer_or_years.get("years", 4))
        salary = offer_or_years.get("offered_salary", offer_or_years.get("salary_per_year", 5.0))
    else:
        try:
            years = int(offer_or_years)
        except Exception:
            years = 4

    if not torneo or not hasattr(torneo, 'squadre'):
        return {"success": False, "error": "Tournament not active."}

    all_teams = torneo.squadre
    target_team = next((t for t in all_teams if t.nome == target_team_name), None)
    if not target_team:
        return {"success": False, "error": f"Franchise '{target_team_name}' not found in league."}

    old_team = getattr(torneo, 'squadra_giocatore', None)
    old_team_name = old_team.nome if old_team else "Previous Team"

    if hasattr(user_gm, 'teams_managed_history'):
        user_gm.teams_managed_history.append({
            "team": old_team_name,
            "seasons": getattr(user_gm, 'seasons_managed', 1),
            "titles": getattr(user_gm, 'titles_won', 0)
        })

    user_gm.current_team_name = target_team_name
    if hasattr(user_gm, 'contract') and user_gm.contract:
        user_gm.contract.years_remaining = years
        user_gm.contract.total_years = years
        user_gm.contract.salary_per_year = salary
        user_gm.contract.can_extend = False
        user_gm.contract.extension_offered = None

    torneo.squadra_giocatore = target_team

    # Update GM prestige slightly for landing a new contract
    if hasattr(user_gm, 'prestige_score'):
        user_gm.prestige_score = min(99.0, user_gm.prestige_score + 1.5)

    try:
        profile = init_board_profile_for_team(target_team)
        generate_seasonal_objectives(target_team, profile)
        target_team.board_profile = profile
    except Exception as e:
        logger.warning(f"Warning initializing board profile on team switch: {e}")

    msg = f"Welcome to the {target_team_name}! You have officially taken over as General Manager on a {years}-year deal (${salary:.1f}M/year)."
    return {
        "success": True,
        "message": msg,
        "target_team_name": target_team_name,
        "years": years,
        "salary": salary
    }


