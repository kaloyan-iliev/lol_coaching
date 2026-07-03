"""
Summoner's Rift geometry: jungle camp coordinates, map-zone classification,
and objective metadata used to interpret match-v5 timeline positions.

Coordinates are approximate (map units, 0-14820 on both axes) and only need
to be accurate enough for nearest-camp matching against 60s position
snapshots. Cross-checked against ELITE_MONSTER_KILL positions in real
timelines. Patch-dependent values live here so patch drift is a one-file fix.
"""

import math

MAP_SIZE = 14820  # x + y along the river diagonal

# Camp positions per map side. "blue" = bottom-left (teamId 100),
# "red" = top-right (teamId 200).
CAMPS = {
    "blue": {
        "blue_buff": (3800, 7900),
        "gromp": (2100, 8400),
        "wolves": (3850, 6440),
        "raptors": (7000, 5325),
        "red_buff": (7800, 4000),
        "krugs": (8400, 2700),
    },
    "red": {
        "blue_buff": (11100, 7000),
        "gromp": (12700, 6440),
        "wolves": (11000, 8450),
        "raptors": (7850, 9600),
        "red_buff": (7100, 10900),
        "krugs": (6500, 12300),
    },
}

SCUTTLE = {
    "top_river": (4950, 10390),
    "bot_river": (10050, 4590),
}

OBJECTIVE_PITS = {
    "BARON_NASHOR": (5010, 10470),
    "RIFTHERALD": (5010, 10470),
    "HORDE": (5010, 10470),      # void grubs share the baron pit
    "DRAGON": (9860, 4360),
    "ATAKHAN": (9860, 4360),     # spawns near dragon-side river (approx)
}

# Monsters counted by participantFrames.jungleMinionsKilled per camp clear.
# NOTE: calibrate against real data (full clear totals) - krug splits vary by patch.
CAMP_MONSTER_COUNTS = {
    "blue_buff": 1,
    "gromp": 1,
    "wolves": 3,
    "raptors": 6,
    "red_buff": 1,
    "krugs": 10,
    "scuttle": 1,
}

# Rough proximity threshold (map units) for "at this camp / objective"
CAMP_RADIUS = 1500
OBJECTIVE_RADIUS = 3000
NEARBY_ALLY_RADIUS = 2500


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def nearest_camp(pos: tuple[float, float]) -> tuple[str, str, float]:
    """Return (side, camp_name, distance) of the closest jungle camp."""
    best = None
    for side, camps in CAMPS.items():
        for name, cpos in camps.items():
            d = dist(pos, cpos)
            if best is None or d < best[2]:
                best = (side, name, d)
    for river, cpos in SCUTTLE.items():
        d = dist(pos, cpos)
        if d < best[2]:
            best = (river, "scuttle", d)
    return best


def classify_zone(x: float, y: float) -> str:
    """Coarse map-zone label for a position."""
    if x < 2000 and y < 2000:
        return "blue_base"
    if x > MAP_SIZE - 2000 and y > MAP_SIZE - 2000:
        return "red_base"
    # Lanes hug the map edges / the main diagonal
    if (x < 2200 and y > 4000) or (y > MAP_SIZE - 2200 and x < 10800):
        return "top_lane"
    if (y < 2200 and x > 4000) or (x > MAP_SIZE - 2200 and y < 10800):
        return "bot_lane"
    if abs(x - y) < 1400 and 3500 < x < MAP_SIZE - 3500:
        return "mid_lane"
    # River runs along x + y = MAP_SIZE
    if abs((x + y) - MAP_SIZE) < 1500:
        return "top_river" if y > x else "bot_river"
    # Jungle quadrants
    if x + y < MAP_SIZE:  # blue half
        return "blue_jungle_top" if y > x else "blue_jungle_bot"
    return "red_jungle_top" if y > x else "red_jungle_bot"


LANE_ZONES = {"top_lane", "mid_lane", "bot_lane"}


def side_of_team(team_id: int) -> str:
    return "blue" if team_id == 100 else "red"


def is_enemy_jungle(zone: str, team_id: int) -> bool:
    enemy = "red" if team_id == 100 else "blue"
    return zone.startswith(f"{enemy}_jungle")


def is_own_jungle(zone: str, team_id: int) -> bool:
    own = side_of_team(team_id)
    return zone.startswith(f"{own}_jungle")
