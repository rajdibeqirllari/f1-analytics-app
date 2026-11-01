import streamlit as st
import pandas as pd
import numpy as np
import fastf1
import requests
from pathlib import Path
from datetime import timedelta

# ------------------------------------------------------------
# Paths / Cache
# ------------------------------------------------------------

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

CACHE_DIR = BASE_DIR / "fastf1_cache"
CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

OPENF1_BASE = "https://api.openf1.org/v1"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _find_col(df: pd.DataFrame, *names):
    lower = {c.lower(): c for c in df.columns}
    for name in names:
        name = name.lower()
        for lc, real in lower.items():
            if lc == name or name in lc:
                return real
    return None


def _time_to_seconds(series: pd.Series) -> np.ndarray:
    try:
        return pd.to_timedelta(series.astype(str)).dt.total_seconds().astype(float).to_numpy()
    except Exception:
        pass

    try:
        return pd.to_numeric(series, errors="coerce").astype(float).to_numpy()
    except Exception:
        pass

    dt = pd.to_datetime(series, errors="coerce", utc=True)
    return (dt - dt.iloc[0]).dt.total_seconds().astype(float).to_numpy()


def _normalize_brake(v):
    if pd.isna(v):
        return False

    s = str(v).strip().lower()
    if s in ["true", "yes", "on", "1"]:
        return True
    if s in ["false", "no", "off", "0"]:
        return False

    try:
        x = float(v)
    except Exception:
        return False

    return x > 0


def _normalize_drs(v):
    if pd.isna(v):
        return False

    s = str(v).strip().lower()
    if s in ["true", "yes", "on"]:
        return True
    if s in ["false", "no", "off"]:
        return False

    try:
        x = int(float(v))
    except Exception:
        return False

    return x in [10, 12, 14]


def _safe_bool_from_number(v):
    try:
        return float(v) > 0
    except Exception:
        return False


def _safe_drs_bool(v):
    try:
        return int(float(v)) in [10, 12, 14]
    except Exception:
        return False


def parse_lap_time(text: str) -> float | None:
    txt = str(text).strip()
    if not txt:
        return None

    if ":" in txt:
        m, s = txt.split(":", 1)
        return int(m) * 60 + float(s)

    return float(txt)


def normalize_to_tel_df(df: pd.DataFrame) -> pd.DataFrame:
    time_col = _find_col(df, "time", "sessiontime", "t")
    speed_col = _find_col(df, "speed", "speed_kmh")
    rpm_col = _find_col(df, "rpm")
    gear_col = _find_col(df, "ngear", "n_gear", "gear")
    throttle_col = _find_col(df, "throttle")
    brake_col = _find_col(df, "brake")
    drs_col = _find_col(df, "drs")
    x_col = _find_col(df, "x")
    y_col = _find_col(df, "y")
    z_col = _find_col(df, "z")

    if time_col is None:
        raise ValueError("CSV needs Time / SessionTime / t column.")
    if speed_col is None:
        raise ValueError("CSV needs Speed / speed_kmh column.")
    if rpm_col is None:
        raise ValueError("CSV needs RPM column.")
    if gear_col is None:
        raise ValueError("CSV needs nGear / n_gear / gear column.")
    if throttle_col is None:
        raise ValueError("CSV needs Throttle column.")

    t = _time_to_seconds(df[time_col])

    tel = pd.DataFrame({
        "t": t,
        "speed_kmh": pd.to_numeric(df[speed_col], errors="coerce").fillna(0).astype(float),
        "rpm": pd.to_numeric(df[rpm_col], errors="coerce").fillna(0).astype(float),
        "gear": pd.to_numeric(df[gear_col], errors="coerce").fillna(1).astype(int).clip(1, 8),
        "throttle": pd.to_numeric(df[throttle_col], errors="coerce").fillna(0).astype(float).clip(0, 100),
        "brake": df[brake_col].apply(_normalize_brake) if brake_col else False,
        "drs": df[drs_col].apply(_normalize_drs) if drs_col else False,
        "x": pd.to_numeric(df[x_col], errors="coerce").fillna(0).astype(float) if x_col else 0.0,
        "y": pd.to_numeric(df[y_col], errors="coerce").fillna(0).astype(float) if y_col else 0.0,
        "z": pd.to_numeric(df[z_col], errors="coerce").fillna(0).astype(float) if z_col else 0.0,
    })

    tel = tel.dropna(subset=["t"]).sort_values("t").reset_index(drop=True)

    if len(tel) == 0:
        raise ValueError("CSV was read, but no valid telemetry rows were found.")

    tel["t"] = tel["t"] - float(tel["t"].iloc[0])
    return tel


def make_after_effects_tsv_from_tel(tel_df: pd.DataFrame, fps: int = 30, duration_override: float | None = None) -> pd.DataFrame:
    df = tel_df.copy()
    df = df.sort_values("t").reset_index(drop=True)

    max_time = float(duration_override) if duration_override is not None else float(df["t"].max())
    max_frame = int(np.floor(max_time * fps))

    target = pd.DataFrame({"frame": np.arange(0, max_frame + 1, dtype=int)})
    target["time_sec"] = target["frame"] / fps

    cont_cols = ["speed_kmh", "rpm", "throttle", "x", "y", "z"]

    src_cont = (
        df[["t"] + cont_cols]
        .drop_duplicates(subset="t", keep="last")
        .set_index("t")
        .sort_index()
    )

    interp = src_cont.reindex(src_cont.index.union(target["time_sec"]))
    interp = interp.sort_index().interpolate(method="index").ffill().bfill()
    interp = interp.reindex(target["time_sec"]).reset_index(drop=True)

    src_disc = df[["t", "gear", "brake", "drs"]].copy().sort_values("t")

    nearest = pd.merge_asof(
        target[["time_sec"]].sort_values("time_sec"),
        src_disc,
        left_on="time_sec",
        right_on="t",
        direction="nearest"
    ).ffill().bfill()

    out = pd.DataFrame({
        "frame": target["frame"],
        "Speed": interp["speed_kmh"].round(3),
        "RPM": interp["rpm"].round(3),
        "nGear": nearest["gear"].round().astype(int),
        "Throttle": interp["throttle"].round(3).clip(0, 100),
        "Brake": nearest["brake"].astype(bool),
        "DRS": nearest["drs"].astype(bool),
        "X": interp["x"].round(6),
        "Y": interp["y"].round(6),
        "Z": interp["z"].round(6),
    })

    return out


def make_racerender_csv_from_tel(tel_df: pd.DataFrame) -> pd.DataFrame:
    df = tel_df.copy()

    out = pd.DataFrame({
        "Time": pd.to_timedelta(df["t"], unit="s").astype(str),
        "RPM": df["rpm"],
        "Speed": df["speed_kmh"],
        "nGear": df["gear"],
        "Throttle": df["throttle"],
        "Brake": df["brake"],
        "Distance": 0.0,
        "X": df["x"],
        "Y": df["y"],
        "Z": df["z"],
    })

    return out


# ------------------------------------------------------------
# FastF1
# ------------------------------------------------------------

def load_fastf1_tel(year, event_name, session_name, driver, lap_mode, lap_number):
    session = fastf1.get_session(int(year), event_name, session_name)
    session.load(laps=True, telemetry=True, weather=False, messages=False)

    laps = session.laps.pick_drivers(driver.upper())

    if len(laps) == 0:
        raise RuntimeError("FastF1 loaded the session, but no laps were found for this driver.")

    if lap_mode == "Fastest":
        lap = laps.pick_fastest()
    else:
        lap_df = laps[laps["LapNumber"] == int(lap_number)]
        if len(lap_df) == 0:
            raise RuntimeError("FastF1 did not find that lap number.")
        lap = lap_df.iloc[0]

    car = lap.get_car_data()
    car["t"] = car["Time"].dt.total_seconds().astype(float)

    pos = lap.get_pos_data()
    pos["t"] = pos["Time"].dt.total_seconds().astype(float)

    car_cols = ["t"]
    for c in ["Speed", "Throttle", "Brake", "nGear", "RPM", "DRS"]:
        if c in car.columns:
            car_cols.append(c)

    pos_cols = ["t"]
    for c in ["X", "Y", "Z"]:
        if c in pos.columns:
            pos_cols.append(c)

    car = car[car_cols].sort_values("t")
    pos = pos[pos_cols].sort_values("t")

    tel = pd.merge_asof(
        car,
        pos,
        on="t",
        direction="nearest",
        tolerance=0.5
    )

    result = pd.DataFrame({
        "t": tel["t"].astype(float),
        "speed_kmh": tel["Speed"].fillna(0).astype(float) if "Speed" in tel else 0.0,
        "rpm": tel["RPM"].fillna(0).astype(float) if "RPM" in tel else 0.0,
        "gear": tel["nGear"].fillna(1).astype(int).clip(1, 8) if "nGear" in tel else 1,
        "throttle": tel["Throttle"].fillna(0).astype(float).clip(0, 100) if "Throttle" in tel else 0.0,
        "brake": tel["Brake"].apply(_normalize_brake) if "Brake" in tel else False,
        "drs": tel["DRS"].apply(_normalize_drs) if "DRS" in tel else False,
        "x": tel["X"].fillna(0).astype(float) if "X" in tel else 0.0,
        "y": tel["Y"].fillna(0).astype(float) if "Y" in tel else 0.0,
        "z": tel["Z"].fillna(0).astype(float) if "Z" in tel else 0.0,
    })

    if len(result) == 0:
        raise RuntimeError("FastF1 returned no telemetry rows.")

    result["t"] = result["t"] - float(result["t"].iloc[0])
    return result


# ------------------------------------------------------------
# OpenF1
# ------------------------------------------------------------

def openf1_get(endpoint: str, params: dict):
    url = f"{OPENF1_BASE}/{endpoint}"

    try:
        r = requests.get(url, params=params, timeout=60)
    except Exception as e:
        raise RuntimeError(f"OpenF1 connection failed: {e}")

    if r.status_code == 404:
        raise RuntimeError(
            "OpenF1 has no data for this request.\n\n"
            f"Endpoint: {endpoint}\n"
            f"Params: {params}\n"
            f"Final URL: {r.url}\n\n"
            "This is not an API key problem. It means OpenF1 does not have this exact data."
        )

    try:
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            f"OpenF1 request failed.\n\n"
            f"URL: {r.url}\n"
            f"Status: {r.status_code}\n"
            f"Error: {e}"
        )

    return r.json()


def session_code_to_openf1_name(code: str) -> str:
    mapping = {
        "FP1": "Practice 1",
        "FP2": "Practice 2",
        "FP3": "Practice 3",
        "Q": "Qualifying",
        "R": "Race",
        "SQ": "Sprint Qualifying",
        "SS": "Sprint Shootout",
        "S": "Sprint",
    }
    return mapping.get(code, code)


def find_openf1_session(year: int, event_search: str, session_code: str):
    wanted_session = session_code_to_openf1_name(session_code)
    sessions = openf1_get("sessions", {"year": int(year)})

    q = str(event_search).strip().lower()
    matches = []

    for s in sessions:
        session_name = str(s.get("session_name", "")).strip().lower()
        searchable = " ".join([
            str(s.get("country_name", "")),
            str(s.get("location", "")),
            str(s.get("circuit_short_name", "")),
            str(s.get("meeting_name", "")),
            str(s.get("meeting_official_name", "")),
        ]).lower()

        if session_name == wanted_session.lower() and q in searchable:
            matches.append(s)

    if not matches:
        examples = sorted(set(
            f"{x.get('country_name', '')} | {x.get('location', '')} | {x.get('session_name', '')}"
            for x in sessions
        ))

        raise RuntimeError(
            "OpenF1 could not find that event/session.\n\n"
            "Try search words like Bahrain, Australia, Canada, Monza, Singapore.\n\n"
            "Examples:\n" + "\n".join(examples[:25])
        )

    matches = sorted(matches, key=lambda x: str(x.get("date_start", "")), reverse=True)
    return matches[0]


def get_openf1_drivers_df(session_key: int) -> pd.DataFrame:
    drivers = openf1_get("drivers", {"session_key": int(session_key)})
    if not drivers:
        raise RuntimeError("OpenF1 returned no drivers for this session.")
    return pd.DataFrame(drivers)


def get_openf1_driver_number(session_key: int, driver_code: str) -> int:
    drivers = get_openf1_drivers_df(session_key)
    code = driver_code.strip().upper()

    if code.isdigit():
        return int(code)

    for _, d in drivers.iterrows():
        acronym = str(d.get("name_acronym", "")).upper()
        number = d.get("driver_number")

        if acronym == code:
            return int(number)

    available = [
        f"{str(d.get('name_acronym', '')).upper()} ({d.get('driver_number', '')})"
        for _, d in drivers.iterrows()
    ]

    raise RuntimeError(
        f"OpenF1 could not find driver {driver_code}.\n\n"
        "Available drivers:\n" + ", ".join(available)
    )


def openf1_car_data_to_csv_df(car_data: list[dict], session_key: int, driver_number: int) -> pd.DataFrame:
    if not car_data:
        raise RuntimeError("OpenF1 returned no car_data rows.")

    car = pd.DataFrame(car_data)

    required = ["date", "speed", "rpm", "n_gear", "throttle", "brake", "drs"]
    missing = [c for c in required if c not in car.columns]
    if missing:
        raise RuntimeError(f"OpenF1 car_data is missing columns: {missing}")

    car["date_dt"] = pd.to_datetime(car["date"], utc=True, errors="coerce")
    car = car.dropna(subset=["date_dt"]).sort_values("date_dt").reset_index(drop=True)

    if len(car) == 0:
        raise RuntimeError("OpenF1 car_data existed, but no valid date rows were found.")

    car["t"] = (car["date_dt"] - car["date_dt"].iloc[0]).dt.total_seconds()

    tel = pd.DataFrame({
        "t": car["t"].astype(float),
        "Time": pd.to_timedelta(car["t"], unit="s").astype(str),
        "Speed": pd.to_numeric(car["speed"], errors="coerce").fillna(0).astype(float),
        "RPM": pd.to_numeric(car["rpm"], errors="coerce").fillna(0).astype(float),
        "nGear": pd.to_numeric(car["n_gear"], errors="coerce").fillna(1).astype(int).clip(1, 8),
        "Throttle": pd.to_numeric(car["throttle"], errors="coerce").fillna(0).astype(float).clip(0, 100),
        "Brake": car["brake"].apply(_safe_bool_from_number),
        "DRS": car["drs"].apply(_safe_drs_bool),
        "X": 0.0,
        "Y": 0.0,
        "Z": 0.0,
        "date": car["date"],
        "session_key": session_key,
        "driver_number": driver_number,
    })

    return tel


def openf1_full_csv_to_tel_df(full_df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "t": full_df["t"].astype(float),
        "speed_kmh": pd.to_numeric(full_df["Speed"], errors="coerce").fillna(0).astype(float),
        "rpm": pd.to_numeric(full_df["RPM"], errors="coerce").fillna(0).astype(float),
        "gear": pd.to_numeric(full_df["nGear"], errors="coerce").fillna(1).astype(int).clip(1, 8),
        "throttle": pd.to_numeric(full_df["Throttle"], errors="coerce").fillna(0).astype(float).clip(0, 100),
        "brake": full_df["Brake"].apply(_normalize_brake),
        "drs": full_df["DRS"].apply(_normalize_drs),
        "x": pd.to_numeric(full_df["X"], errors="coerce").fillna(0).astype(float),
        "y": pd.to_numeric(full_df["Y"], errors="coerce").fillna(0).astype(float),
        "z": pd.to_numeric(full_df["Z"], errors="coerce").fillna(0).astype(float),
    })


def load_openf1_full_session_csv(year, event_search, session_code, driver_code):
    session = find_openf1_session(year, event_search, session_code)
    session_key = int(session["session_key"])
    driver_number = get_openf1_driver_number(session_key, driver_code)

    # IMPORTANT:
    # Full-session export does NOT use date filters and does NOT require the laps endpoint.
    # This avoids the old failures caused by date>= / date<= filters.
    params = {
        "session_key": session_key,
        "driver_number": driver_number,
    }

    car_data = openf1_get("car_data", params)
    tel = openf1_car_data_to_csv_df(car_data, session_key, driver_number)

    return tel, session


def load_openf1_lap_csv(year, event_search, session_code, driver_code, lap_mode, lap_number):
    session = find_openf1_session(year, event_search, session_code)
    session_key = int(session["session_key"])
    driver_number = get_openf1_driver_number(session_key, driver_code)

    laps = openf1_get("laps", {
        "session_key": session_key,
        "driver_number": driver_number,
    })

    if not laps:
        raise RuntimeError("OpenF1 returned no laps for this driver/session.")

    laps_df = pd.DataFrame(laps).dropna(subset=["lap_duration", "date_start"]).copy()
    if len(laps_df) == 0:
        raise RuntimeError("OpenF1 laps exist, but none have lap_duration/date_start.")

    if lap_mode == "Fastest":
        if "is_pit_out_lap" in laps_df.columns:
            laps_df = laps_df[laps_df["is_pit_out_lap"] != True].copy()
        lap_row = laps_df.sort_values("lap_duration").iloc[0]
    else:
        lap_df = laps_df[laps_df["lap_number"] == int(lap_number)]
        if len(lap_df) == 0:
            raise RuntimeError("OpenF1 did not find that lap number.")
        lap_row = lap_df.iloc[0]

    # Download full session car_data, then crop locally.
    # We do not send date filters to OpenF1 anymore.
    full_csv, _ = load_openf1_full_session_csv(year, event_search, session_code, driver_code)
    full_csv = full_csv.copy()
    full_csv["date_dt"] = pd.to_datetime(full_csv["date"], utc=True, errors="coerce")

    start = pd.to_datetime(lap_row["date_start"], utc=True)
    lap_seconds = float(lap_row["lap_duration"])
    end = start + timedelta(seconds=lap_seconds)

    cropped = full_csv[(full_csv["date_dt"] >= start) & (full_csv["date_dt"] <= end)].copy()

    if len(cropped) == 0:
        raise RuntimeError(
            "OpenF1 had lap data and full-session car_data, but no car_data rows matched this lap time.\n\n"
            "Use OpenF1 Full Session CSV instead, then crop manually."
        )

    cropped = cropped.drop(columns=["date_dt"])
    cropped["t"] = cropped["t"] - float(cropped["t"].iloc[0])
    cropped["Time"] = pd.to_timedelta(cropped["t"], unit="s").astype(str)

    tel_df = openf1_full_csv_to_tel_df(cropped)
    tel_df["t"] = tel_df["t"] - float(tel_df["t"].iloc[0])

    return tel_df, lap_seconds, session, lap_row, cropped


# ------------------------------------------------------------
# UI
# ------------------------------------------------------------

st.set_page_config(page_title="F1 Telemetry Fallback", layout="wide")
st.title("F1 Telemetry Fallback Generator")

st.caption("No hud_renderer. This app creates telemetry CSV / AE TSV from OpenF1, FastF1, or an uploaded CSV.")

c1, c2 = st.columns(2)

with c1:
    data_source = st.selectbox(
        "Data source",
        ["OpenF1 Full Session CSV", "OpenF1 Lap CSV", "FastF1", "Upload CSV"],
        index=0
    )

with c2:
    fps = st.selectbox("Export FPS for AE TSV", [25, 30, 50], index=1)


tel_df = None
lap_seconds = None
output_label = "telemetry"


if data_source == "OpenF1 Full Session CSV":
    st.subheader("OpenF1 Full Session CSV")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        year = st.number_input("Year", min_value=2023, max_value=2035, value=2025, step=1)
    with c2:
        event_search = st.text_input("Event search", value="Bahrain")
    with c3:
        session_code = st.selectbox("Session", ["FP1", "FP2", "FP3", "Q", "R", "SQ", "S"], index=4)
    with c4:
        driver = st.text_input("Driver code or number", value="VER")

    c_check, c_generate = st.columns([1, 1])

    with c_check:
        if st.button("Check session/drivers"):
            try:
                session_info = find_openf1_session(year, event_search, session_code)
                session_key = int(session_info["session_key"])
                drivers_df = get_openf1_drivers_df(session_key)

                st.success(f"Session found. session_key={session_key}")
                st.write("Session:", session_info)
                show_cols = [c for c in ["driver_number", "name_acronym", "full_name", "team_name"] if c in drivers_df.columns]
                st.dataframe(drivers_df[show_cols] if show_cols else drivers_df, use_container_width=True)

            except Exception as e:
                st.error(str(e))

    with c_generate:
        if st.button("Generate CSV from OpenF1", type="primary"):
            try:
                with st.spinner("Downloading OpenF1 car_data and creating CSV..."):
                    full_session_df, session_info = load_openf1_full_session_csv(
                        year,
                        event_search,
                        session_code,
                        driver,
                    )

                st.success(f"CSV generated. Rows: {len(full_session_df)}")
                st.write("Session:", session_info)
                st.dataframe(full_session_df.head(30), use_container_width=True)

                safe_label = f"openf1_{year}_{event_search}_{session_code}_{driver}"
                safe_label = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in safe_label)

                st.download_button(
                    "Download OpenF1 full session CSV",
                    data=full_session_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_label}_full_session.csv",
                    mime="text/csv",
                )

                tel_df = openf1_full_csv_to_tel_df(full_session_df)
                lap_seconds = float(tel_df["t"].iloc[-1])
                output_label = safe_label

            except Exception as e:
                st.error(str(e))


elif data_source == "OpenF1 Lap CSV":
    st.subheader("OpenF1 Lap CSV")

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        year = st.number_input("Year", min_value=2023, max_value=2035, value=2025, step=1)
    with c2:
        event_search = st.text_input("Event search", value="Bahrain")
    with c3:
        session_code = st.selectbox("Session", ["FP1", "FP2", "FP3", "Q", "R", "SQ", "S"], index=4)
    with c4:
        driver = st.text_input("Driver code or number", value="VER")
    with c5:
        lap_mode = st.selectbox("Lap", ["Fastest", "Lap number"], index=0)

    lap_number = None
    if lap_mode == "Lap number":
        lap_number = st.number_input("Lap #", min_value=1, max_value=300, value=1, step=1)

    if st.button("Generate lap CSV from OpenF1", type="primary"):
        try:
            with st.spinner("Loading OpenF1 lap and full-session car_data..."):
                tel_df, lap_seconds, session_info, lap_row, cropped_csv = load_openf1_lap_csv(
                    year,
                    event_search,
                    session_code,
                    driver,
                    lap_mode,
                    lap_number,
                )

            output_label = f"openf1_lap_{year}_{event_search}_{session_code}_{driver}"
            safe_label = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in output_label)

            st.success(f"OpenF1 lap CSV generated. Duration: {lap_seconds:.3f}s. Rows: {len(cropped_csv)}")
            st.write("Session:", session_info)
            st.write("Lap:", lap_row.to_dict())
            st.dataframe(cropped_csv.head(30), use_container_width=True)

            st.download_button(
                "Download OpenF1 lap CSV",
                data=cropped_csv.to_csv(index=False).encode("utf-8"),
                file_name=f"{safe_label}.csv",
                mime="text/csv",
            )

        except Exception as e:
            st.error(str(e))


elif data_source == "FastF1":
    st.subheader("FastF1")

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        year = st.number_input("Year", min_value=2018, max_value=2035, value=2024, step=1)
    with c2:
        event_name = st.text_input("Event", value="Monza")
    with c3:
        session_code = st.selectbox("Session", ["FP1", "FP2", "FP3", "Q", "R", "SQ", "SS"], index=3)
    with c4:
        driver = st.text_input("Driver code", value="LEC")
    with c5:
        lap_mode = st.selectbox("Lap", ["Fastest", "Lap number"], index=0)

    lap_number = None
    if lap_mode == "Lap number":
        lap_number = st.number_input("Lap #", min_value=1, max_value=300, value=1, step=1)

    if st.button("Load FastF1 data", type="primary"):
        try:
            with st.spinner("Loading FastF1..."):
                tel_df = load_fastf1_tel(
                    year,
                    event_name,
                    session_code,
                    driver,
                    lap_mode,
                    lap_number,
                )
                lap_seconds = float(tel_df["t"].iloc[-1])
                output_label = f"fastf1_{year}_{event_name}_{session_code}_{driver}"

            st.success(f"FastF1 loaded. Lap duration: {lap_seconds:.3f}s")

        except Exception as e:
            st.error(
                "FastF1 failed. Use OpenF1 or Upload CSV.\n\n"
                + str(e)
            )


elif data_source == "Upload CSV":
    st.subheader("Upload CSV")

    uploaded = st.file_uploader("Upload telemetry CSV", type=["csv"])

    manual_lap_time = st.text_input(
        "Optional lap time override",
        value="",
        help="Example: 93.669 or 1:33.669"
    )

    if uploaded is not None:
        raw_df = pd.read_csv(uploaded)
        st.write("Detected columns:", list(raw_df.columns))

        try:
            tel_df = normalize_to_tel_df(raw_df)
            lap_seconds = float(tel_df["t"].iloc[-1])

            override = parse_lap_time(manual_lap_time) if manual_lap_time.strip() else None
            if override is not None:
                lap_seconds = override

            output_label = "uploaded_csv"
            st.success(f"CSV loaded. Duration: {lap_seconds:.3f}s")

        except Exception as e:
            st.error(str(e))


# ------------------------------------------------------------
# Output downloads
# ------------------------------------------------------------

if tel_df is not None:
    st.subheader("Telemetry Preview")
    st.write(f"Rows: {len(tel_df)}")
    st.write(f"Duration: {lap_seconds:.3f}s")
    st.dataframe(tel_df.head(30), use_container_width=True)

    safe_label = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in output_label)

    normalized_csv = tel_df.to_csv(index=False).encode("utf-8")
    ae_df = make_after_effects_tsv_from_tel(tel_df, fps=int(fps), duration_override=lap_seconds)
    rr_df = make_racerender_csv_from_tel(tel_df)

    st.download_button(
        "Download normalized telemetry CSV",
        data=normalized_csv,
        file_name=f"{safe_label}_normalized.csv",
        mime="text/csv",
    )

    st.download_button(
        "Download After Effects TSV",
        data=ae_df.to_csv(sep="\t", index=False).encode("utf-8"),
        file_name=f"{safe_label}_ae_{int(fps)}fps.tsv",
        mime="text/tab-separated-values",
    )

    st.download_button(
        "Download RaceRender CSV",
        data=rr_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{safe_label}_racerender.csv",
        mime="text/csv",
    )
