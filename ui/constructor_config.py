"""Overview scanner calibration. Offsets are CSS pixels; scale is multiplicative."""

DEBUG_CAR_ALIGNMENT = False
SHOWCASE_SEASON = 2026
SCROLL_PER_CONSTRUCTOR_VH = 22

# Every constructor, including the last, receives a full viewport-relative
# segment. Browser geometry resolves this to pixels without any Python rerun.
SHOWCASE_SETTINGS = {
    "scrollPerConstructorVh": SCROLL_PER_CONSTRUCTOR_VH,
    "autoAdvanceMs": 3000,
    "autoTransitionMs": 750,
    "transitionStart": 0.45,
    "transitionEnd": 1.0,
    "finalExitStart": 0.70,
    "finalExitOpacity": 0.78,
    "transitionDistance": 18,
    "settleDistance": 4,
    "verticalDistance": 3,
    "rotationDegrees": 0.25,
    "scaleDrift": 0.012,
    "carWidthPercent": 94,
    "mobileCarWidthPercent": 90,
}

# Canonical asset/calibration mapping, NOT a ranking. Service IDs are preferred;
# normalized display-name aliases handle provider naming differences.
# Positive x = right; positive y = down. Applied separately from scroll motion.
CONSTRUCTOR_ASSETS = {
    "alpine": {"name": "ALPINE", "image": "alpine.png", "aliases": ("alpine", "alpinef1team"), "scale": 1.00, "x": 0, "y": 0},
    "astonmartin": {"name": "ASTON MARTIN", "image": "astonmartin.png", "aliases": ("astonmartin",), "scale": 1.00, "x": 0, "y": 0},
    "audi": {"name": "AUDI", "image": "audi.png", "aliases": ("audi", "audif1team"), "scale": 1.00, "x": 0, "y": 0},
    "cadillac": {"name": "CADILLAC", "image": "cadillac.png", "aliases": ("cadillac", "cadillacf1team"), "scale": 1.00, "x": 0, "y": 0},
    "ferrari": {"name": "SCUDERIA FERRARI", "image": "ferrari.png", "aliases": ("ferrari", "scuderiaferrari"), "scale": 1.00, "x": 0, "y": 0},
    "haas": {"name": "HAAS F1 TEAM", "image": "haas.png", "aliases": ("haas", "haasf1team"), "scale": 1.00, "x": 0, "y": 0},
    "mclaren": {"name": "McLAREN", "image": "mclaren.png", "aliases": ("mclaren",), "scale": 1.00, "x": 0, "y": 0},
    "mercedes": {"name": "MERCEDES-AMG PETRONAS", "image": "mercedes.png", "aliases": ("mercedes", "mercedesamgpetronas"), "scale": 1.00, "x": 0, "y": 0},
    "racingbulls": {"name": "RACING BULLS", "image": "racingbulls.png", "aliases": ("rb", "rbf1team", "racingbulls", "racingbullsf1team"), "scale": 1.00, "x": 0, "y": 0},
    "redbull": {"name": "RED BULL RACING", "image": "redbull.png", "aliases": ("redbull", "redbullracing"), "scale": 1.00, "x": 0, "y": 0},
    "williams": {"name": "WILLIAMS", "image": "williams.png", "aliases": ("williams",), "scale": 1.00, "x": 0, "y": 0},
}


def constructors_from_standings(standings: list[dict]) -> list[dict]:
    """Map the already-ranked shared service rows. Never fetch or invent data."""
    aliases = {alias: key for key, asset in CONSTRUCTOR_ASSETS.items() for alias in asset["aliases"]}
    cars, seen = [], set()
    for rank, row in enumerate(standings, start=1):
        key = None
        for field in ("team_id", "team"):
            normalized = "".join(char for char in str(row.get(field, "")).lower() if char.isalnum())
            key = aliases.get(normalized)
            if key:
                break
        if key is None or key in seen:
            continue
        seen.add(key)
        cars.append({**CONSTRUCTOR_ASSETS[key], "id": key, "index": rank,
                     "points": row.get("points"), "field_size": len(standings)})
    return cars
