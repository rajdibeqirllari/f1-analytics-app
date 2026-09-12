from __future__ import annotations

from pathlib import Path

import fastf1
import pandas as pd

from services.export_service import normalize_telemetry


def enable_fastf1_cache(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(path))


def load_fastf1_lap_export(
    year: int,
    event_name: str,
    session_name: str,
    driver: str,
    lap_mode: str = "Fastest",
    lap_number: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    session = fastf1.get_session(int(year), event_name, session_name)
    session.load(laps=True, telemetry=True, weather=False, messages=False)
    laps = session.laps.pick_drivers(str(driver).upper())
    if laps is None or laps.empty:
        raise RuntimeError("FastF1 loaded the session, but found no laps for this driver.")
    if lap_mode == "Fastest":
        lap = laps.pick_fastest()
    else:
        selected = laps[laps["LapNumber"] == int(lap_number or 0)]
        if selected.empty:
            raise RuntimeError(f"FastF1 did not find lap {lap_number}.")
        lap = selected.iloc[0]
    raw = lap.get_telemetry()
    canonical = normalize_telemetry(raw, "FastF1")
    metadata = {
        "source": "FastF1",
        "event": str(session.event.get("EventName", event_name)),
        "session": str(getattr(session, "name", session_name)),
        "driver": str(driver).upper(),
        "lap_number": int(lap.get("LapNumber", 0) or 0),
    }
    return canonical, canonical.copy(), metadata
