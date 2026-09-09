#!/usr/bin/env python3
"""
ONE-TIME backfill: pulls full draft results for every season 2015-2026,
enriched with each player's position and how many fantasy points they scored
that season. Feeds the "League Manager drafting habits" site feature --
positional tendencies, hit/bust tracking (draft slot vs. actual points), and
fun-fact leaderboards. The site computes the actual stats client-side from
this raw data; this script just gets clean raw picks out of ESPN.

Enrichment notes (read before assuming something's "broken"):
  - The draft endpoint itself doesn't include a player's position, so this
    script cross-references that same year's team rosters to fill it in.
    A player who was drafted and later dropped before ever appearing on any
    roster snapshot (rare, but happens with year-of-draft cuts) will show
    position: null instead of guessing.
  - "season_points" is each player's total fantasy points scored that NFL
    season (per ESPN's scoring, not a re-calculation), used to judge value
    vs. draft slot. This means one extra ESPN call per drafted player --
    ~190 players/year x 12 years is a lot of calls, so this script sleeps
    briefly between them. Expect this script to take a while; that's normal.
  - Set FETCH_SEASON_POINTS = False below to skip that enrichment entirely
    and get just the draft picks (fast) if you want the rest of the site
    built first and points added later.

Usage:
    ESPN_S2="..." SWID="{...}" python fetch_draft_history.py

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
OUTPUT_FILE = "draft_history.json"
FETCH_SEASON_POINTS = True
SLEEP_BETWEEN_PLAYER_CALLS = 0.2


def owner_for(team_id, fallback_name=""):
    return TEAM_ID_TO_OWNER.get(team_id, f"UNMAPPED (ESPN team #{team_id}: {fallback_name})")


def build_position_lookup(league):
    """name -> position, from every roster spot on every team, for this year."""
    lookup = {}
    for team in league.teams:
        try:
            for p in team.roster:
                name = getattr(p, "name", None)
                pos = getattr(p, "position", None)
                if name and pos:
                    lookup[name] = pos
        except Exception:
            continue
    return lookup


def season_points_for(league, player_id, player_name):
    if not FETCH_SEASON_POINTS:
        return None
    try:
        info = league.player_info(playerId=player_id) if player_id else league.player_info(name=player_name)
        if info is None:
            return None
        # Different espn_api versions expose this differently -- try the
        # common shapes rather than assuming one.
        total = getattr(info, "total_points", None)
        if total is not None:
            return round(total, 1)
        stats = getattr(info, "stats", None)
        if isinstance(stats, dict):
            season_entry = stats.get(0) or stats.get("0")
            if isinstance(season_entry, dict) and "points" in season_entry:
                return round(season_entry["points"], 1)
            # Fall back to summing weekly entries if there's no season total key.
            weekly_total = sum(
                v.get("points", 0) for k, v in stats.items()
                if isinstance(v, dict) and str(k) != "0"
            )
            if weekly_total:
                return round(weekly_total, 1)
        return None
    except Exception:
        return None


def main():
    espn_s2 = os.environ.get("ESPN_S2")
    swid = os.environ.get("SWID")
    if not espn_s2 or not swid:
        print("ERROR: ESPN_S2 and SWID environment variables must both be set.")
        sys.exit(1)

    all_years = {}

    for year in YEARS:
        print(f"\n=== Fetching draft for {year} ===")
        try:
            league = League(league_id=LEAGUE_ID, year=year, espn_s2=espn_s2, swid=swid)
        except Exception as e:
            print(f"  Could not load {year}: {e}")
            all_years[str(year)] = {"error": str(e), "picks": []}
            continue

        try:
            picks = league.draft
        except Exception as e:
            print(f"  Could not load draft for {year}: {e}")
            all_years[str(year)] = {"error": str(e), "picks": []}
            continue

        if not picks:
            print("  No draft data returned for this year.")
            all_years[str(year)] = {"picks": []}
            continue

        position_lookup = build_position_lookup(league)

        picks_out = []
        for pick in picks:
            team = getattr(pick, "team", None)
            team_id = getattr(team, "team_id", None)
            player_name = getattr(pick, "playerName", None) or ""
            player_id = getattr(pick, "playerId", None)
            round_num = getattr(pick, "round_num", None)
            round_pick = getattr(pick, "round_pick", None)

            entry = {
                "round": round_num,
                "round_pick": round_pick,
                "team_id": team_id,
                "owner": owner_for(team_id, getattr(team, "team_name", "")) if team_id is not None else str(team),
                "player_name": player_name,
                "position": position_lookup.get(player_name),
                "bid_amount": getattr(pick, "bid_amount", None),
                "keeper_status": getattr(pick, "keeper_status", None),
            }

            if FETCH_SEASON_POINTS:
                entry["season_points"] = season_points_for(league, player_id, player_name)
                time.sleep(SLEEP_BETWEEN_PLAYER_CALLS)

            picks_out.append(entry)

        picks_out.sort(key=lambda p: ((p["round"] or 0), (p["round_pick"] or 0)))
        all_years[str(year)] = {"picks": picks_out}
        print(f"  {len(picks_out)} picks captured.")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league_id": LEAGUE_ID,
        "fetched_season_points": FETCH_SEASON_POINTS,
        "years": all_years,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    total_picks = sum(len(y.get("picks", [])) for y in all_years.values())
    print(f"\nWrote {OUTPUT_FILE}: {len(YEARS)} seasons, {total_picks} picks total.")


if __name__ == "__main__":
    main()
