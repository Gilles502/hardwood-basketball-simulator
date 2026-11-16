# core/league/builder.py
"""
Deterministic league builder: LeagueData -> a starting SQLite database.

No randomness: the same league always produces the same table contents. The schema is copied from
`data/nba_sim_template.db`, plus `teams.franchise_id` (the league's stable team id) and any
ability/tendency column the league schema needs that the template lacks.
"""
import os
import sqlite3

from core import paths
from core.league.schema import ABILITY_KEYS, TENDENCY_KEYS, LeagueData

TEMPLATE_DB = paths.game_path("data", "nba_sim_template.db")


def _copy_schema(conn: sqlite3.Connection) -> None:
    src = sqlite3.connect(TEMPLATE_DB)
    try:
        statements = src.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
            "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, rowid").fetchall()
    finally:
        src.close()
    for (sql,) in statements:
        conn.execute(sql)
    conn.execute("ALTER TABLE teams ADD COLUMN franchise_id TEXT")
    for table, keys in (("abilities", ABILITY_KEYS), ("tendencies", TENDENCY_KEYS)):
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for key in keys:
            if key not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {key} INTEGER DEFAULT 50")


def _populate(conn: sqlite3.Connection, league: LeagueData) -> None:
    team_row = {}
    for fr in league.franchises:
        cur = conn.execute(
            "INSERT INTO teams (name, conference, owner_personality, franchise_id) VALUES (?, ?, ?, ?)",
            (fr.name, fr.conference, fr.owner_personality, fr.id))
        team_row[fr.id] = cur.lastrowid

    entries = []
    for fr in league.franchises:
        for p in league.players[fr.id]:
            entries.append((p, team_row[fr.id]))
    for p in league.free_agents:
        entries.append((p, None))

    for p, team_id in entries:
        cur = conn.execute(
            "INSERT INTO players (name, role, age, overall, potential, provenance, pedigree, morale, fvs, "
            "is_untouchable, years_on_team, teams_drafted, team_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (p["name"], p["role"], p["age"], p["overall"], p["potential"], p["provenance"], p["pedigree"],
             p["morale"], p["fvs"], p["is_untouchable"], p["years_on_team"], p["teams_drafted"], team_id))
        pid = cur.lastrowid
        for table, keys, block in (("abilities", ABILITY_KEYS, p["abilities"]),
                                   ("tendencies", TENDENCY_KEYS, p["tendencies"])):
            conn.execute(
                f"INSERT INTO {table} (player_id, {', '.join(keys)}) VALUES (?, {', '.join('?' * len(keys))})",
                [pid] + [block[k] for k in keys])


def build_league_db(league: LeagueData, dest_path: str) -> None:
    """Builds the starting DB at dest_path. Writes dest_path + '.tmp' first, then replaces atomically,
    so a failed build never leaves a half database (and never touches an existing dest)."""
    tmp_path = dest_path + ".tmp"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    conn = sqlite3.connect(tmp_path)
    try:
        _copy_schema(conn)
        _populate(conn, league)
        conn.commit()
    except BaseException:
        conn.close()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    conn.close()
    os.replace(tmp_path, dest_path)
