import os
import json
from typing import Any
import logging
logger = logging.getLogger('main_sim')

def export_co_gm_data(torneo: Any, league_state: str, fa_objects: list = None) -> dict:
    """
    Generates a complete strategic Executive Dossier of the franchise and the whole league.
    Optimized both for the human GM's analysis and as a dense context prompt for AI models.

    Generates:
      1. scratch/ai_gm/team_state.json (structured raw data)
      2. scratch/ai_gm/league_executive_dossier.md (highly readable markdown report for AI)
      3. scratch/ai_gm/co_gm_report.md (backwards compatibility)
    """
    scratch_dir = os.path.join(os.path.dirname(__file__), "..", "scratch", "ai_gm")
    os.makedirs(scratch_dir, exist_ok=True)
    
    user_team = getattr(torneo, 'squadra_giocatore', None)
    if not user_team:
        # Spectator mode: pick the first team as the focus
        if getattr(torneo, 'squadre', None) and len(torneo.squadre) > 0:
            user_team = torneo.squadre[0]
        else:
            return {"error": "No active franchise found in the tournament"}
        
    starting_year = getattr(torneo, 'starting_year', 2025)
    current_year = getattr(torneo, 'anno_corrente', starting_year + getattr(torneo, 'season_number', 1) - 1)
    season_number = getattr(torneo, 'season_number', 1)
    
    # -------------------------------------------------------------------------
    # 1. TEAM STATE & ROSTER ANALYTICS
    # -------------------------------------------------------------------------
    roster_data = []
    for p in sorted(user_team.roster, key=lambda x: x.ovr, reverse=True):
        c = p.contract
        s_stats = p.season_stats
        gp = getattr(s_stats, 'partite_giocate', 0)
        ppg = (s_stats.punti / gp) if gp > 0 else 0.0
        rpg = (s_stats.rimbalzi / gp) if gp > 0 else 0.0
        apg = (s_stats.assist / gp) if gp > 0 else 0.0
        fg_pct = ((s_stats.tiri_fatti_2 + s_stats.tiri_fatti_3) / max(1, (s_stats.tiri_tentati_2 + s_stats.tiri_tentati_3))) * 100.0 if (s_stats.tiri_tentati_2 + s_stats.tiri_tentati_3) > 0 else 0.0
        
        status_label = "Healthy"
        if getattr(p, 'infortunato', False):
            inf_nome = getattr(p, 'infortunio_nome', 'Infortunio')
            inf_giorni = getattr(p, 'giorni_infortunio_rimanenti', 0)
            status_label = f"Out ({inf_nome}, {inf_giorni}g)"
        elif getattr(p, 'is_day_to_day', False):
            status_label = "Day-to-Day"

        roster_data.append({
            "name": p.nome,
            "role": p.ruolo,
            "sec_role": getattr(p, 'ruolo_secondario', None),
            "age": p.eta,
            "ovr": p.ovr,
            "pot": p.potenziale,
            "salary": c.salario_annuale if c else 0.0,
            "years": c.anni_rimanenti if c else 0,
            "morale": p.morale,
            "stamina": getattr(p, 'stamina_stagionale', 100.0),
            "status": status_label,
            "gp": gp,
            "ppg": round(ppg, 1),
            "rpg": round(rpg, 1),
            "apg": round(apg, 1),
            "fg_pct": round(fg_pct, 1),
            "is_untouchable": getattr(p, 'is_untouchable', False),
            "on_trade_block": getattr(p, 'on_trade_block', False),
            "3pt": p.abilita.three_point_shot_rating,
            "mid": p.abilita.mid_range_shot_rating,
            "int_def": p.abilita.interior_defense_rating,
            "peri_def": p.abilita.perimeter_defense_rating,
            "vision": p.abilita.passing_vision
        })
        
    picks_data = []
    pick_ownership = getattr(torneo, 'pick_ownership', {})
    pick_protections = getattr(torneo, 'pick_protections', {})
    for year in range(1, 6):
        draft_year = current_year + year - 1
        for pick_key, owner in pick_ownership.get(year, {}).items():
            if owner == user_team.nome:
                prot = pick_protections.get(year, {}).get(pick_key, "Unprotected")
                picks_data.append({
                    "year": draft_year,
                    "key": f"{year}:{pick_key}",
                    "display_name": f"{draft_year} - {pick_key} ({prot})" if prot != "Unprotected" else f"{draft_year} - {pick_key}",
                    "protection": prot
                })
                
    needs = user_team.analizza_roster_per_upgrade() if hasattr(user_team, 'analizza_roster_per_upgrade') else []
    
    # Financial indicators
    salary_cap = getattr(torneo, 'salary_cap', 136.0)
    luxury_tax = getattr(torneo, 'luxury_tax_threshold', 165.0)
    first_apron = getattr(torneo, 'first_apron_threshold', 172.0)
    second_apron = getattr(torneo, 'second_apron_threshold', 182.0)
    
    tax_status = "Under the Tax"
    if user_team.payroll > second_apron:
        tax_status = f"🔴 2nd Apron (+${user_team.payroll - second_apron:.1f}M)"
    elif user_team.payroll > first_apron:
        tax_status = f"🟠 1st Apron (+${user_team.payroll - first_apron:.1f}M)"
    elif user_team.payroll > luxury_tax:
        tax_status = f"🟡 Luxury Tax (+${user_team.payroll - luxury_tax:.1f}M)"
    
    team_state = {
        "team_name": user_team.nome,
        "conference": user_team.conference,
        "current_year": current_year,
        "season_number": season_number,
        "phase": league_state,
        "wins": user_team.vittorie,
        "losses": user_team.sconfitte,
        "win_pct": round((user_team.vittorie / max(1, user_team.vittorie + user_team.sconfitte)) * 100, 1),
        "streak": f"{getattr(user_team, 'striscia_tipo', 'V')}{getattr(user_team, 'striscia_numero', 0)}",
        "team_goal": getattr(user_team, 'team_goal', 'Contender'),
        "payroll": round(user_team.payroll, 1),
        "cap_space": round(user_team.salary_cap_space, 1),
        "tax_status": tax_status,
        "needs": needs,
        "roster": roster_data,
        "picks": picks_data
    }
    
    # -------------------------------------------------------------------------
    # 2. LEAGUE STANDINGS & POWER TIERS
    # -------------------------------------------------------------------------
    all_teams = getattr(torneo, 'squadre', [])
    east_standings = sorted([s for s in all_teams if s.conference == "East"], key=lambda s: s.vittorie, reverse=True)
    west_standings = sorted([s for s in all_teams if s.conference == "West"], key=lambda s: s.vittorie, reverse=True)
    
    # -------------------------------------------------------------------------
    # 3. LEAGUE TRADE TRACKER (Trades executed in this simulation)
    # -------------------------------------------------------------------------
    from core.save_manager import get_historical_file_path
    trades_log = []
    trades_file = get_historical_file_path("trades_history.txt")
    if os.path.exists(trades_file):
        try:
            with open(trades_file, 'r', encoding='utf-8') as f_tr:
                lines = [line.strip() for line in f_tr if line.strip()]
                # Take the last 20 trades
                trades_log = lines[-20:]
        except Exception:
            logger.warning("Ignored error in export_co_gm_data()", exc_info=True)
            
    # -------------------------------------------------------------------------
    # 4. LEAGUE LEADERS & AWARDS RACE
    # -------------------------------------------------------------------------
    all_league_players = []
    for s in all_teams:
        for p in s.roster:
            p._team_name = s.nome
            all_league_players.append(p)
            
    def get_player_ppg(p):
        gp = getattr(p.season_stats, 'partite_giocate', 0)
        return (p.season_stats.punti / gp) if gp >= 5 else 0.0

    def get_player_rpg(p):
        gp = getattr(p.season_stats, 'partite_giocate', 0)
        return (p.season_stats.rimbalzi / gp) if gp >= 5 else 0.0

    def get_player_apg(p):
        gp = getattr(p.season_stats, 'partite_giocate', 0)
        return (p.season_stats.assist / gp) if gp >= 5 else 0.0

    top_scorers = sorted(all_league_players, key=get_player_ppg, reverse=True)[:5]
    top_rebounders = sorted(all_league_players, key=get_player_rpg, reverse=True)[:5]
    top_passers = sorted(all_league_players, key=get_player_apg, reverse=True)[:5]
    
    # Awards projections
    mvp_cand = getattr(torneo, 'regular_season_mvp', None)
    dpoy_cand = getattr(torneo, 'defensive_player_of_the_year', None)
    getattr(torneo, 'rookie_of_the_year', None)
    getattr(torneo, 'sesto_uomo', None)
    
    # -------------------------------------------------------------------------
    # 5. KEY LEAGUE INJURIES (Medical Intel for stars)
    # -------------------------------------------------------------------------
    league_injuries = []
    for p in all_league_players:
        if getattr(p, 'infortunato', False) and p.ovr >= 78:
            league_injuries.append({
                "player": p.nome,
                "team": getattr(p, '_team_name', 'N/A'),
                "ovr": p.ovr,
                "injury": getattr(p, 'infortunio_nome', 'Infortunio'),
                "days_left": getattr(p, 'giorni_infortunio_rimanenti', 0),
                "is_dtd": getattr(p, 'is_day_to_day', False)
            })
    league_injuries.sort(key=lambda x: x["ovr"], reverse=True)
    
    # -------------------------------------------------------------------------
    # 6. DRAFT PROSPECTS, EXPIRING CONTRACTS & TRADE MARKET TARGETS
    # -------------------------------------------------------------------------
    draft_prospects = []
    draft_class = getattr(torneo, 'draft_class', None)
    if draft_class:
        for p in draft_class[:15]:
            draft_prospects.append({
                "name": getattr(p, 'nome', 'Rookie'),
                "role": getattr(p, 'ruolo', 'SG'),
                "ovr": getattr(p, 'valutazione', 60),
                "pot": getattr(p, 'potenziale', 70),
                "provenance": getattr(p, 'provenance', 'College')
            })
            
    # Expiring contracts (1 year remaining in contract with OVR >= 78)
    expiring_targets = []
    trade_targets_by_role = {"PG": [], "SG": [], "SF": [], "PF": [], "C": []}
    
    for s in all_teams:
        if s.nome == user_team.nome:
            continue
        # Compute team status (Seller if win_pct < 40%, Buyer/Contender if win_pct > 55%)
        s_gp = s.vittorie + s.sconfitte
        s_pct = (s.vittorie / s_gp * 100) if s_gp > 0 else 50.0
        s_status = "Seller (Tanking/Rebuilding)" if s_pct < 42.0 else ("Buyer (Contender)" if s_pct > 56.0 else "Neutral")
        
        for p in s.roster:
            c_p = p.contract
            sal = c_p.salario_annuale if c_p else 0.0
            yrs = c_p.anni_rimanenti if c_p else 0
            
            if c_p and yrs == 1 and p.ovr >= 78:
                expiring_targets.append({
                    "name": p.nome,
                    "team": s.nome,
                    "team_status": s_status,
                    "role": p.ruolo,
                    "ovr": p.ovr,
                    "age": p.eta,
                    "salary": sal
                })
                
            # Fill the trade targets by position (valuable players with OVR >= 77)
            if p.ovr >= 77 and p.ruolo in trade_targets_by_role and not getattr(p, 'is_untouchable', False):
                trade_targets_by_role[p.ruolo].append({
                    "name": p.nome,
                    "team": s.nome,
                    "team_status": s_status,
                    "ovr": p.ovr,
                    "pot": p.potenziale,
                    "age": p.eta,
                    "salary": sal,
                    "years": yrs,
                    "is_trade_block": getattr(p, 'on_trade_block', False)
                })
                
    expiring_targets.sort(key=lambda x: x["ovr"], reverse=True)
    for r in trade_targets_by_role:
        trade_targets_by_role[r].sort(key=lambda x: x["ovr"], reverse=True)
    
    # Free Agency Pool (if in the offseason)
    fa_pool = []
    src_pool = fa_objects if fa_objects is not None else getattr(torneo, 'free_agents_pool', [])
    if src_pool and league_state in ["OFFSEASON_FREE_AGENCY", "FREE_AGENCY", "OFFSEASON_UFA_START", "OFFSEASON_UFA_NEGOTIATION"]:
        for fa in sorted(src_pool, key=lambda x: x.ovr, reverse=True)[:15]:
            fa_pool.append({
                "name": fa.nome,
                "role": fa.ruolo,
                "age": fa.eta,
                "ovr": fa.ovr,
                "pot": fa.potenziale,
                "demand": getattr(fa, '_market_demand', 3.0)
            })

    # -------------------------------------------------------------------------
    # 7. GENERATE DENSE, STRUCTURED MARKDOWN EXECUTIVE DOSSIER FOR AI & GM
    # -------------------------------------------------------------------------
    md_content = []
    md_content.append("# 🏀 Hardwood Basketball Simulator Executive Intelligence Dossier")
    md_content.append(f"> **Franchise Focus:** {user_team.nome} | **Season:** {season_number} ({current_year}) | **Phase:** {league_state.replace('_', ' ')}")
    md_content.append("\n---\n")
    
    # 1. Team State
    md_content.append(f"## 🏢 1. Franchise Diagnosis: {user_team.nome}")
    md_content.append(f"- **W-L Record:** {user_team.vittorie}-{user_team.sconfitte} ({team_state['win_pct']}% Win Rate) | **Streak:** {team_state['streak']}")
    md_content.append(f"- **Corporate Goal:** `{team_state['team_goal']}` | **Detected Roster Needs:** `{', '.join(needs) if needs else 'Balanced Roster'}`")
    md_content.append(f"- **Finanze:** Payroll: **${team_state['payroll']}M** | Cap Space: **${team_state['cap_space']}M** | Status Tax: {tax_status}")
    md_content.append(f"- **Parametri CBA Lega:** Salary Cap: ${salary_cap}M | Tax: ${luxury_tax}M | 1st Apron: ${first_apron}M | 2nd Apron: ${second_apron}M\n")
    
    # CBA Rules reminder for AI
    md_content.append("> 📌 **CBA Rules for Valid Trades (Guidelines for the AI):**")
    md_content.append(f"> 1. **Cap Absorption:** Teams under the Cap (${salary_cap}M) can absorb salaries up to their available cap space.")
    md_content.append("> 2. **Salary Matching:** Teams over the Cap must match salaries within **125% + $0.25M** of the outgoing salary.")
    md_content.append("> 3. **Stepien Rule:** A team cannot be left without first-round picks in two consecutive future years.")
    md_content.append("> 4. **Untouchable Players:** Players marked `[Untouchable]` cannot be traded except for offers they can't refuse.\n")

    # Roster Table
    md_content.append(f"### 👥 Active Roster & Technical Hierarchy ({user_team.nome})")
    md_content.append("| Player | Position | Age | OVR | POT | Salary | Years | Status | PPG | RPG | APG | FG% | 3PT | Def(I/P) |")
    md_content.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for p in roster_data:
        tag = " 🔒[Untouchable]" if p['is_untouchable'] else (" 🏷️[On Block]" if p['on_trade_block'] else "")
        md_content.append(f"| **{p['name']}**{tag} | {p['role']} | {p['age']} | **{p['ovr']}** | {p['pot']} | ${p['salary']:.1f}M | {p['years']}y | {p['status']} | {p['ppg']} | {p['rpg']} | {p['apg']} | {p['fg_pct']}% | {p['3pt']} | {p['int_def']}/{p['peri_def']} |")
    md_content.append("\n")
    
    # Future Picks
    md_content.append(f"### 🎟️ Assets & Draft Picks ({user_team.nome})")
    if picks_data:
        for p in picks_data:
            md_content.append(f"- `{p['display_name']}`")
    else:
        md_content.append("- No future draft picks owned.")
    md_content.append("\n---\n")
    
    # 2. League Standings
    md_content.append("## 🏆 2. Power Map & NBA Standings")
    md_content.append("| Eastern Conference (Top 8) | W-L | | Western Conference (Top 8) | W-L |")
    md_content.append("| :--- | :---: | | :--- | :---: |")
    for i in range(8):
        e_t = east_standings[i] if i < len(east_standings) else None
        w_t = west_standings[i] if i < len(west_standings) else None
        e_name = e_t.nome if e_t else "-"
        e_rec = f"{e_t.vittorie}-{e_t.sconfitte}" if e_t else "-"
        w_name = w_t.nome if w_t else "-"
        w_rec = f"{w_t.vittorie}-{w_t.sconfitte}" if w_t else "-"
        md_content.append(f"| {e_name} | {e_rec} | | {w_name} | {w_rec} |")
    md_content.append("\n---\n")
    
    # 3. Trade Market & Targets by Role
    md_content.append("## 🔄 3. Trade Targets & Assets Available on Other Teams")
    md_content.append("The following players are prime market targets available on rival franchises:")
    md_content.append("| Position | Player | Team | OVR (POT) | Age | Salary | Years | Team Status |")
    md_content.append("| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :--- |")
    for role_name in ["PG", "SG", "SF", "PF", "C"]:
        for t_p in trade_targets_by_role[role_name][:4]:
            block_tag = " 🏷️" if t_p.get("is_trade_block") else ""
            md_content.append(f"| **{role_name}** | **{t_p['name']}**{block_tag} | {t_p['team']} | **{t_p['ovr']}** ({t_p['pot']}) | {t_p['age']} | ${t_p['salary']:.1f}M | {t_p['years']}y | {t_p['team_status']} |")
    md_content.append("\n---\n")
    
    # 4. Stat Leaders & Awards
    md_content.append("## ⭐ 4. Statistical Leaders & Awards Race")
    md_content.append("- **Top Scorers:** " + ", ".join([f"{p.nome} ({getattr(p, '_team_name', '')}) {get_player_ppg(p):.1f} PPG" for p in top_scorers]))
    md_content.append("- **Top Rebounders:** " + ", ".join([f"{p.nome} ({getattr(p, '_team_name', '')}) {get_player_rpg(p):.1f} RPG" for p in top_rebounders]))
    md_content.append("- **Top Assistman:** " + ", ".join([f"{p.nome} ({getattr(p, '_team_name', '')}) {get_player_apg(p):.1f} APG" for p in top_passers]))
    if mvp_cand:
        md_content.append(f"- 🏅 **Frontrunner MVP:** {getattr(mvp_cand, 'nome', str(mvp_cand))}")
    if dpoy_cand:
        md_content.append(f"- 🛡️ **Frontrunner DPOY:** {getattr(dpoy_cand, 'nome', str(dpoy_cand))}")
    md_content.append("\n---\n")

    # 5. Key League Injuries
    md_content.append("## 🏥 5. League Medical Report (Key Absences)")
    if league_injuries:
        md_content.append("| Player | Team | OVR | Diagnosis | Time Remaining |")
        md_content.append("| :--- | :--- | :---: | :--- | :---: |")
        for inj in league_injuries[:8]:
            md_content.append(f"| **{inj['player']}** | {inj['team']} | {inj['ovr']} | {inj['injury']} | {inj['days_left']} partite |")
    else:
        md_content.append("- No serious injuries among the league's stars.")
    md_content.append("\n---\n")

    # 6. Draft & Expiring Targets
    md_content.append("## 🔮 6. Scouting & Expiring Contracts")
    if draft_prospects:
        md_content.append("### 🎓 Top 5 Incoming Draft Prospects")
        md_content.append("| Rank | Name | Position | Est. OVR | POT | Origin |")
        md_content.append("| :---: | :--- | :---: | :---: | :---: | :--- |")
        for idx, dp in enumerate(draft_prospects[:5]):
            md_content.append(f"| #{idx+1} | **{dp['name']}** | {dp['role']} | {dp['ovr']} | {dp['pot']} | {dp['provenance']} |")
        md_content.append("\n")

    if expiring_targets:
        md_content.append("### 🎯 Stars on Expiring Contracts (1y left - Offseason/FA Targets)")
        md_content.append("| Player | Team | Position | OVR | Age | Salary | Team Status |")
        md_content.append("| :--- | :--- | :---: | :---: | :---: | :---: | :--- |")
        for exp in expiring_targets[:8]:
            md_content.append(f"| **{exp['name']}** | {exp['team']} | {exp['role']} | **{exp['ovr']}** | {exp['age']} | ${exp['salary']:.1f}M | {exp['team_status']} |")
        md_content.append("\n")
        
    full_markdown_text = "\n".join(md_content)
    
    # Write JSON and MD files to disk
    json_path = os.path.join(scratch_dir, "team_state.json")
    with open(json_path, 'w', encoding='utf-8') as f_json:
        json.dump(team_state, f_json, indent=4)
        
    dossier_md_path = os.path.join(scratch_dir, "league_executive_dossier.md")
    with open(dossier_md_path, 'w', encoding='utf-8') as f_dossier:
        f_dossier.write(full_markdown_text)
        
    legacy_md_path = os.path.join(scratch_dir, "co_gm_report.md")
    with open(legacy_md_path, 'w', encoding='utf-8') as f_legacy:
        f_legacy.write(full_markdown_text)
        
    return {
        "success": True,
        "json_path": json_path,
        "md_path": dossier_md_path,
        "markdown_content": full_markdown_text,
        "team_state": team_state,
        "league_standings": {
            "east": [{"name": s.nome, "wins": s.vittorie, "losses": s.sconfitte} for s in east_standings],
            "west": [{"name": s.nome, "wins": s.vittorie, "losses": s.sconfitte} for s in west_standings]
        },
        "trades_log": trades_log,
        "league_injuries": league_injuries,
        "top_scorers": [{"name": p.nome, "team": getattr(p, '_team_name', ''), "ppg": round(get_player_ppg(p), 1)} for p in top_scorers],
        "top_rebounders": [{"name": p.nome, "team": getattr(p, '_team_name', ''), "rpg": round(get_player_rpg(p), 1)} for p in top_rebounders],
        "top_passers": [{"name": p.nome, "team": getattr(p, '_team_name', ''), "apg": round(get_player_apg(p), 1)} for p in top_passers],
        "draft_prospects": draft_prospects,
        "expiring_targets": expiring_targets,
        "fa_pool": fa_pool
    }
