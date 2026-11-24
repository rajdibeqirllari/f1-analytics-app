"""Lap-relative comparison data shared by video renderers.

Car animation uses elapsed lap time; delta uses matching normalized distance.
Positions are metres. Renderers must disclose any decorative lateral offset.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import fastf1
import fastf1.plotting
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DRS_ACTIVE = {10, 12, 14}


@dataclass(frozen=True)
class VideoSelection:
    year: int
    event: str
    session: str
    driver_a: str
    driver_b: str
    lap_a: int | None = None
    lap_b: int | None = None
    qualifying_part: str = "All"


@dataclass
class ComparisonLap:
    code: str
    name: str
    team: str
    color: str
    number: int
    lap_time: float
    samples: pd.DataFrame
    warnings: list[str]
    source: str = 'FastF1'
    sectors: tuple = (None, None, None)
    unavailable_channels: tuple = ()

    def __post_init__(self):
        self._times = self.samples["t"].to_numpy()
        self._channels = {key: self.samples[key].to_numpy() for key in
                          ("progress", "speed", "throttle", "rpm", "gear", "brake", "drs")}
        distance_rows = self.samples.drop_duplicates("progress", keep="first")
        self._distance_progress = distance_rows["progress"].to_numpy()
        self._distance_times = distance_rows["t"].to_numpy()

    def progress_at(self, elapsed):
        return np.interp(elapsed, self._times, self._channels["progress"])

    def at(self, elapsed: float) -> dict[str, Any]:
        t = min(self.lap_time, max(0.0, float(elapsed)))
        times = self._times
        continuous = ("progress", "speed", "throttle", "rpm")
        result = {key: float(np.interp(t, times, self._channels[key])) for key in continuous}
        idx = min(len(times)-1, max(0, int(np.searchsorted(times, t, side="right")-1)))
        result.update(gear=int(self._channels["gear"][idx]),
                      brake=bool(self._channels["brake"][idx]),
                      drs=bool(self._channels["drs"][idx]),
                      elapsed=t, finished=elapsed >= self.lap_time)
        if 'drs' in self.unavailable_channels:
            result['drs'] = None
        return result

    def time_at_distance(self, progress: float) -> float:
        return float(np.interp(min(1.0, max(0.0, float(progress))), self._distance_progress, self._distance_times))


@dataclass
class Comparison:
    year: int
    event: str
    session: str
    laps: tuple[ComparisonLap, ComparisonLap]
    track: np.ndarray  # normalized distance, x, y, z
    warnings: list[str]

    @property
    def duration(self) -> float:
        return max(lap.lap_time for lap in self.laps)

    def delta_at(self, progress: float) -> float:
        """Positive means A reaches this distance sooner than B."""
        a, b = self.laps
        return b.time_at_distance(progress) - a.time_at_distance(progress)

    def point(self, progress: float) -> np.ndarray:
        progress = min(1.0, max(0.0, float(progress)))
        return np.array([np.interp(progress, self.track[:, 0], self.track[:, i])
                         for i in (1, 2, 3)])


@lru_cache(maxsize=2)
def load_video_session(year: int, event: str, session_code: str):
    cache = ROOT / "fastf1_cache"
    cache.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(str(cache))
    session = fastf1.get_session(int(year), event, session_code)
    session.load(laps=True, telemetry=True, weather=False, messages=False)
    # FastF1 logs download failures but can return normally with no lap data.
    # Raise inside the cached function so an incomplete session is never cached.
    try:
        laps=session.laps
    except fastf1.exceptions.DataNotLoadedError as exc:
        raise ValueError(
            f"Timing data could not be downloaded for {year} {event} ({session_code}). "
            "Since 15 Oct 2026 F1's timing archive (livetiming.formula1.com) refuses downloads without an F1 TV login, "
            "so FastF1 only works for sessions already in your cache."
        ) from exc
    if laps.empty:
        raise ValueError(f"No timed laps are available for {year} {event} ({session_code}). Choose an available session or retry later.")
    return session


def is_qualifying(session) -> bool:
    name = str(getattr(session, "name", "") or "").lower()
    return "qualifying" in name or "shootout" in name


def filtered_laps(session, code: str, qualifying_part: str = "All"):
    laps = session.laps.pick_drivers(code).copy()
    # A Q1/Q2/Q3 choice left over from a qualifying session must never slice a race or practice.
    if qualifying_part != "All" and is_qualifying(session):
        splits = session.laps.split_qualifying_sessions()
        index = int(qualifying_part[-1]) - 1
        part = splits[index]
        if part is None:
            return laps.iloc[:0]
        laps = part.pick_drivers(code).copy()
    return laps.dropna(subset=["LapTime", "LapStartTime"])


def session_catalog(year: int, event: str, session_code: str) -> dict:
    try:
        session = load_video_session(year, event, session_code)
    except Exception as primary:
        from services.openf1_comparison import catalog
        try:
            result = catalog(year, event, session_code)
            result['fallback_reason'] = str(primary)
            return result
        except Exception as secondary:
            raise ValueError(f'FastF1 unavailable: {primary} OpenF1 fallback unavailable: {secondary}') from secondary
    entries = {}
    for number in session.drivers:
        driver = session.get_driver(number)
        code = str(driver.get("Abbreviation") or number)
        laps = filtered_laps(session, code)
        # Drivers without a timed lap stay listed (the picker shows them disabled) instead of vanishing.
        entries[code] = {"name": str(driver.get("FullName") or code),
                         "team": str(driver.get("TeamName") or ''),
                         "color": str(driver.get("TeamColor") or ''),
                         "portrait": '',
                         "laps": sorted(int(n) for n in laps["LapNumber"].unique())}
        if laps.empty:
            entries[code]["status"] = str(driver.get("Status") or '') or 'No timed lap'
        if session_code in {"Q", "SQ"}:
            entries[code]["segments"] = {
                part: sorted(int(n) for n in filtered_laps(session, code, part)["LapNumber"].unique())
                for part in ("Q1", "Q2", "Q3")}
    if sum(1 for e in entries.values() if e["laps"]) < 2:
        raise ValueError("This session has fewer than two drivers with timed laps.")
    return {"drivers": entries, "event": str(session.event.get("EventName", event)),
            "session": str(session.name), "source": "FastF1"}


def prepare_lap_samples(telemetry: pd.DataFrame, lap_start: float, lap_time: float) -> tuple[pd.DataFrame, list[str]]:
    required = {"SessionTime", "Speed", "X", "Y"}
    if not required.issubset(telemetry.columns):
        raise ValueError("The selected lap is missing speed or position telemetry.")
    frame = telemetry.copy()
    frame["t"] = frame["SessionTime"].dt.total_seconds() - lap_start
    frame = frame.dropna(subset=["t", "Speed", "X", "Y"]).sort_values("t").drop_duplicates("t")
    if len(frame) < 20 or lap_time <= 0:
        raise ValueError("The selected lap has insufficient telemetry for a comparison video.")
    warnings = []
    # Allow normal sample-boundary spacing, but reject materially incomplete laps.
    if frame["t"].min() > 1 or frame["t"].max() < lap_time - 1:
        raise ValueError("Telemetry does not cover the complete selected lap. Choose another lap.")
    running = frame[(frame["t"] >= 0) & (frame["t"] <= lap_time)]
    if running["t"].diff().max() > 2:
        raise ValueError("The lap contains a telemetry gap longer than two seconds. Choose another lap.")
    if frame["t"].min() > 0 or frame["t"].max() < lap_time:
        warnings.append("Boundary samples are held for less than one second at the lap edges.")
    t = np.unique(np.r_[0.0, running["t"].to_numpy(), lap_time])
    result = pd.DataFrame({"t": t})
    for source, target, default in (("Speed", "speed", 0), ("Throttle", "throttle", 0),
                                    ("RPM", "rpm", 0), ("X", "x", 0), ("Y", "y", 0), ("Z", "z", 0)):
        if source not in frame or frame[source].isna().all():
            if source not in {"Z"}:
                warnings.append(f"{source} is unavailable; its display is omitted.")
            values = np.full(len(frame), default, dtype=float)
        else:
            values = pd.to_numeric(frame[source], errors="coerce").interpolate().ffill().bfill().fillna(default).to_numpy()
        result[target] = np.interp(t, frame["t"], values)
    result[["x", "y", "z"]] /= 10.0
    result["throttle"] = result["throttle"].clip(0, 100)
    if "Throttle" in frame and (pd.to_numeric(frame["Throttle"], errors="coerce") > 100).any():
        warnings.append("Out-of-range throttle samples were clamped for display.")
    indices = np.clip(np.searchsorted(frame["t"].to_numpy(), t, side="right") - 1, 0, len(frame) - 1)
    for source, target in (("nGear", "gear"), ("Brake", "brake"), ("DRS", "drs")):
        if source not in frame or frame[source].isna().all():
            warnings.append(f"{source} is unavailable; its display is omitted.")
        values = pd.to_numeric(frame.get(source, pd.Series(0, index=frame.index)), errors="coerce").fillna(0).to_numpy()
        result[target] = values[indices]
    result["gear"] = result["gear"].round().astype(int)
    result["brake"] = result["brake"].astype(bool)
    result["drs"] = result["drs"].astype(int).isin(DRS_ACTIVE)
    # Integrated speed is more stable than accumulated noisy GPS distances.
    speed = result["speed"].to_numpy() / 3.6
    distance = np.r_[0, np.cumsum((speed[:-1] + speed[1:]) * 0.5 * np.diff(t))]
    if distance[-1] <= 100:
        raise ValueError("The selected lap has no usable distance trace.")
    result["progress"] = distance / distance[-1]
    return result, warnings


def _select_lap(session, code: str, number: int | None, part: str):
    laps = filtered_laps(session, code, part)
    if number is not None:
        selected = laps[laps["LapNumber"] == number]
    else:
        # Fastest means a valid timed lap, never a deleted qualifying lap.
        if "Deleted" in laps:
            laps = laps[~laps["Deleted"].eq(True)]
        selected = laps.nsmallest(1, "LapTime")
    if selected.empty:
        raise ValueError(f"No suitable lap was found for {code} in this selection.")
    return selected.iloc[0]


def build_comparison(selection: VideoSelection) -> Comparison:
    if selection.driver_a == selection.driver_b:
        raise ValueError("Choose two different drivers.")
    try:
        return _build_fastf1_comparison(selection)
    except Exception as primary:
        from services.openf1_comparison import comparison
        try:
            return comparison(selection)
        except Exception as secondary:
            raise ValueError(f'FastF1 comparison unavailable: {primary} OpenF1 fallback unavailable: {secondary}') from secondary


def _build_fastf1_comparison(selection: VideoSelection) -> Comparison:
    if selection.driver_a == selection.driver_b:
        raise ValueError("Choose two different drivers.")
    session = load_video_session(selection.year, selection.event, selection.session)
    prepared = []
    for code, number in ((selection.driver_a, selection.lap_a), (selection.driver_b, selection.lap_b)):
        lap = _select_lap(session, code, number, selection.qualifying_part)
        data, warnings = prepare_lap_samples(lap.get_telemetry(), lap["LapStartTime"].total_seconds(), lap["LapTime"].total_seconds())
        if pd.notna(lap.get("PitInTime")) or pd.notna(lap.get("PitOutTime")):
            warnings.append("This lap includes a pit entry or exit.")
        if pd.notna(lap.get("Deleted")) and bool(lap.get("Deleted")):
            warnings.append("This selected lap was deleted by race control.")
        if pd.notna(lap.get("IsAccurate")) and not bool(lap.get("IsAccurate")):
            warnings.append("FastF1 flags this lap's timing as potentially inaccurate.")
        if str(lap.get("TrackStatus", "1")) != "1":
            warnings.append("This lap includes a non-green track status.")
        driver = session.get_driver(code)
        try:
            color = fastf1.plotting.get_driver_color(code, session)
        except Exception:
            color = "#6ce5d2" if not prepared else "#ff665d"
        prepared.append(ComparisonLap(code, str(driver.get("FullName") or code), str(driver.get("TeamName") or ""),
                                      color, int(lap["LapNumber"]), float(lap["LapTime"].total_seconds()), data, warnings))
    # One common reference path. The cars are lap ghosts, not inferred overtakes.
    reference = min(prepared, key=lambda lap: lap.lap_time).samples
    grid = np.linspace(0, 1, 720)
    unique = reference.drop_duplicates("progress")
    track = np.column_stack([grid] + [np.interp(grid, unique["progress"], unique[key]) for key in ("x", "y", "z")])
    warnings = [f"{lap.code}: {message}" for lap in prepared for message in lap.warnings]
    return Comparison(selection.year, str(session.event.get("EventName", selection.event)), str(session.name),
                      tuple(prepared), track, warnings)
