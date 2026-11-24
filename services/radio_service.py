from __future__ import annotations

from pathlib import Path
import re
from typing import Any


RADIO_RACE_ALIASES = {
    "monza": "Italian Grand Prix",
    "italy": "Italian Grand Prix",
    "imola": "Emilia Romagna Grand Prix",
    "silverstone": "British Grand Prix",
    "spa": "Belgian Grand Prix",
    "hungaroring": "Hungarian Grand Prix",
    "zandvoort": "Dutch Grand Prix",
    "suzuka": "Japanese Grand Prix",
    "spielberg": "Austrian Grand Prix",
    "red bull ring": "Austrian Grand Prix",
    "cota": "United States Grand Prix",
    "austin": "United States Grand Prix",
    "interlagos": "Sao Paulo Grand Prix",
    "bahrain": "Bahrain Grand Prix",
    "jeddah": "Saudi Arabian Grand Prix",
    "miami": "Miami Grand Prix",
    "monaco": "Monaco Grand Prix",
    "montreal": "Canadian Grand Prix",
    "canada": "Canadian Grand Prix",
    "barcelona": "Barcelona-Catalunya Grand Prix",
    "barcelona-catalunya": "Barcelona-Catalunya Grand Prix",
    "catalunya": "Barcelona-Catalunya Grand Prix",
    "baku": "Azerbaijan Grand Prix",
    "singapore": "Singapore Grand Prix",
    "mexico": "Mexico City Grand Prix",
    "las vegas": "Las Vegas Grand Prix",
    "qatar": "Qatar Grand Prix",
    "abu dhabi": "Abu Dhabi Grand Prix",
}


def normalize_radio_race_name(value: str) -> str:
    text = str(value or "").strip()
    key = text.lower()
    if key in RADIO_RACE_ALIASES:
        return RADIO_RACE_ALIASES[key]
    bases = {name.lower().replace(" grand prix", "") for name in RADIO_RACE_ALIASES.values()}
    if "grand prix" not in key and key in bases:
        return f"{text} Grand Prix"
    return text


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_")


def _laps_by_time(rows: list[dict[str, Any]], year: int, session_code: str, race: str) -> None:
    """Fill in each clip's lap from when it aired, using OpenF1 lap start times (cached, free).

    The archive gives most clips no lap. A clip belongs to the driver's last lap that started before it aired;
    clips from before the first lap are pre-race. Best effort: without OpenF1 data the laps stay unknown."""
    if not any(r.get("lap") is None and r.get("date") for r in rows):
        return
    try:
        import pandas as pd
        from services.openf1_comparison import historical, resolve
        key = int(resolve(year, race, session_code)["session_key"])
        laps = pd.DataFrame(historical("laps", {"session_key": key}))
        laps["start"] = pd.to_datetime(laps["date_start"], utc=True, format="ISO8601", errors="coerce")
        laps = laps.dropna(subset=["start"])
    except Exception:
        return
    for r in rows:
        if r.get("lap") is not None or not r.get("date") or r.get("driver_number") is None:
            continue
        aired = pd.to_datetime(r["date"], utc=True, errors="coerce")
        mine = laps[laps.driver_number == int(r["driver_number"])].sort_values("start")
        if pd.isna(aired) or mine.empty:
            continue
        before = mine[mine.start <= aired]
        if before.empty:
            r["pre"] = True
        else:
            r["lap"] = int(before.iloc[-1].lap_number)
            r["pre"] = False


def load_radio_session(
    year: int,
    race: str,
    session_code: str,
    *,
    cache_dir: Path,
    output_dir: Path,
    force_refresh: bool = False,
) -> dict[str, Any]:
    import f1radio

    requested = str(race).strip()
    resolved = normalize_radio_race_name(requested)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    f1radio.set_cache_dir(str(cache_dir))
    session = f1radio.load(
        int(year),
        resolved,
        str(session_code).strip().upper(),
        verbose=False,
        force_refresh=bool(force_refresh),
    )
    label = _safe_name(f"radio_{year}_{session.race}_{session.session_type}")
    csv_path = output_dir / f"{label}.csv"
    json_path = output_dir / f"{label}.json"
    session.export_csv(str(csv_path))
    session.export_json(str(json_path))
    rows = []
    for index, clip in enumerate(session.clips):
        rows.append(
            {
                "idx": index,
                "driver": clip.driver,
                "driver_number": clip.driver_number,
                "driver_name": clip.driver_name,
                "team": clip.team,
                "time": clip.time,
                "date": getattr(clip, "date", None),
                # The archive gives clips from before the start a session time of 00:00:00 and no lap.
                "lap": clip.lap if clip.lap is not None else clip.context.lap_number,
                "pre": clip.lap is None and clip.context.lap_number is None and str(clip.time or '') in ('', '00:00:00'),
                "recording_url": clip.recording_url,
                "local_path": clip.local_path,
                "position": clip.context.position,
                "compound": clip.context.compound,
                "tyre_age": clip.context.tyre_age,
                "last_lap": clip.context.last_lap_time,
            }
        )
    _laps_by_time(rows, year, session_code, resolved)
    return {
        "year": session.year,
        "requested_race": requested,
        "resolved_race": resolved,
        "race": session.race,
        "session_type": session.session_type,
        "csv_path": csv_path,
        "json_path": json_path,
        "clips": rows,
    }
