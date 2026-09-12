from __future__ import annotations

"""Compact browser replay payload builder.

The telemetry extraction, frame timeline, leaderboard ordering, and safety-car
concepts are adapted from the MIT-licensed 4f4d/f1-race-replay project while
replacing its Arcade rendering layer with a JSON payload for Canvas playback.
"""

from dataclasses import dataclass
from pathlib import Path
import json
import math
import re
from typing import Any

import fastf1
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FASTF1_CACHE = ROOT / "fastf1_cache"
REPLAY_CACHE = ROOT / "replay_cache"
FASTF1_CACHE.mkdir(parents=True, exist_ok=True)
REPLAY_CACHE.mkdir(parents=True, exist_ok=True)

try:
    fastf1.Cache.enable_cache(str(FASTF1_CACHE))
except Exception:
    pass

DRS_ACTIVE_VALUES = {10, 12, 14}
TYRE_NAMES = {
    0: "UNKNOWN",
    1: "SOFT",
    2: "MEDIUM",
    3: "HARD",
    4: "INTERMEDIATE",
    5: "WET",
}


@dataclass(frozen=True)
class ReplaySelection:
    year: int
    event_name: str
    session_type: str
    sample_rate_hz: int = 5


def session_type_to_code(session_type: str) -> str:
    mapping = {
        "Race": "R",
        "Sprint": "S",
        "Qualifying": "Q",
        "Sprint Qualifying": "SQ",
        "R": "R",
        "S": "S",
        "Q": "Q",
        "SQ": "SQ",
    }
    return mapping.get(str(session_type), "R")


def cache_path(selection: ReplaySelection) -> Path:
    event = re.sub(r"[^A-Za-z0-9]+", "_", selection.event_name).strip("_")
    return REPLAY_CACHE / f"{selection.year}_{event}_{session_type_to_code(selection.session_type)}_{selection.sample_rate_hz}hz.json"


def list_replay_cache() -> list[Path]:
    return sorted(REPLAY_CACHE.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def clear_replay_cache() -> int:
    count = 0
    for path in REPLAY_CACHE.glob("*.json"):
        path.unlink(missing_ok=True)
        count += 1
    return count


def load_cached_payload(selection: ReplaySelection) -> dict[str, Any] | None:
    path = cache_path(selection)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_replay_payload(
    year: int,
    event_name: str,
    session_type: str = "Race",
    sample_rate_hz: int = 5,
    refresh: bool = False,
    progress_callback=None,
) -> dict[str, Any]:
    selection = ReplaySelection(int(year), str(event_name), session_type_to_code(session_type), int(sample_rate_hz))
    path = cache_path(selection)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    def progress(value: float, text: str) -> None:
        if progress_callback:
            progress_callback(value, text)

    progress(0.05, "Loading FastF1 session")
    session = fastf1.get_session(selection.year, selection.event_name, selection.session_type)
    session.load(laps=True, telemetry=True, weather=False, messages=True)

    progress(0.18, "Building driver metadata")
    drivers = _driver_metadata(session)

    progress(0.25, "Extracting track geometry")
    track = _build_track_geometry(session)

    progress(0.35, "Extracting driver telemetry")
    driver_data = _extract_driver_data(session, drivers)
    if not driver_data:
        raise RuntimeError("No usable telemetry was available for this replay.")

    global_min = min(d["t"][0] for d in driver_data.values() if len(d["t"]))
    global_max = max(d["t"][-1] for d in driver_data.values() if len(d["t"]))
    lap_window = _session_lap_window(session)
    if lap_window is not None:
        global_min = max(global_min, lap_window[0])
        global_max = min(global_max, lap_window[1])
    duration = max(1.0, global_max - global_min)
    requested_rate = max(1, min(10, selection.sample_rate_hz))
    desired_count = int(duration * requested_rate) + 1
    max_browser_frames = 6000
    if desired_count > max_browser_frames:
        timeline = np.linspace(global_min, global_max, max_browser_frames)
        effective_rate = round(max_browser_frames / duration, 2)
    else:
        step = 1.0 / requested_rate
        timeline = np.arange(global_min, global_max, step)
        effective_rate = requested_rate

    progress(0.58, "Sampling replay frames")
    track_statuses = _track_statuses(session, global_min, global_max)
    frames = _build_frames(timeline, global_min, driver_data, track_statuses, track)

    progress(0.88, "Finalizing replay payload")
    payload = {
        "meta": {
            "year": selection.year,
            "event": str(session.event.get("EventName", selection.event_name)),
            "round": int(session.event.get("RoundNumber", 0) or 0),
            "session": selection.session_type,
            "duration_seconds": round(float(duration), 2),
            "sample_rate_hz": effective_rate,
            "requested_sample_rate_hz": selection.sample_rate_hz,
            "cache_file": str(path),
            "attribution": "Telemetry payload adapted from 4f4d/f1-race-replay concepts (MIT); rendered in F1 HYPE Studio Canvas.",
        },
        "track": track,
        "drivers": drivers,
        "frames": frames,
        "technical": {
            "frame_count": len(frames),
            "driver_count": len(drivers),
            "track_statuses": track_statuses,
            "nullable_future_fields": ["active_aero_mode", "overtake_mode", "boost_mode", "recharge_mode"],
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    progress(1.0, "Replay ready")
    return payload


def _driver_metadata(session) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for number in session.drivers:
        try:
            drv = session.get_driver(number)
        except Exception:
            continue
        code = str(drv.get("Abbreviation") or number).upper()
        team = str(drv.get("TeamName") or drv.get("Team") or "")
        name = str(drv.get("FullName") or f"{drv.get('FirstName', '')} {drv.get('LastName', '')}").strip() or code
        try:
            color = fastf1.plotting.get_driver_color(code, session)
        except Exception:
            color = "#E10600"
        rows[code] = {
            "name": name,
            "team": team,
            "number": str(number),
            "color": color,
        }
    return rows


def _build_track_geometry(session) -> dict[str, Any]:
    lap = session.laps.pick_fastest()
    tel = lap.get_telemetry()
    if tel is None or tel.empty or not {"X", "Y"}.issubset(tel.columns):
        return {"centerline": [], "inner_boundary": [], "outer_boundary": [], "drs_zones": [], "start_finish": None}
    xy = tel[["X", "Y"]].dropna().to_numpy(dtype=float)
    xy = _downsample_points(xy, 360)
    inner, outer = _offset_boundaries(xy, 70.0)
    drs_zones = _extract_drs_zones(tel, max_segments=6)
    return {
        "centerline": _round_points(xy),
        "inner_boundary": _round_points(inner),
        "outer_boundary": _round_points(outer),
        "drs_zones": drs_zones,
        "start_finish": _round_point(xy[0]) if len(xy) else None,
    }


def _extract_driver_data(session, drivers: dict[str, Any]) -> dict[str, dict[str, np.ndarray]]:
    output: dict[str, dict[str, np.ndarray]] = {}
    for code, meta in drivers.items():
        stream_data = _extract_driver_from_streams(session, meta["number"])
        if stream_data is not None:
            output[code] = stream_data
            continue

        laps = session.laps.pick_drivers(meta["number"])
        chunks: list[pd.DataFrame] = []
        total_offset = 0.0
        for _, lap in laps.iterlaps():
            try:
                tel = lap.get_telemetry()
            except Exception:
                continue
            required = {"SessionTime", "X", "Y", "Distance", "Speed", "nGear", "DRS", "Throttle", "Brake"}
            if tel is None or tel.empty or not required.issubset(tel.columns):
                continue
            frame = tel[list(required)].copy()
            frame["t"] = frame["SessionTime"].dt.total_seconds()
            frame["race_dist"] = total_offset + pd.to_numeric(frame["Distance"], errors="coerce")
            frame["lap"] = int(lap.get("LapNumber", 0) or 0)
            frame["tyre"] = str(lap.get("Compound", "UNKNOWN") or "UNKNOWN").upper()
            frame["tyre_age"] = int(lap.get("TyreLife", 0) or 0) if pd.notna(lap.get("TyreLife", np.nan)) else None
            total_offset = float(frame["race_dist"].max()) if pd.notna(frame["race_dist"].max()) else total_offset
            chunks.append(frame)
        if not chunks:
            continue
        df = pd.concat(chunks, ignore_index=True).sort_values("t").dropna(subset=["t", "X", "Y"])
        df = df[~df["t"].duplicated(keep="first")]
        if len(df) < 2:
            continue
        output[code] = {
            "t": df["t"].to_numpy(dtype=float),
            "x": df["X"].to_numpy(dtype=float),
            "y": df["Y"].to_numpy(dtype=float),
            "dist": df["race_dist"].to_numpy(dtype=float),
            "lap": df["lap"].to_numpy(dtype=float),
            "speed": pd.to_numeric(df["Speed"], errors="coerce").fillna(0).to_numpy(dtype=float),
            "gear": pd.to_numeric(df["nGear"], errors="coerce").fillna(0).to_numpy(dtype=float),
            "drs": pd.to_numeric(df["DRS"], errors="coerce").fillna(0).to_numpy(dtype=float),
            "throttle": pd.to_numeric(df["Throttle"], errors="coerce").fillna(0).to_numpy(dtype=float),
            "brake": pd.to_numeric(df["Brake"], errors="coerce").fillna(0).to_numpy(dtype=float),
            "tyre": df["tyre"].to_numpy(),
            "tyre_age": df["tyre_age"].to_numpy(),
        }
    return output


def _extract_driver_from_streams(session, driver_number: str) -> dict[str, np.ndarray] | None:
    try:
        pos = session.pos_data.get(str(driver_number))
    except Exception:
        pos = None
    if pos is None or pos.empty or not {"Time", "X", "Y"}.issubset(pos.columns):
        return None

    pos_df = pos[["Time", "X", "Y"]].copy().dropna()
    pos_df["t"] = pos_df["Time"].dt.total_seconds()
    pos_df = pos_df.sort_values("t")
    pos_df = pos_df[~pos_df["t"].duplicated(keep="first")]
    if len(pos_df) < 3:
        return None

    t = pos_df["t"].to_numpy(dtype=float)
    x = pd.to_numeric(pos_df["X"], errors="coerce").ffill().fillna(0).to_numpy(dtype=float)
    y = pd.to_numeric(pos_df["Y"], errors="coerce").ffill().fillna(0).to_numpy(dtype=float)
    segment = np.sqrt(np.diff(x, prepend=x[0]) ** 2 + np.diff(y, prepend=y[0]) ** 2)
    dist = np.cumsum(np.nan_to_num(segment, nan=0.0))

    speed = np.zeros_like(t)
    gear = np.zeros_like(t)
    drs = np.zeros_like(t)
    throttle = np.zeros_like(t)
    brake = np.zeros_like(t)
    try:
        car = session.car_data.get(str(driver_number))
    except Exception:
        car = None
    if car is not None and not car.empty and "Time" in car.columns:
        car_df = car.copy().dropna(subset=["Time"]).sort_values("Time")
        car_t = car_df["Time"].dt.total_seconds().to_numpy(dtype=float)
        if len(car_t) > 1:
            def resample(name: str, default: float = 0.0) -> np.ndarray:
                if name not in car_df.columns:
                    return np.full_like(t, default, dtype=float)
                values = pd.to_numeric(car_df[name], errors="coerce").fillna(default).to_numpy(dtype=float)
                return np.interp(t, car_t, values)

            speed = resample("Speed")
            gear = resample("nGear")
            drs = resample("DRS")
            throttle = resample("Throttle")
            brake = resample("Brake")

    laps = session.laps.pick_drivers(str(driver_number))
    lap_arr = np.ones_like(t)
    tyre_arr = np.array(["UNKNOWN"] * len(t), dtype=object)
    tyre_age_arr = np.array([None] * len(t), dtype=object)
    if laps is not None and not laps.empty and "LapStartTime" in laps.columns:
        lap_rows = laps.sort_values("LapStartTime").reset_index(drop=True)
        starts = lap_rows["LapStartTime"].dt.total_seconds().to_numpy(dtype=float)
        for idx, row in lap_rows.iterrows():
            start = starts[idx]
            end = starts[idx + 1] if idx + 1 < len(starts) else t[-1] + 1
            mask = (t >= start) & (t < end)
            lap_arr[mask] = float(row.get("LapNumber", idx + 1) or idx + 1)
            tyre_arr[mask] = str(row.get("Compound", "UNKNOWN") or "UNKNOWN").upper()
            tyre_life = row.get("TyreLife", None)
            tyre_age_arr[mask] = int(tyre_life) if pd.notna(tyre_life) else None

    return {
        "t": t,
        "x": x,
        "y": y,
        "dist": dist,
        "lap": lap_arr,
        "speed": speed,
        "gear": gear,
        "drs": drs,
        "throttle": throttle,
        "brake": brake,
        "tyre": tyre_arr,
        "tyre_age": tyre_age_arr,
    }


def _build_frames(timeline: np.ndarray, global_min: float, driver_data: dict[str, dict[str, np.ndarray]], statuses, track) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    centerline = track.get("centerline") or []
    for idx, t_abs in enumerate(timeline):
        snapshot = []
        for code, data in driver_data.items():
            if t_abs < data["t"][0] or t_abs > data["t"][-1]:
                continue
            dist = float(np.interp(t_abs, data["t"], data["dist"]))
            snap = {
                "code": code,
                "_dist": dist,
                "x": round(float(np.interp(t_abs, data["t"], data["x"])), 1),
                "y": round(float(np.interp(t_abs, data["t"], data["y"])), 1),
                "lap": int(round(np.interp(t_abs, data["t"], data["lap"]))),
                "speed": int(round(np.interp(t_abs, data["t"], data["speed"]))),
                "gear": int(round(np.interp(t_abs, data["t"], data["gear"]))),
                "drs_raw": int(round(np.interp(t_abs, data["t"], data["drs"]))),
                "throttle": int(round(np.interp(t_abs, data["t"], data["throttle"]))),
                "brake": bool(round(np.interp(t_abs, data["t"], data["brake"]))),
                "tyre": str(_nearest_label(t_abs, data["t"], data["tyre"])),
                "tyre_age": _nearest_label(t_abs, data["t"], data["tyre_age"]),
                "status": "RUNNING",
            }
            snap["drs_active"] = snap["drs_raw"] in DRS_ACTIVE_VALUES
            snapshot.append(snap)
        if not snapshot:
            continue
        snapshot.sort(key=lambda item: (item["lap"], item["_dist"]), reverse=True)
        frame_drivers = {}
        for pos, item in enumerate(snapshot, start=1):
            item["position"] = pos
            item["gap"] = "LEADER" if pos == 1 else ""
            code = item.pop("code")
            item.pop("_dist", None)
            frame_drivers[code] = item
        rel_t = float(t_abs - global_min)
        status = _status_at(rel_t, statuses)
        frame = {
            "t": round(rel_t, 3),
            "lap": snapshot[0]["lap"],
            "drivers": frame_drivers,
            "safety_car": _safety_car_at(rel_t, status, centerline, idx),
            "track_status": status["label"],
        }
        frames.append(frame)
    return frames


def _track_statuses(session, global_min: float, global_max: float) -> list[dict[str, Any]]:
    statuses = []
    status_df = getattr(session, "track_status", None)
    if status_df is not None and not status_df.empty:
        for row in status_df.to_dict("records"):
            start = float(row["Time"].total_seconds()) - global_min
            statuses.append({"status": str(row.get("Status", "")), "start_time": start, "end_time": None, "label": _status_label(row.get("Status", ""))})
    statuses.sort(key=lambda s: s["start_time"])
    for idx in range(len(statuses) - 1):
        statuses[idx]["end_time"] = statuses[idx + 1]["start_time"]
    if statuses:
        statuses[-1]["end_time"] = max(0.0, global_max - global_min)
    return statuses or [{"status": "1", "start_time": 0.0, "end_time": max(0.0, global_max - global_min), "label": "GREEN"}]


def _session_lap_window(session) -> tuple[float, float] | None:
    laps = getattr(session, "laps", None)
    if laps is None or laps.empty or "LapStartTime" not in laps.columns:
        return None
    starts = laps["LapStartTime"].dropna().dt.total_seconds()
    if starts.empty:
        return None
    end_values = []
    if "LapTime" in laps.columns:
        for _, row in laps.dropna(subset=["LapStartTime"]).iterrows():
            start = row["LapStartTime"].total_seconds()
            lap_time = row.get("LapTime")
            if hasattr(lap_time, "total_seconds") and pd.notna(lap_time):
                end_values.append(start + lap_time.total_seconds())
    start = float(starts.min())
    end = float(max(end_values)) if end_values else float(starts.max())
    if end <= start:
        return None
    return start, end


def _status_label(status: Any) -> str:
    code = str(status)
    return {
        "1": "GREEN",
        "2": "YELLOW",
        "4": "SAFETY CAR",
        "5": "RED",
        "6": "VSC",
        "7": "VSC ENDING",
    }.get(code, f"STATUS {code}" if code else "GREEN")


def _status_at(t: float, statuses: list[dict[str, Any]]) -> dict[str, Any]:
    for status in statuses:
        end = status.get("end_time")
        if status["start_time"] <= t and (end is None or t < end):
            return status
    return {"status": "1", "label": "GREEN"}


def _safety_car_at(t: float, status: dict[str, Any], centerline: list[list[float]], frame_idx: int) -> dict[str, Any] | None:
    if str(status.get("status")) != "4" or not centerline:
        return None
    point = centerline[(frame_idx * 2) % len(centerline)]
    return {"x": point[0], "y": point[1], "phase": "on_track", "alpha": 1.0}


def _nearest_label(t: float, t_arr: np.ndarray, values: np.ndarray) -> Any:
    idx = int(np.clip(np.searchsorted(t_arr, t), 0, len(values) - 1))
    value = values[idx]
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass
    return value.item() if hasattr(value, "item") else value


def _downsample_points(points: np.ndarray, max_points: int) -> np.ndarray:
    if len(points) <= max_points:
        return points
    indexes = np.linspace(0, len(points) - 1, max_points).astype(int)
    return points[indexes]


def _offset_boundaries(points: np.ndarray, width: float) -> tuple[np.ndarray, np.ndarray]:
    if len(points) < 2:
        return points, points
    dx = np.gradient(points[:, 0])
    dy = np.gradient(points[:, 1])
    norm = np.sqrt(dx ** 2 + dy ** 2)
    norm[norm == 0] = 1.0
    nx = -dy / norm
    ny = dx / norm
    inner = np.column_stack([points[:, 0] + nx * width, points[:, 1] + ny * width])
    outer = np.column_stack([points[:, 0] - nx * width, points[:, 1] - ny * width])
    return inner, outer


def _extract_drs_zones(tel: pd.DataFrame, max_segments: int = 6) -> list[dict[str, Any]]:
    if "DRS" not in tel.columns:
        return []
    df = tel[["X", "Y", "DRS"]].dropna()
    active = df["DRS"].astype(int).isin(DRS_ACTIVE_VALUES).to_numpy()
    xy = df[["X", "Y"]].to_numpy(dtype=float)
    zones = []
    start = None
    for idx, is_active in enumerate(active):
        if is_active and start is None:
            start = idx
        if start is not None and (not is_active or idx == len(active) - 1):
            end = idx
            if end - start > 5:
                segment = _downsample_points(xy[start:end], 48)
                zones.append({"points": _round_points(segment)})
            start = None
        if len(zones) >= max_segments:
            break
    return zones


def _round_points(points: np.ndarray) -> list[list[float]]:
    return [[round(float(x), 2), round(float(y), 2)] for x, y in points]


def _round_point(point: np.ndarray) -> list[float]:
    return [round(float(point[0]), 2), round(float(point[1]), 2)]
