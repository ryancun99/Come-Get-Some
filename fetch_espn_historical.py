#!/usr/bin/env python3
"""
One-time (not scheduled) pull of FINAL standings for past seasons, straight from
ESPN, to cross-check against what's already on come-get-some.html.

This is NOT meant to run on a recurring schedule like fetch_espn.py -- history
doesn't change. Run it once, review the output, and use it to spot-check the
site's numbers.

Usage:
    ESPN_S2="..." SWID="{...}" python fetch_espn_historical.py

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

LEAGUE_ID = 375325
YEARS = list(range(2015, 2026))  # 2015 through 2025 inclusive
OUTPUT_FILE = "history_data.json"


def main():
    espn_s2 = os.environ.get("ESPN_S2")
    swid = os.environ.get("SWID")
    if not espn_s2 or not swid:
        print("ERROR: ESPN_S2 and SWID environment variables must both be set.")
        sys.exit(1)

    all_years = {}

    for year in YEARS:
        print(f"\n=== Fetching {year} ===")
        try:
            league = League(league_id=LEAGUE_ID, year=year, espn_s2=espn_s2, swid=swid)
        except Exception as e:
            print(f"  Could not load {year}: {e}")
            all_years[year] = {"error": str(e)}
            continue

        teams = []
        for team in league.teams:
            teams.append({
                "team_id": team.team_id,
                "espn_team_name": team.team_name,
                "wins": team.wins,
                "losses": team.losses,
                "ties": getattr(team, "ties", 0),
                "pf": round(team.points_for, 1),
                "pa": round(team.points_against, 1),
                "final_standing": getattr(team, "final_standing", None),
            })
        teams.sort(key=lambda t: (t.get("final_standing") or 999))

        all_years[year] = {"teams": teams}
        print(f"  {len(teams)} teams found.")
        for t in teams:
            print(f"    #{t['final_standing']}: {t['espn_team_name']} "
                  f"({t['wins']}-{t['losses']}-{t['ties']}, PF {t['pf']}, PA {t['pa']})")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "years": all_years,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {OUTPUT_FILE} covering {len(YEARS)} seasons.")
    print("Upload this file (or paste its contents) back for cross-checking against come-get-some.html.")


if __name__ == "__main__":
    main()
