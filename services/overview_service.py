"""Small, cached race/standings summaries for the public-facing overview.

This uses the same Jolpica (Ergast-compatible) source as FastF1, without loading
laps or telemetry. A race is considered completed only when the source has
published its classification, never because a scheduled weekend has started.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
import time
from typing import Any

import requests
import streamlit as st


JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"
_REQUEST_TIMEOUT = (3, 7)
_REQUEST_LOCK = Lock()
_last_request_at = 0.0


def _number(value: Any, *, integer: bool = False) -> int | float | None:
    try:
        return int(value) if integer else float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _driver_fields(driver: dict[str, Any]) -> dict[str, Any]:
    return {
        "driver_id": str(driver.get("driverId", "")),
        "driver_code": str(driver.get("code", "")),
        "driver": " ".join(
            str(driver.get(key, "")).strip()
            for key in ("givenName", "familyName")
            if driver.get(key)
        ),
    }


@st.cache_data(ttl=900, max_entries=36, show_spinner=False)
def _get_json(path: str) -> dict[str, Any]:
    global _last_request_at
    # Season switches and concurrent visitors share this process-wide pacing.
    # Successful responses are cached; exceptions are deliberately not cached.
    with _REQUEST_LOCK:
        delay = 0.4 - (time.monotonic() - _last_request_at)
        if delay > 0:
            time.sleep(delay)
        _last_request_at = time.monotonic()
    response = requests.get(
        f"{JOLPICA_BASE}/{path}/",
        params={"format": "json", "limit": 100},
        headers={"Accept": "application/json", "User-Agent": "RaceHypeStudio/1.0"},
        timeout=_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("MRData"), dict):
        raise ValueError("The results provider returned an unexpected response.")
    data = payload["MRData"]
    # Never present an unexpectedly paginated response as a complete table.
    total = _number(data.get("total"), integer=True)
    limit = _number(data.get("limit"), integer=True)
    if total is not None and limit is not None and total > limit:
        raise ValueError("The results provider returned an incomplete table.")
    data["_fetched_at"] = datetime.now(timezone.utc).isoformat()
    return data


def _parse_latest_race(data: dict[str, Any], year: int) -> dict[str, Any] | None:
    table = data.get("RaceTable")
    if not isinstance(table, dict) or not isinstance(table.get("Races"), list):
        raise ValueError("The results provider returned an unexpected race table.")
    completed = [
        race
        for race in table["Races"]
        if isinstance(race, dict)
        and _number(race.get("season"), integer=True) == year
        and isinstance(race.get("Results"), list)
        and race["Results"]
    ]
    if not completed:
        return None
    race = max(completed, key=lambda item: _number(item.get("round"), integer=True) or 0)
    circuit = race.get("Circuit", {})
    location = circuit.get("Location", {})
    results = []
    for item in race["Results"]:
        team = item.get("Constructor", {})
        results.append(
            {
                "position": _number(item.get("position"), integer=True),
                "position_text": str(item.get("positionText", "")),
                **_driver_fields(item.get("Driver", {})),
                "team": str(team.get("name", "")),
                "team_id": str(team.get("constructorId", "")),
                "points": _number(item.get("points")),
                "status": str(item.get("status", "")),
                "time": str(item.get("Time", {}).get("time", "")),
                "laps": _number(item.get("laps"), integer=True),
                "grid": _number(item.get("grid"), integer=True),
            }
        )
    results.sort(key=lambda item: item["position"] or 999)
    return {
        "year": year,
        "round": _number(race.get("round"), integer=True),
        "event_name": str(race.get("raceName", "")),
        "date": str(race.get("date", "")),
        "circuit": str(circuit.get("circuitName", "")),
        "circuit_id": str(circuit.get("circuitId", "")),
        "locality": str(location.get("locality", "")),
        "country": str(location.get("country", "")),
        "results": results,
    }


def _parse_standings(
    data: dict[str, Any], year: int, *, drivers: bool
) -> tuple[list[dict[str, Any]], int | None]:
    table = data.get("StandingsTable")
    if not isinstance(table, dict) or not isinstance(table.get("StandingsLists"), list):
        raise ValueError("The results provider returned an unexpected standings table.")
    lists = [
        item
        for item in table["StandingsLists"]
        if isinstance(item, dict) and _number(item.get("season"), integer=True) == year
    ]
    if not lists:
        return [], None
    latest = max(lists, key=lambda item: _number(item.get("round"), integer=True) or 0)
    key = "DriverStandings" if drivers else "ConstructorStandings"
    if not isinstance(latest.get(key), list):
        raise ValueError("The results provider returned an unexpected standings table.")
    rows = []
    for item in latest[key]:
        row = {
            "position": _number(item.get("position"), integer=True),
            "points": _number(item.get("points")),
            "wins": _number(item.get("wins"), integer=True),
        }
        if drivers:
            teams = item.get("Constructors", [])
            row.update(_driver_fields(item.get("Driver", {})))
            # Preserve every team when a driver changed teams during the season.
            row["team"] = " / ".join(str(team.get("name", "")) for team in teams)
            row["team_id"] = str(teams[0].get("constructorId", "")) if len(teams) == 1 else ""
        else:
            team = item.get("Constructor", {})
            row["team"] = str(team.get("name", ""))
            row["team_id"] = str(team.get("constructorId", ""))
        rows.append(row)
    if drivers:
        rows.sort(key=lambda item: item["position"] or 999)
    else:
        # Canonical constructor order shared by the table and hero. Official
        # classified position preserves the provider's countback for ties.
        rows.sort(key=lambda item: (item["points"] is None, -(item["points"] or 0), item["position"] or 999))
    return rows, _number(latest.get("round"), integer=True)


def _error_message(exc: Exception) -> str:
    if isinstance(exc, requests.Timeout):
        return "The results provider took too long to respond. Please try again later."
    if isinstance(exc, requests.HTTPError):
        return f"The results provider is unavailable (HTTP {exc.response.status_code})."
    if isinstance(exc, requests.RequestException):
        return "Could not connect to the results provider. Please try again later."
    return "The results provider returned an unexpected response. Please try again later."


@st.cache_data(ttl=60, max_entries=12, show_spinner=False)
def get_season_overview(year: int) -> dict[str, Any]:
    """Return a JSON-compatible overview; missing sections stay empty.

    Keys: ``year``, ``source``, ``source_url``, ``fetched_at`` (UTC ISO string),
    ``latest_race`` (None or metadata with full ``results``),
    ``driver_standings``, ``constructor_standings``, their separate
    ``driver_standings_round`` / ``constructor_standings_round`` values,
    ``standings_round`` (only set when both published rounds agree), and
    ``errors`` (section name to a short display-safe explanation).

    Race metadata: year, round, event_name, date (ISO), circuit, circuit_id,
    locality, country, results. Result rows: position, position_text,
    driver_id, driver_code, driver (full name), team, team_id, points,
    status, time (published time/gap, or empty), laps, grid.

    Standings rows: position, points, wins, team, team_id; driver standings
    additionally include driver_id, driver_code, driver. Numeric fields can
    be None if absent in the source. Rows are ordered by classified position.
    Empty data never causes automatic substitution of another season.
    Source responses are cached for 15 minutes. The assembled overview is
    cached for one minute, allowing a failed section to recover independently.
    """
    year = int(year)
    overview: dict[str, Any] = {
        "year": year,
        "source": "Jolpica",
        "source_url": "https://api.jolpi.ca/",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "latest_race": None,
        "driver_standings": [],
        "constructor_standings": [],
        "driver_standings_round": None,
        "constructor_standings_round": None,
        "standings_round": None,
        "errors": {},
    }
    if not 1950 <= year <= datetime.now(timezone.utc).year:
        overview["errors"]["season"] = "Choose a Formula 1 season from 1950 through the current year."
        return overview

    endpoints = {
        "latest_race": f"{year}/last/results",
        "driver_standings": f"{year}/driverStandings",
        "constructor_standings": f"{year}/constructorStandings",
    }
    # Exactly three small requests run together, each with bounded connect/read
    # timeouts and no retry loop. An unavailable section cannot hide the others.
    fetched_times = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {section: pool.submit(_get_json, path) for section, path in endpoints.items()}
        for section, future in pending.items():
            try:
                data = future.result()
                if data.get("_fetched_at"):
                    fetched_times.append(data["_fetched_at"])
                if section == "latest_race":
                    overview[section] = _parse_latest_race(data, year)
                    if overview[section] is None:
                        overview["errors"][section] = "No completed race results have been published for this season yet."
                else:
                    rows, round_number = _parse_standings(data, year, drivers=section == "driver_standings")
                    overview[section] = rows
                    overview[f"{section}_round"] = round_number
                    if not rows:
                        overview["errors"][section] = "Standings have not been published for this season yet."
            except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError) as exc:
                overview["errors"][section] = _error_message(exc)

    if overview["driver_standings_round"] == overview["constructor_standings_round"]:
        overview["standings_round"] = overview["driver_standings_round"]
    if fetched_times:
        overview["fetched_at"] = min(fetched_times)
    return overview
