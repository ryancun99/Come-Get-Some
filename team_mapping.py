# Maps ESPN's internal team_id (stable all season, assigned when the league was
# created) to the owner names used everywhere else on the site.
#
# HOW TO FILL THIS IN:
# The very first time the Action runs, it won't know these yet, so data.json will
# label unmapped teams as "UNMAPPED (ESPN team #N: <espn team name>)". Open data.json
# in the repo (or check the Action's run log), match each ESPN team name to the real
# owner, fill in the dict below, commit, and every future run will use the right names.

TEAM_ID_TO_OWNER = {
    1: "Ryan Cunningham",
    2: "Dan Marinos",
    3: "Chris Dietz",
    5: "ryan grzymala",
    6: "Nicholas Gargiulo & Kevin Crown",
    7: "Daniel Jimenez",
    8: "Bobby Lupo",
    9: "Jonathan Lee",
    10: "Dom Belli",
    12: "Justin Eveland",
    13: "Hanew Alhayek",
    14: "Al Rucc",
}
