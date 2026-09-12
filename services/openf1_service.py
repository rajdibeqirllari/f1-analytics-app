from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd
import requests


OPENF1_BASE = "https://api.openf1.org/v1"
OPENF1_FULL_SESSION_RULE = {
    "car_data": ["session_key", "driver_number"],
    "note": "Fetch full-session car_data without remote date filters, then crop locally for lap exports.",
}


def openf1_get(endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        response = requests.get(f"{OPENF1_BASE}/{endpoint}", params=params, timeout=60)
    except requests.RequestException as exc:
        raise RuntimeError(f"OpenF1 connection failed: {exc}") from exc
    if response.status_code == 404:
        raise RuntimeError(
            f"OpenF1 has no {endpoint} data for this request. "
            "This is a clean no-data response, not an API-key problem."
        )
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"OpenF1 request failed ({response.status_code}) for {response.url}: {exc}"
        ) from exc
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"OpenF1 returned an unexpected {endpoint} response.")
    return payload


def session_code_to_openf1_name(code: str) -> str:
    return {
        "FP1": "Practice 1",
        "FP2": "Practice 2",
        "FP3": "Practice 3",
        "Q": "Qualifying",
        "R": "Race",
        "SQ": "Sprint Qualifying",
        "SS": "Sprint Shootout",
        "S": "Sprint",
    }.get(str(code).upper(), str(code))


def find_openf1_session(year: int, event_search: str, session_code: str) -> dict[str, Any]:
    wanted = session_code_to_openf1_name(session_code).lower()
    query = str(event_search).lower().replace("grand prix", "").strip()
    sessions = openf1_get("sessions", {"year": int(year)})
    matches = []
    for item in sessions:
        searchable = " ".join(
            str(item.get(key, ""))
            for key in (
                "country_name",
                "location",
                "circuit_short_name",
                "meeting_name",
                "meeting_official_name",
            )
        ).lower()
        if str(item.get("session_name", "")).lower() == wanted and query in searchable:
            matches.append(item)
    if not matches:
        raise RuntimeError(
            f"OpenF1 could not find {event_search} / {session_code} in {year}. "
            "The session may not be published by OpenF1 yet."
        )
    return sorted(matches, key=lambda item: str(item.get("date_start", "")), reverse=True)[0]


def get_openf1_driver_number(session_key: int, driver_code: str) -> int:
    code = str(driver_code).strip().upper()
    if code.isdigit():
        return int(code)
    drivers = openf1_get("drivers", {"session_key": int(session_key)})
    for driver in drivers:
        if str(driver.get("name_acronym", "")).upper() == code:
            return int(driver["driver_number"])
    available = ", ".join(
        f"{driver.get('name_acronym', '?')} ({driver.get('driver_number', '?')})"
        for driver in drivers
    )
    raise RuntimeError(f"OpenF1 has no driver {code} in this session. Available: {available}")


def _as_bool(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return str(value).strip().lower() in {"true", "yes", "on"}


def _drs_active(value: Any) -> bool:
    try:
        return int(float(value)) in {10, 12, 14}
    except (TypeError, ValueError):
        return False


def car_data_to_canonical(
    car_data: list[dict[str, Any]],
    *,
    session_key: int,
    driver_number: int,
) -> pd.DataFrame:
    if not car_data:
        raise RuntimeError("OpenF1 returned no car_data rows.")
    car = pd.DataFrame(car_data)
    required = {"date", "speed", "rpm", "n_gear", "throttle", "brake", "drs"}
    missing = sorted(required.difference(car.columns))
    if missing:
        raise RuntimeError(f"OpenF1 car_data is missing columns: {', '.join(missing)}")
    car["date_dt"] = pd.to_datetime(car["date"], utc=True, errors="coerce")
    car = car.dropna(subset=["date_dt"]).sort_values("date_dt").reset_index(drop=True)
    if car.empty:
        raise RuntimeError("OpenF1 car_data contained no valid timestamped rows.")
    time_sec = (car["date_dt"] - car["date_dt"].iloc[0]).dt.total_seconds()
    count = len(car)
    return pd.DataFrame(
        {
            "time_sec": time_sec.astype(float),
            "date": car["date"].astype(str),
            "session_time": time_sec.astype(float),
            "speed_kmh": pd.to_numeric(car["speed"], errors="coerce"),
            "rpm": pd.to_numeric(car["rpm"], errors="coerce"),
            "gear": pd.to_numeric(car["n_gear"], errors="coerce").astype("Int64"),
            "throttle_pct": pd.to_numeric(car["throttle"], errors="coerce").clip(0, 100),
            "brake_active": car["brake"].map(_as_bool),
            "drs_raw": pd.to_numeric(car["drs"], errors="coerce").astype("Int64"),
            "drs_active": car["drs"].map(_drs_active),
            "distance_m": pd.Series([pd.NA] * count, dtype="Float64"),
            "relative_distance": pd.Series([pd.NA] * count, dtype="Float64"),
            "x": pd.Series([pd.NA] * count, dtype="Float64"),
            "y": pd.Series([pd.NA] * count, dtype="Float64"),
            "z": pd.Series([pd.NA] * count, dtype="Float64"),
            "source": "OpenF1",
            "active_aero_mode": pd.Series([pd.NA] * count, dtype="object"),
            "overtake_mode": pd.Series([pd.NA] * count, dtype="object"),
            "boost_mode": pd.Series([pd.NA] * count, dtype="object"),
            "recharge_mode": pd.Series([pd.NA] * count, dtype="object"),
            "session_key": int(session_key),
            "driver_number": int(driver_number),
        }
    )


def load_openf1_full_session(
    year: int,
    event_search: str,
    session_code: str,
    driver_code: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    session = find_openf1_session(year, event_search, session_code)
    session_key = int(session["session_key"])
    driver_number = get_openf1_driver_number(session_key, driver_code)
    # Deliberately no date>= / date<= remote filters.
    car_data = openf1_get(
        "car_data",
        {"session_key": session_key, "driver_number": driver_number},
    )
    return (
        car_data_to_canonical(
            car_data,
            session_key=session_key,
            driver_number=driver_number,
        ),
        session,
    )


def load_openf1_lap(
    year: int,
    event_search: str,
    session_code: str,
    driver_code: str,
    lap_mode: str,
    lap_number: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    session = find_openf1_session(year, event_search, session_code)
    session_key = int(session["session_key"])
    driver_number = get_openf1_driver_number(session_key, driver_code)
    laps = pd.DataFrame(
        openf1_get(
            "laps",
            {"session_key": session_key, "driver_number": driver_number},
        )
    )
    if laps.empty or not {"lap_duration", "date_start"}.issubset(laps.columns):
        raise RuntimeError("OpenF1 returned no timestamped laps for this driver/session.")
    laps = laps.dropna(subset=["lap_duration", "date_start"]).copy()
    if lap_mode == "Fastest":
        if "is_pit_out_lap" in laps:
            laps = laps[laps["is_pit_out_lap"] != True]  # noqa: E712
        lap_row = laps.sort_values("lap_duration").iloc[0]
    else:
        selected = laps[laps["lap_number"] == int(lap_number or 0)]
        if selected.empty:
            raise RuntimeError(f"OpenF1 did not find lap {lap_number}.")
        lap_row = selected.iloc[0]

    # Download the complete stream, then crop on local timestamps.
    full, _ = load_openf1_full_session(year, event_search, session_code, driver_code)
    timestamps = pd.to_datetime(full["date"], utc=True, errors="coerce")
    start = pd.to_datetime(lap_row["date_start"], utc=True)
    end = start + timedelta(seconds=float(lap_row["lap_duration"]))
    lap = full[(timestamps >= start) & (timestamps <= end)].copy()
    if lap.empty:
        raise RuntimeError(
            "OpenF1 found the lap and full-session car_data, but their timestamps did not overlap."
        )
    lap["time_sec"] = lap["time_sec"] - float(lap["time_sec"].iloc[0])
    return lap.reset_index(drop=True), full, session, lap_row.to_dict()
