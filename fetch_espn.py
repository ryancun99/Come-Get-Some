#!/usr/bin/env python3
"""
Pulls live standings + recent transactions for the "Come Get Some" 2026 league
from ESPN and writes them to data.json, which the tracker page (index.html)
fetches client-side to render live.

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
        owner = TEAM_ID_TO_OWNER.get(
            team.team_id, f"UNMAPPED (ESPN team #{team.team_id}: {team.team_name})"
        )
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

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_week": getattr(league, "current_week", 0),
        "standings": standings,
        "transactions": transactions,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {OUTPUT_FILE}: {len(standings)} teams, {len(transactions)} recent transactions.")

    unmapped = [s for s in standings if s["owner"].startswith("UNMAPPED")]
    if unmapped:
        print("\n*** ACTION NEEDED — some ESPN team IDs aren't mapped to owner names yet: ***")
        for s in unmapped:
            print(f"  ESPN team #{s['team_id']}: \"{s['espn_team_name']}\"")
        print("Add these to team_mapping.py's TEAM_ID_TO_OWNER dict, commit, and re-run.")


if __name__ == "__main__":
    main()
