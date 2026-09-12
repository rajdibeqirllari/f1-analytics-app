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
                "lap": clip.lap,
                "recording_url": clip.recording_url,
                "local_path": clip.local_path,
                "position": clip.context.position,
                "compound": clip.context.compound,
                "tyre_age": clip.context.tyre_age,
                "last_lap": clip.context.last_lap_time,
            }
        )
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
