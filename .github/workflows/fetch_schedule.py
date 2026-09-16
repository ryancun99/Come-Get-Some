#!/usr/bin/env python3
"""
One-off pull of the full 2026 regular-season schedule (all 14 weeks) for the
"Come Get Some" league -- team-vs-team pairings for every week, regardless of
whether that week has been played yet. Writes schedule.json.

This is separate from fetch_espn.py (which only pulls results for weeks
already played, for the live tracker) -- this script is for getting the
complete matchup schedule up front, e.g. to check for repeat matchups after
manual schedule edits like a rivalry-week swap.

Run manually via the "Fetch Full Schedule" GitHub Action (workflow_dispatch),
same ESPN_S2 / SWID secrets as the other fetch scripts.
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
REGULAR_SEASON_WEEKS = 14
OUTPUT_FILE = "schedule.json"


def owner_name(team_id):
    return TEAM_ID_TO_OWNER.get(team_id, f"UNMAPPED (ESPN team #{team_id})")


def fetch_week_matchups(league, week):
    """Team-vs-team pairings for one week, regardless of play status.

    Tries the lightweight scoreboard() call first (works for future/unplayed
    weeks since ESPN sets the full schedule before the season starts).
    Falls back to box_scores() if scoreboard() doesn't return anything.
    """
    matchups = []
    try:
        games = league.scoreboard(week)
    except Exception as e:
        print(f"  scoreboard() failed for week {week} ({e}), trying box_scores()...")
        games = None

    if not games:
        try:
            games = league.box_scores(week)
        except Exception as e:
            print(f"  Warning: could not fetch week {week} at all ({e}).")
            return matchups

    for g in games:
        home = getattr(g, "home_team", None)
        away = getattr(g, "away_team", None)
        if home is None or away is None:
            # Bye week (only one side set) or malformed entry -- skip.
            continue
        home_id = getattr(home, "team_id", None)
        away_id = getattr(away, "team_id", None)
        if home_id is None or away_id is None:
            continue
        matchups.append({
            "home_team_id": home_id,
            "home_owner": owner_name(home_id),
            "away_team_id": away_id,
            "away_owner": owner_name(away_id),
        })
    return matchups


def main():
    espn_s2 = os.environ.get("ESPN_S2")
    swid = os.environ.get("SWID")
    if not espn_s2 or not swid:
        print("ERROR: ESPN_S2 and SWID environment variables are required.")
        sys.exit(1)

    league = League(league_id=LEAGUE_ID, year=YEAR, espn_s2=espn_s2, swid=swid)

    weeks_out = {}
    for week in range(1, REGULAR_SEASON_WEEKS + 1):
        print(f"Fetching week {week}...")
        matchups = fetch_week_matchups(league, week)
        if not matchups:
            print(f"  No matchups found for week {week}.")
        weeks_out[str(week)] = matchups

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league_id": LEAGUE_ID,
        "year": YEAR,
        "regular_season_weeks": REGULAR_SEASON_WEEKS,
        "weeks": weeks_out,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
