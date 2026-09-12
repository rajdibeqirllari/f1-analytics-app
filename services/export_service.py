from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


CANONICAL_TELEMETRY_SCHEMA = [
    "time_sec",
    "date",
    "session_time",
    "speed_kmh",
    "rpm",
    "gear",
    "throttle_pct",
    "brake_active",
    "drs_raw",
    "drs_active",
    "distance_m",
    "relative_distance",
    "x",
    "y",
    "z",
    "source",
    "active_aero_mode",
    "overtake_mode",
    "boost_mode",
    "recharge_mode",
]

FUTURE_FIELDS = ["active_aero_mode", "overtake_mode", "boost_mode", "recharge_mode"]


def _first_column(frame: pd.DataFrame, *names: str) -> str | None:
    lookup = {str(column).lower(): column for column in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    for name in names:
        for lowered, column in lookup.items():
            if name.lower() in lowered:
                return column
    return None


def _time_seconds(series: pd.Series) -> pd.Series:
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds()
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() >= max(1, len(series) // 2):
        return numeric.astype(float)
    timedeltas = pd.to_timedelta(series, errors="coerce")
    if timedeltas.notna().any():
        return timedeltas.dt.total_seconds()
    timestamps = pd.to_datetime(series, errors="coerce", utc=True)
    return (timestamps - timestamps.iloc[0]).dt.total_seconds()


def _bool_value(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return str(value).strip().lower() in {"true", "yes", "on"}


def _drs_value(value: Any) -> bool:
    try:
        return int(float(value)) in {10, 12, 14}
    except (TypeError, ValueError):
        return _bool_value(value)


def normalize_telemetry(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    """Map FastF1 or uploaded telemetry to the stable export schema.

    The 2026 mode fields remain nullable unless the input really exposes them.
    """
    if frame is None or frame.empty:
        raise ValueError("The selected source returned no telemetry rows.")
    data = frame.copy()
    time_col = _first_column(data, "time_sec", "t", "Time", "SessionTime", "session_time")
    speed_col = _first_column(data, "speed_kmh", "Speed")
    if time_col is None or speed_col is None:
        raise ValueError("Telemetry needs a time column and a speed column.")
    time_sec = _time_seconds(data[time_col])
    if time_sec.notna().any():
        time_sec = time_sec - float(time_sec.dropna().iloc[0])

    def numeric(*names: str, default=np.nan) -> pd.Series:
        column = _first_column(data, *names)
        if column is None:
            return pd.Series([default] * len(data), index=data.index)
        return pd.to_numeric(data[column], errors="coerce")

    date_col = _first_column(data, "date", "Date")
    session_col = _first_column(data, "session_time", "SessionTime")
    brake_col = _first_column(data, "brake_active", "Brake")
    drs_raw_col = _first_column(data, "drs_raw", "DRS")
    distance = numeric("distance_m", "Distance")
    max_distance = distance.max(skipna=True)
    relative = numeric("relative_distance", "RelativeDistance")
    if relative.isna().all() and pd.notna(max_distance) and float(max_distance) > 0:
        relative = distance / float(max_distance)

    out = pd.DataFrame(
        {
            "time_sec": time_sec,
            "date": data[date_col].astype(str) if date_col else pd.NA,
            "session_time": _time_seconds(data[session_col]) if session_col else time_sec,
            "speed_kmh": numeric("speed_kmh", "Speed"),
            "rpm": numeric("rpm", "RPM"),
            "gear": numeric("gear", "nGear", "n_gear").round().astype("Int64"),
            "throttle_pct": numeric("throttle_pct", "Throttle").clip(0, 100),
            "brake_active": data[brake_col].map(_bool_value) if brake_col else False,
            "drs_raw": numeric("drs_raw", "DRS").round().astype("Int64"),
            "drs_active": data[drs_raw_col].map(_drs_value) if drs_raw_col else False,
            "distance_m": distance,
            "relative_distance": relative,
            "x": numeric("x", "X"),
            "y": numeric("y", "Y"),
            "z": numeric("z", "Z"),
            "source": source,
        }
    )
    for field in FUTURE_FIELDS:
        original = _first_column(data, field)
        out[field] = data[original] if original else pd.NA
    out = out.dropna(subset=["time_sec"]).sort_values("time_sec").reset_index(drop=True)
    if out.empty:
        raise ValueError("Telemetry was read, but no valid timestamped rows remained.")
    return out[CANONICAL_TELEMETRY_SCHEMA]


def make_after_effects_tsv(frame: pd.DataFrame, fps: int = 30) -> pd.DataFrame:
    data = frame.sort_values("time_sec").drop_duplicates("time_sec", keep="last").copy()
    duration = float(data["time_sec"].max())
    target = pd.DataFrame({"frame": np.arange(0, int(np.floor(duration * fps)) + 1)})
    target["time_sec"] = target["frame"] / int(fps)
    continuous = ["speed_kmh", "rpm", "throttle_pct", "x", "y", "z"]
    source_cont = data[["time_sec", *continuous]].set_index("time_sec")
    merged_index = source_cont.index.union(target["time_sec"])
    interpolated = (
        source_cont.reindex(merged_index)
        .sort_index()
        .interpolate(method="index")
        .ffill()
        .bfill()
        .reindex(target["time_sec"])
        .reset_index(drop=True)
    )
    discrete = pd.merge_asof(
        target[["time_sec"]],
        data[["time_sec", "gear", "brake_active", "drs_active"]].sort_values("time_sec"),
        on="time_sec",
        direction="nearest",
    ).ffill().bfill()
    return pd.DataFrame(
        {
            "frame": target["frame"],
            "Speed": interpolated["speed_kmh"].round(3),
            "RPM": interpolated["rpm"].round(3),
            "nGear": discrete["gear"].astype("Int64"),
            "Throttle": interpolated["throttle_pct"].round(3).clip(0, 100),
            "Brake": discrete["brake_active"].astype(bool),
            "DRS": discrete["drs_active"].astype(bool),
            "X": interpolated["x"].round(6),
            "Y": interpolated["y"].round(6),
            "Z": interpolated["z"].round(6),
        }
    )


def make_racerender_csv(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Time": pd.to_timedelta(frame["time_sec"], unit="s").astype(str),
            "RPM": frame["rpm"],
            "Speed": frame["speed_kmh"],
            "nGear": frame["gear"],
            "Throttle": frame["throttle_pct"],
            "Brake": frame["brake_active"],
            "Distance": frame["distance_m"],
            "X": frame["x"],
            "Y": frame["y"],
            "Z": frame["z"],
        }
    )
