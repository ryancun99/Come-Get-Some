#!/usr/bin/env python3
"""
ONE-TIME backfill: pulls every regular-season + playoff matchup (weekly box
score result, not full lineups) for every season 2015-2026 from ESPN.

Feeds two site features:
  1. Full weekly scoreboard for the 2026 season.
  3. Full standings + matchup data for every season (who played who, each
     week, every year), not just final standings.

This is NOT meant to run on a recurring schedule for past years -- history
doesn't change. For 2026 it only pulls weeks that have actually been played
(up to league.current_week), so re-running it later in the season picks up
newly completed weeks. Safe to re-run any time; it always rewrites the full
output file from scratch.

Usage:
    ESPN_S2="..." SWID="{...}" python fetch_matchups_history.py

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
YEARS = list(range(2015, 2027))  # 2015 through 2026 inclusive
OUTPUT_FILE = "matchups_history.json"

# Hard ceiling so a bad settings read can't spin forever. ESPN fantasy football
# seasons never run past week 17-18 including playoffs.
MAX_WEEK_CEILING = 18


def owner_for(team_id, fallback_name=""):
    return TEAM_ID_TO_OWNER.get(team_id, f"UNMAPPED (ESPN team #{team_id}: {fallback_name})")


def matchup_type_label(box_score):
    """espn_api box scores carry a matchup_type like 'NONE', 'WINNERS_BRACKET',
    'LOSERS_BRACKET', 'WINNERS_CONSOLATION_LADDER', etc. Bucket it down to
    something simple for the site to filter on."""
    mtype = str(getattr(box_score, "matchup_type", "NONE") or "NONE").upper()
    if mtype in ("NONE", ""):
        return "regular"
    if "WINNERS" in mtype and "BRACKET" in mtype:
        return "playoff"
    return "consolation"


def main():
    espn_s2 = os.environ.get("ESPN_S2")
    swid = os.environ.get("SWID")
    if not espn_s2 or not swid:
        print("ERROR: ESPN_S2 and SWID environment variables must both be set.")
        sys.exit(1)

    all_years = {}

    for year in YEARS:
        print(f"\n=== Fetching matchups for {year} ===")
        try:
            league = League(league_id=LEAGUE_ID, year=year, espn_s2=espn_s2, swid=swid)
        except Exception as e:
            print(f"  Could not load {year}: {e}")
            all_years[str(year)] = {"error": str(e), "weeks": []}
            continue

        # How many weeks are actually worth asking for?
        reg_season_weeks = getattr(league.settings, "reg_season_count", 14) or 14
        current_week = getattr(league, "current_week", 0) or 0
        if year >= 2026 or current_week:
            # In-progress or current season: only pull weeks that happened.
            last_week_to_try = min(current_week, MAX_WEEK_CEILING) if current_week else reg_season_weeks
        else:
            last_week_to_try = MAX_WEEK_CEILING

        weeks_out = []
        consecutive_empty = 0
        for week in range(1, last_week_to_try + 1):
            try:
                box_scores = league.box_scores(week)
            except Exception as e:
                print(f"  week {week}: could not fetch ({e})")
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                continue

            if not box_scores:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
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

            if not any_real_score and year >= 2026:
                # Scheduled-but-not-played future week for the in-progress season.
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                continue

            consecutive_empty = 0
            weeks_out.append({"week": week, "matchups": matchups})
            print(f"  week {week}: {len(matchups)} matchups")

        all_years[str(year)] = {"weeks": weeks_out}

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league_id": LEAGUE_ID,
        "years": all_years,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    total_weeks = sum(len(y.get("weeks", [])) for y in all_years.values())
    print(f"\nWrote {OUTPUT_FILE}: {len(YEARS)} seasons, {total_weeks} season-weeks total.")


if __name__ == "__main__":
    main()
