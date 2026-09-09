#!/usr/bin/env python3
"""
ONE-TIME backfill: pulls full roster movement (every add / drop / trade) per
team per season, plus an end-of-season roster snapshot as a fallback anchor,
for 2015-2026. Feeds the "full rosters for previous years" site feature.

Important caveat: ESPN's "recent activity" endpoint is the only public source
for add/drop/trade history, and it is NOT guaranteed to retain data for old
seasons -- some early years may come back empty even though nothing is wrong
with the league or this script. Where that happens, the year still gets an
end-of-season roster snapshot, just no move-by-move log. This script prints a
summary at the end so it's obvious which years got full activity data.

Usage:
    ESPN_S2="..." SWID="{...}" python fetch_rosters_history.py

Requires: pip install espn_api
"""

import os
import sys
import json
import time
from datetime import datetime, timezone

try:
    from espn_api.football import League
except ImportError:
    print("Missing dependency 'espn_api'. Run: pip install espn_api")
    sys.exit(1)

from team_mapping import TEAM_ID_TO_OWNER

LEAGUE_ID = 375325
YEARS = list(range(2015, 2027))  # 2015 through 2026 inclusive
OUTPUT_FILE = "rosters_history.json"
ACTIVITY_PAGE_SIZE = 100


def owner_for(team_id, fallback_name=""):
    return TEAM_ID_TO_OWNER.get(team_id, f"UNMAPPED (ESPN team #{team_id}: {fallback_name})")


def player_dict(p):
    return {
        "name": getattr(p, "name", str(p)),
        "position": getattr(p, "position", None),
        "pro_team": getattr(p, "proTeam", None),
        "injury_status": getattr(p, "injuryStatus", None),
    }


def main():
    espn_s2 = os.environ.get("ESPN_S2")
    swid = os.environ.get("SWID")
    if not espn_s2 or not swid:
        print("ERROR: ESPN_S2 and SWID environment variables must both be set.")
        sys.exit(1)

    all_years = {}
    years_with_activity = []
    years_without_activity = []

    for year in YEARS:
        print(f"\n=== Fetching rosters for {year} ===")
        try:
            league = League(league_id=LEAGUE_ID, year=year, espn_s2=espn_s2, swid=swid)
        except Exception as e:
            print(f"  Could not load {year}: {e}")
            all_years[str(year)] = {"error": str(e)}
            continue

        # --- End-of-season (or current, for 2026) roster snapshot ---
        final_rosters = {}
        for team in league.teams:
            owner = owner_for(team.team_id, team.team_name)
            try:
                final_rosters[str(team.team_id)] = {
                    "owner": owner,
                    "espn_team_name": team.team_name,
                    "players": [player_dict(p) for p in team.roster],
                }
            except Exception as e:
                print(f"  Could not read roster for team {team.team_id}: {e}")

        # --- Move-by-move activity log (adds/drops/trades) ---
        activity_out = []
        try:
            activity = league.recent_activity(size=ACTIVITY_PAGE_SIZE)
            for act in activity:
                for entry in act.actions:
                    team = entry[0] if len(entry) > 0 else None
                    action = entry[1] if len(entry) > 1 else ""
                    player = entry[2] if len(entry) > 2 else ""
                    bid = entry[3] if len(entry) > 3 else None
                    team_id = getattr(team, "team_id", None)
                    activity_out.append({
                        "date": datetime.fromtimestamp(
                            act.date / 1000, tz=timezone.utc
                        ).isoformat(),
                        "owner": owner_for(team_id, getattr(team, "team_name", "")) if team_id else str(team),
                        "action": str(action),
                        "player": str(player),
                        "bid_amount": bid,
                    })
            if activity_out:
                years_with_activity.append(year)
            else:
                years_without_activity.append(year)
        except Exception as e:
            print(f"  Warning: could not fetch activity for {year} ({e}).")
            years_without_activity.append(year)

        all_years[str(year)] = {
            "final_rosters": final_rosters,
            "activity": activity_out,
        }
        print(f"  {len(final_rosters)} team rosters, {len(activity_out)} logged moves.")

        # Be polite to ESPN's API -- this script makes a lot of calls across
        # 12 seasons, no need to hammer it.
        time.sleep(0.5)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league_id": LEAGUE_ID,
        "years": all_years,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {OUTPUT_FILE}.")
    print(f"Years WITH move-by-move activity data: {years_with_activity or 'none'}")
    print(f"Years WITHOUT activity data (roster snapshot only): {years_without_activity or 'none'}")
    print("Years without activity data aren't a bug -- ESPN's API sometimes doesn't retain that far back.")


if __name__ == "__main__":
    main()
