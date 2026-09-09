#!/usr/bin/env python3
"""
Pulls live standings + recent transactions + weekly box scores for the
"Come Get Some" 2026 league from ESPN and writes them to data.json, which the
tracker page (index.html) fetches client-side to render live.

Auth: needs ESPN_S2 and SWID env vars (your ESPN session cookies), since this
is a private league. In GitHub Actions these come from encrypted repo secrets;
locally you can set them yourself to test:
    ESPN_S2="..." SWID="{...}" python fetch_espn.py

Requires: pip install espn_api
"""

import os
import sys
import json
from datetime import datetime, timezone

try:
    from espn_api.football import League
except ImportError:
    print("Missing dependency 'espn_api'. Run: pip install espn_api")
    sys.exit(1)

from team_mapping import TEAM_ID_TO_OWNER

LEAGUE_ID = 375325
YEAR = 2026
OUTPUT_FILE = "data.json"


def matchup_type_label(box_score):
    mtype = str(getattr(box_score, "matchup_type", "NONE") or "NONE").upper()
    if mtype in ("NONE", ""):
        return "regular"
    if "WINNERS" in mtype and "BRACKET" in mtype:
        return "playoff"
    return "consolation"


def owner_for(team_id, fallback_name=""):
    return TEAM_ID_TO_OWNER.get(team_id, f"UNMAPPED (ESPN team #{team_id}: {fallback_name})")


def fetch_weekly_scores(league, current_week):
    """Every regular-season + playoff matchup for weeks already played this
    season. Cheap to run daily -- only loops up through current_week."""
    weeks = []
    for week in range(1, (current_week or 0) + 1):
        try:
            box_scores = league.box_scores(week)
        except Exception as e:
            print(f"  Warning: could not fetch week {week} box scores ({e}).")
            continue
        if not box_scores:
            continue
        matchups = []
        any_real_score = False
        for bs in box_scores:
            home_team = getattr(bs, "home_team", None)
            away_team = getattr(bs, "away_team", None)
            home_score = getattr(bs, "home_score", 0) or 0
            away_score = getattr(bs, "away_score", 0) or 0
            if home_score or away_score:
                any_real_score = True
            home_id = getattr(home_team, "team_id", None) if home_team not in (None, 0) else None
            away_id = getattr(away_team, "team_id", None) if away_team not in (None, 0) else None
            home_name = getattr(home_team, "team_name", "") if home_team not in (None, 0) else ""
            away_name = getattr(away_team, "team_name", "") if away_team not in (None, 0) else ""
            matchups.append({
                "home_team_id": home_id,
                "home_owner": owner_for(home_id, home_name) if home_id is not None else "BYE",
                "home_score": round(home_score, 1),
                "away_team_id": away_id,
                "away_owner": owner_for(away_id, away_name) if away_id is not None else "BYE",
                "away_score": round(away_score, 1),
                "type": matchup_type_label(bs),
            })
        if any_real_score:
            weeks.append({"week": week, "matchups": matchups})
    return weeks


def main():
    espn_s2 = os.environ.get("ESPN_S2")
    swid = os.environ.get("SWID")
    if not espn_s2 or not swid:
        print("ERROR: ESPN_S2 and SWID environment variables must both be set.")
        sys.exit(1)

    league = League(league_id=LEAGUE_ID, year=YEAR, espn_s2=espn_s2, swid=swid)

    # --- Standings ---
    standings = []
    for team in league.teams:
        owner = owner_for(team.team_id, team.team_name)
        standings.append({
            "team_id": team.team_id,
            "owner": owner,
            "espn_team_name": team.team_name,
            "wins": team.wins,
            "losses": team.losses,
            "ties": getattr(team, "ties", 0),
            "pf": round(team.points_for, 1),
            "pa": round(team.points_against, 1),
        })
    # Standard fantasy sort: wins desc, then points-for desc as tiebreak.
    standings.sort(key=lambda t: (-t["wins"], -t["pf"]))

    # --- Recent transactions (adds/drops/trades) ---
    transactions = []
    try:
        activity = league.recent_activity(size=50)
        for act in activity:
            for entry in act.actions:
                # entry is typically (team, action_str, player, bid_amount)
                team = entry[0]
                action = entry[1]
                player = entry[2] if len(entry) > 2 else ""
                team_id = getattr(team, "team_id", None)
                owner = TEAM_ID_TO_OWNER.get(team_id, str(team))
                transactions.append({
                    "date": datetime.fromtimestamp(
                        act.date / 1000, tz=timezone.utc
                    ).isoformat(),
                    "owner": owner,
                    "action": str(action),
                    "player": str(player),
                })
    except Exception as e:
        print(f"Warning: could not fetch transactions ({e}). Continuing with standings only.")

    # --- Weekly box scores (feeds the 2026 Scoreboard section) ---
    current_week = getattr(league, "current_week", 0) or 0
    weekly_scores = fetch_weekly_scores(league, current_week)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_week": current_week,
        "standings": standings,
        "transactions": transactions,
        "weekly_scores": weekly_scores,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {OUTPUT_FILE}: {len(standings)} teams, {len(transactions)} recent transactions, "
          f"{len(weekly_scores)} weeks of box scores.")

    unmapped = [s for s in standings if s["owner"].startswith("UNMAPPED")]
    if unmapped:
        print("\n*** ACTION NEEDED — some ESPN team IDs aren't mapped to owner names yet: ***")
        for s in unmapped:
            print(f"  ESPN team #{s['team_id']}: \"{s['espn_team_name']}\"")
        print("Add these to team_mapping.py's TEAM_ID_TO_OWNER dict, commit, and re-run.")


if __name__ == "__main__":
    main()
