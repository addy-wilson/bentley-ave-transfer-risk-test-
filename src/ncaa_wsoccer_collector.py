"""
ncaa_wsoccer_collector.py
═════════════════════════
Collects NCAA D1 Women's Soccer player stats from the NCAA API
and outputs a CSV suitable for building a transfer risk model.

Strategy:
  1. /schedule        → get all game dates for each season
  2. /scoreboard      → get game URLs (full IDs) for each date
  3. /game/{id}/boxscore → player stats per game
  4. Aggregate to one row per player per season

Output: ncaa_wsoccer_transfer_risk.csv

Usage:
    pip install requests pandas tqdm
    python ncaa_wsoccer_collector.py
"""

import requests
import pandas as pd
import time
import json
from collections import defaultdict
from tqdm import tqdm

BASE    = "https://ncaa-api.henrygd.me"
SPORT   = "soccer-women"
DIV     = "d1"
DELAY   = 0.22   # stay under 5 req/sec

# Seasons to collect. Women's soccer runs Aug–Nov each year.
SEASONS = ["2024"]

# Months of the women's soccer season
SEASON_MONTHS = ["08", "09", "10", "11"]

session = requests.Session()
session.headers.update({"User-Agent": "transfer-risk-research/1.0"})


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def get(path: str) -> dict | None:
    url = BASE + path
    try:
        r = session.get(url, timeout=15)
        time.sleep(DELAY)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        time.sleep(DELAY)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Get all game dates for a season
# ─────────────────────────────────────────────────────────────────────────────

def get_game_dates(season: str) -> list[str]:
    """Returns list of date strings like '2024-09-20'."""
    dates = []
    for month in SEASON_MONTHS:
        data = get(f"/schedule/{SPORT}/{DIV}/{season}/{month}")
        if not data:
            continue
        for entry in data.get("gameDates", []):
            if entry.get("games", 0) > 0:
                d = entry.get("contest_date")  # format: "09-01-2024"
                if d:
                    # Convert MM-DD-YYYY → YYYY/MM/DD for scoreboard URL
                    parts = d.split("-")
                    if len(parts) == 3:
                        dates.append(f"{parts[2]}/{parts[0]}/{parts[1]}")
    return dates


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Get full game IDs from scoreboard for each date
# ─────────────────────────────────────────────────────────────────────────────

def get_game_ids_for_date(date_path: str) -> list[tuple[str, dict]]:
    """
    Returns list of (full_game_id, game_meta) for each game on that date.
    date_path format: "2024/09/20"
    """
    data = get(f"/scoreboard/{SPORT}/{DIV}/{date_path}")
    if not data:
        return []

    results = []
    for item in data.get("games", []):
        game = item.get("game", {})
        url  = game.get("url", "")          # e.g. "/game/6348656"
        if not url:
            continue
        full_id = url.strip("/").split("/")[-1]
        if not full_id.isdigit():
            continue

        meta = {
            "game_id":      full_id,
            "game_date":    game.get("startDate", ""),
            "home_team":    game.get("home", {}).get("names", {}).get("full", ""),
            "home_seo":     game.get("home", {}).get("names", {}).get("seo", ""),
            "home_score":   game.get("home", {}).get("score", ""),
            "home_winner":  game.get("home", {}).get("winner", False),
            "home_record":  game.get("home", {}).get("description", ""),
            "away_team":    game.get("away", {}).get("names", {}).get("full", ""),
            "away_seo":     game.get("away", {}).get("names", {}).get("seo", ""),
            "away_score":   game.get("away", {}).get("score", ""),
            "away_winner":  game.get("away", {}).get("winner", False),
            "away_record":  game.get("away", {}).get("description", ""),
            "game_state":   game.get("gameState", ""),
        }
        results.append((full_id, meta))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Parse boxscore for player stats
# ─────────────────────────────────────────────────────────────────────────────

# Soccer-specific stat fields we care about
SOCCER_STAT_FIELDS = [
    "goals", "assists", "points", "shots", "shotsOnGoal",
    "minutesPlayed", "goalsAgainst", "saves",
    # field names vary slightly — we try all
    "Shots", "ShotsOnGoal", "Goals", "Assists", "Points",
    "MinutesPlayed", "GoalsAgainst", "Saves",
    "gp", "gs", "min",
]

def parse_boxscore(game_id: str, meta: dict) -> list[dict]:
    """Returns a list of player-game rows from a boxscore."""
    data = get(f"/game/{game_id}/boxscore")
    if not data:
        return []

    rows = []
    teams_info = {t["teamId"]: t for t in data.get("teams", [])}

    for team_box in data.get("teamBoxscore", []):
        team_id  = str(team_box.get("teamId", ""))
        team_inf = teams_info.get(team_id, teams_info.get(int(team_id), {}))
        team_name = team_inf.get("nameFull") or team_inf.get("nameShort", "")
        team_seo  = team_inf.get("seoname", "")

        # Figure out if this team is home/away and their result
        if team_seo and team_seo == meta.get("home_seo"):
            is_home = True
            won     = meta.get("home_winner", False)
            record  = meta.get("home_record", "")
        else:
            is_home = False
            won     = meta.get("away_winner", False)
            record  = meta.get("away_record", "")

        for player in team_box.get("playerStats", []):
            row = {
                "game_id":     game_id,
                "game_date":   meta["game_date"],
                "season":      meta["game_date"][:4] if meta["game_date"] else "",
                "player_first":player.get("firstName", ""),
                "player_last": player.get("lastName", ""),
                "player_num":  player.get("number", ""),
                "position":    player.get("position", ""),
                "stat_type":   player.get("__typename", ""),
                "category":    player.get("category", ""),
                "team_name":   team_name,
                "team_seo":    team_seo,
                "is_home":     is_home,
                "team_won":    won,
                "team_record_at_game": record,
            }
            # Grab all numeric stat fields present
            for field in SOCCER_STAT_FIELDS:
                if field in player:
                    row[f"stat_{field.lower()}"] = player[field]
            # Also grab any unknown fields that look like stats
            for k, v in player.items():
                if k.startswith("__") or k in ("firstName","lastName","number","position","category"):
                    continue
                col = f"stat_{k.lower()}"
                if col not in row:
                    row[col] = v
            rows.append(row)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Aggregate to player-season level
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_player_season(game_rows: pd.DataFrame) -> pd.DataFrame:
    """Roll up game-level rows to one row per player per season."""
    if game_rows.empty:
        return pd.DataFrame()

    # Normalize column names
    game_rows.columns = [c.lower() for c in game_rows.columns]

    # Numeric stat columns
    stat_cols = [c for c in game_rows.columns if c.startswith("stat_")]
    for c in stat_cols:
        game_rows[c] = pd.to_numeric(game_rows[c], errors="coerce")

    group_cols = ["player_first", "player_last", "team_name", "team_seo", "season"]

    agg_dict = {c: "sum" for c in stat_cols}
    agg_dict["game_id"]  = "count"   # = games appeared in
    agg_dict["team_won"] = "sum"     # = wins while this player appeared

    agg = game_rows.groupby(group_cols, as_index=False).agg(agg_dict)
    agg.rename(columns={"game_id": "games_played", "team_won": "team_wins_in"}, inplace=True)

    # Starts (games where minutesPlayed > 45 or shotsOnGoal > 0 is a rough proxy)
    # Best proxy: if minutesPlayed >= 60 treat as start
    min_col = next((c for c in stat_cols if "minute" in c or c == "stat_min"), None)
    if min_col:
        starts = (
            game_rows[game_rows[min_col] >= 60]
            .groupby(group_cols)["game_id"]
            .count()
            .reset_index()
            .rename(columns={"game_id": "est_starts"})
        )
        agg = agg.merge(starts, on=group_cols, how="left")
        agg["est_starts"] = agg["est_starts"].fillna(0).astype(int)
        agg["start_rate"] = agg["est_starts"] / agg["games_played"].replace(0, pd.NA)

    # Win rate
    agg["win_rate"] = agg["team_wins_in"] / agg["games_played"].replace(0, pd.NA)

    # Production per game
    g_col = next((c for c in stat_cols if c == "stat_goals"), None)
    a_col = next((c for c in stat_cols if c == "stat_assists"), None)
    if g_col and a_col:
        agg["production_per_game"] = (
            agg[g_col].fillna(0) + 0.5 * agg[a_col].fillna(0)
        ) / agg["games_played"].replace(0, pd.NA)

    return agg


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    all_game_rows = []

    for season in SEASONS:
        print(f"\n{'━'*60}")
        print(f"  Season {season}")
        print(f"{'━'*60}")

        # Get all game dates
        print("  Getting schedule...")
        dates = get_game_dates(season)
        print(f"  → {len(dates)} game dates found")

        # Get all game IDs
        print("  Getting game IDs from scoreboards...")
        game_metas = []
        for date in tqdm(dates, desc="  Scoreboards"):
            game_metas.extend(get_game_ids_for_date(date))
        # Deduplicate
        seen = set()
        unique_games = []
        for gid, meta in game_metas:
            if gid not in seen:
                seen.add(gid)
                unique_games.append((gid, meta))
        print(f"  → {len(unique_games)} unique games found")

        # Fetch boxscores
        print("  Fetching boxscores...")
        season_rows = []
        failed = 0
        for gid, meta in tqdm(unique_games, desc="  Boxscores"):
            rows = parse_boxscore(gid, meta)
            if rows:
                season_rows.extend(rows)
            else:
                failed += 1

        print(f"  → {len(season_rows)} player-game rows collected ({failed} games failed/empty)")
        all_game_rows.extend(season_rows)

    if not all_game_rows:
        print("\n[ERROR] No data collected.")
        return

    # Save raw game-level data
    raw_df = pd.DataFrame(all_game_rows)
    import os
    os.makedirs("data/raw", exist_ok=True)
    raw_df.to_csv("data/raw/ncaa_wsoccer_raw_games.csv", index=False)
    print(f"\n✓ Raw game rows: {raw_df.shape} → saved to ncaa_wsoccer_raw_games.csv")

    # Aggregate to player-season level
    player_df = aggregate_player_season(raw_df.copy())
    player_df.to_csv("data/raw/ncaa_wsoccer_transfer_risk.csv", index=False)
    print(f"✓ Player-season rows: {player_df.shape} → saved to ncaa_wsoccer_transfer_risk.csv")

    print("\nSample (first 5 rows):")
    print(player_df.head().to_string())
    print("\nColumns:", list(player_df.columns))


if __name__ == "__main__":
    main()
