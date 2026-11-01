"""Existing FastF1 analysis calculations extracted from app.py.

No Streamlit initialization; rendering is serialized by the API job worker.
"""
from pathlib import Path
from datetime import date
import fastf1
import fastf1.plotting
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patheffects as path_effects
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.colors as mcolors
BASE_DIR=Path(__file__).resolve().parents[1]
ASSET_DIR=BASE_DIR/'assets'
COLOR_MODE='FastF1 Official'
CUSTOM_COLOR_A='#00D2BE'
CUSTOM_COLOR_B='#DC0000'
MONO_COLOR_A='#FFFFFF'
MONO_COLOR_B='#8B5CF6'
image_format='16:9 (YouTube)'
plt.style.use('dark_background')


THEME = {
    "background": "#0B0B0F",
    "panel": "#15151C",
    "grid": "#2A2A36",
    "text": "#E6E6F0",
    "subtext": "#9CA3AF",
    "white": "#FFFFFF",
}


HIGHLIGHT = {
    "fastest": "#A7F432",
    "delta_pos": "#60A5FA",
    "delta_neg": "#FF4D4D",
    "neutral": "#FACC15",
    "sector1": "#FFD800",
    "sector2": "#00D2FF",
    "sector3": "#FF4D4D",
}


FALLBACK_2026_RACES = [
    {"RoundNumber": 1, "EventName": "Australian Grand Prix", "RaceDate": "2026-03-08"},
    {"RoundNumber": 2, "EventName": "Chinese Grand Prix", "RaceDate": "2026-03-15"},
    {"RoundNumber": 3, "EventName": "Japanese Grand Prix", "RaceDate": "2026-03-29"},
    {"RoundNumber": 4, "EventName": "Miami Grand Prix", "RaceDate": "2026-05-03"},
    {"RoundNumber": 5, "EventName": "Canadian Grand Prix", "RaceDate": "2026-05-24"},
    {"RoundNumber": 6, "EventName": "Monaco Grand Prix", "RaceDate": "2026-06-07"},
    {"RoundNumber": 7, "EventName": "Barcelona-Catalunya Grand Prix", "RaceDate": "2026-06-14"},
    {"RoundNumber": 8, "EventName": "Austrian Grand Prix", "RaceDate": "2026-06-28"},
    {"RoundNumber": 9, "EventName": "British Grand Prix", "RaceDate": "2026-07-05"},
    {"RoundNumber": 10, "EventName": "Belgian Grand Prix", "RaceDate": "2026-07-19"},
    {"RoundNumber": 11, "EventName": "Hungarian Grand Prix", "RaceDate": "2026-07-26"},
    {"RoundNumber": 12, "EventName": "Dutch Grand Prix", "RaceDate": "2026-08-23"},
    {"RoundNumber": 13, "EventName": "Italian Grand Prix", "RaceDate": "2026-09-06"},
    {"RoundNumber": 14, "EventName": "Spanish Grand Prix", "RaceDate": "2026-09-13"},
    {"RoundNumber": 15, "EventName": "Azerbaijan Grand Prix", "RaceDate": "2026-09-27"},
    {"RoundNumber": 16, "EventName": "Singapore Grand Prix", "RaceDate": "2026-10-11"},
    {"RoundNumber": 17, "EventName": "United States Grand Prix", "RaceDate": "2026-10-25"},
    {"RoundNumber": 18, "EventName": "Mexico City Grand Prix", "RaceDate": "2026-11-01"},
    {"RoundNumber": 19, "EventName": "Sao Paulo Grand Prix", "RaceDate": "2026-11-08"},
    {"RoundNumber": 20, "EventName": "Las Vegas Grand Prix", "RaceDate": "2026-11-21"},
    {"RoundNumber": 21, "EventName": "Qatar Grand Prix", "RaceDate": "2026-11-29"},
    {"RoundNumber": 22, "EventName": "Abu Dhabi Grand Prix", "RaceDate": "2026-12-06"},
]


def get_driver_plot_color(session, driver_code: str, role: str = "a") -> str:
    if COLOR_MODE == "Custom":
        return CUSTOM_COLOR_A if role == "a" else CUSTOM_COLOR_B
    if COLOR_MODE == "Monochrome":
        return MONO_COLOR_A if role == "a" else MONO_COLOR_B
    return fastf1.plotting.get_driver_color(driver_code, session)


def get_team_plot_color(session, team_name: str) -> str:
    if COLOR_MODE == "Monochrome":
        return MONO_COLOR_B
    return fastf1.plotting.get_team_color(team_name, session=session)


def style_axes(ax, xgrid: bool = True, ygrid: bool = False):
    ax.set_facecolor(THEME["panel"])
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(THEME["grid"])
    ax.spines["bottom"].set_color(THEME["grid"])
    if xgrid:
        ax.grid(axis="x", alpha=0.18, linewidth=0.8)
    if ygrid:
        ax.grid(axis="y", alpha=0.22, linewidth=0.8)


def apply_text_effect(text_obj):
    text_obj.set_path_effects([
        path_effects.Stroke(linewidth=3, foreground="black"),
        path_effects.Normal(),
    ])


def make_racerender_csv(full_tel: pd.DataFrame) -> pd.DataFrame:
    """
    Builds a RaceRender-friendly telemetry CSV from FastF1 lap.get_telemetry()

    Output columns:
    Time, RPM, Speed, nGear, Throttle, Brake, Distance, X, Y, Z
    """
    df = full_tel.copy()

    if "Time" in df.columns:
        time_col = "Time"
    elif "SessionTime" in df.columns:
        time_col = "SessionTime"
    else:
        raise ValueError("FULL telemetry has no Time/SessionTime column.")

    wanted = ["RPM", "Speed", "nGear", "Throttle", "Brake", "Distance", "X", "Y", "Z"]
    for c in wanted:
        if c not in df.columns:
            df[c] = np.nan

    out = df[[time_col] + wanted].copy()
    out = out.rename(columns={time_col: "Time"})

    for c in ["RPM", "Speed", "nGear", "Throttle", "Brake", "Distance", "X", "Y", "Z"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out["nGear"] = out["nGear"].round().astype("Int64")
    out = out.dropna(subset=["Time"])

    if out["X"].notna().any() and out["Y"].notna().any():
        out = out.dropna(subset=["X", "Y"])

    return out


def _telemetry_time_column(df: pd.DataFrame) -> str:
    for col in ["Time", "SessionTime"]:
        if col in df.columns:
            return col
    raise ValueError(
        "Telemetry data has no Time or SessionTime column. "
        f"Available columns: {', '.join(map(str, df.columns))}"
    )


def get_figsize(format_mode):
    if format_mode == "16:9 (YouTube)":
        return (16, 9)
    if format_mode == "1:1 (Instagram)":
        return (10, 10)
    if format_mode == "9:16 (TikTok)":
        return (9, 16)


def make_after_effects_tsv(full_tel: pd.DataFrame, fps: int = 30) -> pd.DataFrame:
    df = full_tel.copy()

    time_col = _telemetry_time_column(df)
    required = ["Speed", "RPM", "nGear", "Throttle", "Brake", "X", "Y", "Z"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column for AE TSV: {col}")

    df["time_sec"] = pd.to_timedelta(df[time_col].astype(str)).dt.total_seconds()
    if df["time_sec"].notna().any():
        df["time_sec"] = df["time_sec"] - float(df["time_sec"].dropna().iloc[0])
    df = df.dropna(subset=["time_sec"]).sort_values("time_sec").reset_index(drop=True)

    numeric_cols = ["Speed", "RPM", "nGear", "Throttle", "X", "Y", "Z"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    def to_bool(v):
        if pd.isna(v):
            return np.nan
        s = str(v).strip().lower()
        if s in ["true", "1", "yes"]:
            return True
        if s in ["false", "0", "no"]:
            return False
        return np.nan

    df["Brake"] = df["Brake"].apply(to_bool)
    df = df.dropna(subset=["Speed", "RPM", "nGear", "Throttle", "X", "Y", "Z"]).copy()
    df["Brake"] = df["Brake"].ffill().bfill()

    max_time = df["time_sec"].max()
    max_frame = int(np.floor(max_time * fps))

    target = pd.DataFrame({"frame": np.arange(0, max_frame + 1, dtype=int)})
    target["time_sec"] = target["frame"] / fps

    cont_cols = ["Speed", "RPM", "Throttle", "X", "Y", "Z"]

    src_cont = (
        df[["time_sec"] + cont_cols]
        .drop_duplicates(subset="time_sec", keep="last")
        .set_index("time_sec")
        .sort_index()
    )

    interp = src_cont.reindex(src_cont.index.union(target["time_sec"]))
    interp = interp.sort_index().interpolate(method="index")
    interp = interp.reindex(target["time_sec"]).reset_index(drop=True)

    src_disc = df[["time_sec", "nGear", "Brake"]].copy().sort_values("time_sec")

    nearest = pd.merge_asof(
        target[["time_sec"]].sort_values("time_sec"),
        src_disc,
        on="time_sec",
        direction="nearest"
    )

    out = pd.DataFrame({
        "frame": target["frame"],
        "Speed": interp["Speed"].round(3),
        "RPM": interp["RPM"].round(3),
        "nGear": nearest["nGear"].round().astype(int),
        "Throttle": interp["Throttle"].round(3),
        "Brake": nearest["Brake"].astype(bool),
        "X": interp["X"].round(6),
        "Y": interp["Y"].round(6),
        "Z": interp["Z"].round(6),
    })

    out["Throttle"] = out["Throttle"].clip(lower=0, upper=100)

    return out


def get_session_from_inputs(
    mode: str,
    year: int,
    event_name: str | None,
    session_name: str | None,
    test_number: int | None,
    day_number: int | None,
    require_telemetry: bool = False,
):
    if mode == "Race Weekend":
        session = fastf1.get_session(int(year), event_name, session_name)
    else:
        session = fastf1.get_testing_session(int(year), int(test_number), int(day_number))

    errors = []

    # First try what we actually need
    load_attempts = [
        dict(laps=True, telemetry=require_telemetry, weather=False, messages=False),
        dict(laps=True, telemetry=False, weather=False, messages=False),
        dict(),  # last fallback
    ]

    for kwargs in load_attempts:
        try:
            session.load(**kwargs)

            try:
                laps = session.laps
                if laps is not None and len(laps) > 0:
                    return session
                errors.append(f"Loaded with {kwargs}, but laps were empty.")
            except Exception as e:
                errors.append(f"Loaded with {kwargs}, but session.laps failed: {type(e).__name__}: {e}")

        except Exception as e:
            errors.append(f"session.load({kwargs}) failed: {type(e).__name__}: {e}")

    raise RuntimeError(
        "FastF1 could not load lap data for this session.\n\n"
        "This is usually not your app code. FastF1 opened the session, but timing/lap data was unavailable.\n\n"
        "Try one of these:\n"
        "- use an older finished session, for example 2024 Monza Q\n"
        "- try another 2026 event/session\n"
        "- use CSV upload mode for 2026\n"
        "- later we can add OpenF1 fallback\n\n"
        "Load attempts:\n" + "\n".join(errors)
    )


def build_selected_lap_tel(
    mode,
    year,
    event_name,
    session_name,
    test_number,
    day_number,
    driver,
    lap_mode,
    lap_number,
):
    session = get_session_from_inputs(
        mode=mode,
        year=year,
        event_name=event_name,
        session_name=session_name,
        test_number=test_number,
        day_number=day_number,
        require_telemetry=True,
    )

    laps = session.laps.pick_drivers(driver.upper())
    if len(laps) == 0:
        raise RuntimeError("No laps found for that driver code.")

    if lap_mode == "Fastest":
        lap = laps.pick_fastest()
    else:
        lap_df = laps[laps["LapNumber"] == int(lap_number)]
        if len(lap_df) == 0:
            raise RuntimeError("That lap number not found.")
        lap = lap_df.iloc[0]

    tel_df = fastf1_lap_to_tel_df(lap)
    return session, tel_df, lap


def fastf1_lap_to_tel_df(lap) -> pd.DataFrame:
    """
    Convert FastF1 lap telemetry + position samples into a compact dataframe
    suitable for HUD/map animation pipelines (e.g. After Effects).
    """
    car = lap.get_car_data()
    car["t"] = car["Time"].dt.total_seconds().astype(float)

    pos = lap.get_pos_data()
    pos["t"] = pos["Time"].dt.total_seconds().astype(float)

    car_cols = ["t"]
    for c in ["Speed", "Throttle", "Brake", "nGear", "RPM", "DRS"]:
        if c in car.columns:
            car_cols.append(c)
    car = car[car_cols].copy()

    pos_cols = ["t"]
    for c in ["X", "Y"]:
        if c in pos.columns:
            pos_cols.append(c)
    pos = pos[pos_cols].copy()

    car = car.sort_values("t")
    pos = pos.sort_values("t")

    # Merge nearest position sample to each car telemetry row
    tel = pd.merge_asof(
        car,
        pos,
        on="t",
        direction="nearest",
        tolerance=0.5,  # slightly wider tolerance reduces NaNs
    )

    # Ensure all columns exist
    if "Speed" not in tel.columns:
        tel["Speed"] = np.nan
    if "Throttle" not in tel.columns:
        tel["Throttle"] = np.nan
    if "Brake" not in tel.columns:
        tel["Brake"] = np.nan
    if "nGear" not in tel.columns:
        tel["nGear"] = np.nan
    if "RPM" not in tel.columns:
        tel["RPM"] = np.nan
    if "DRS" not in tel.columns:
        tel["DRS"] = np.nan
    if "X" not in tel.columns:
        tel["X"] = np.nan
    if "Y" not in tel.columns:
        tel["Y"] = np.nan

    # Fill NaNs safely before casting
    tel["Speed"] = tel["Speed"].fillna(0.0)
    tel["Throttle"] = tel["Throttle"].fillna(0.0)
    tel["Brake"] = tel["Brake"].fillna(0.0)
    tel["RPM"] = tel["RPM"].fillna(0.0)
    tel["DRS"] = tel["DRS"].fillna(0)

    # Gear: fill NaN then cast
    tel["nGear"] = tel["nGear"].fillna(1).astype(int)

    # X/Y: keep NaN as 0 to avoid map errors in downstream tooling
    tel["X"] = tel["X"].fillna(0.0)
    tel["Y"] = tel["Y"].fillna(0.0)

    return pd.DataFrame(
        {
            "t": tel["t"].astype(float),
            "speed_kmh": tel["Speed"].astype(float),
            "throttle": tel["Throttle"].astype(float),
            "brake": tel["Brake"],
            "gear": tel["nGear"].astype(int),
            "rpm": tel["RPM"].astype(float),
            "drs": tel["DRS"],
            "x": tel["X"].astype(float),
            "y": tel["Y"].astype(float),
        }
    )


def _pick_first_present(d: dict, keys: list[str], default=None):
    for k in keys:
        if k in d and pd.notna(d[k]) and str(d[k]).strip() != "":
            return d[k]
    return default


def _find_local_asset(base_dir: Path, subdir: str, stem: str) -> str | None:
    asset_dir = base_dir / "assets" / subdir
    if not asset_dir.exists():
        return None

    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        p = asset_dir / f"{stem}{ext}"
        if p.exists():
            return str(p)
    return None


def _team_slug_candidates(team_name: str) -> list[str]:
    t = team_name.lower().strip()
    compact = (
        t.replace("-", " ")
        .replace("_", " ")
        .replace(".", " ")
    )
    compact = " ".join(compact.split())

    candidates = set()
    candidates.add(compact.replace(" ", "_"))

    alias_map = {
        "ferrari": "ferrari",
        "scuderia ferrari": "ferrari",
        "scuderia ferrari hp": "ferrari",
        "audi": "audi",
        "sauber": "sauber",
        "stake": "sauber",
        "kick sauber": "sauber",
        "mercedes": "mercedes",
        "mclaren": "mclaren",
        "williams": "williams",
        "red bull": "red_bull",
        "racing bulls": "racing_bulls",
        "rb": "racing_bulls",
        "aston martin": "aston_martin",
        "alpine": "alpine",
        "haas": "haas",
    }

    for key, slug in alias_map.items():
        if key in compact:
            candidates.add(slug)

    return sorted(candidates)


def _resolve_car_image(team_name: str, car_url) -> str:
    if pd.notna(car_url) and str(car_url).strip():
        return str(car_url)

    for slug in _team_slug_candidates(team_name):
        if slug in F1_CAR_MEDIA_BY_TEAM:
            return F1_CAR_MEDIA_BY_TEAM[slug]
        local_car = _find_local_asset(BASE_DIR, "cars", slug)
        if local_car:
            return local_car

    # Always return a generic car image as final fallback.
    return GENERIC_CAR_IMAGE_URL


def get_race_event_options(year: int) -> list[str]:
    try:
        sched = fastf1.get_event_schedule(int(year), include_testing=False)
        if "EventDate" in sched.columns:
            sched = sched.sort_values("EventDate",kind="stable")
        if "EventName" in sched.columns:
            vals = [str(v).strip() for v in sched["EventName"].tolist() if pd.notna(v) and str(v).strip()]
            if vals:
                return vals
    except Exception:
        pass

    if int(year) == 2026 and "FALLBACK_2026_RACES" in globals():
        return [race["EventName"] for race in FALLBACK_2026_RACES]

    return [
        "Bahrain",
        "Saudi Arabia",
        "Australia",
        "Japan",
        "China",
        "Miami",
        "Emilia Romagna",
        "Monaco",
        "Canada",
        "Spain",
        "Austria",
        "Great Britain",
        "Hungary",
        "Belgium",
        "Netherlands",
        "Italy",
        "Azerbaijan",
        "Singapore",
        "United States",
        "Mexico",
        "Brazil",
        "Las Vegas",
        "Qatar",
        "Abu Dhabi",
    ]


def get_fallback_schedule(year: int) -> pd.DataFrame:
    if int(year) == 2026:
        return pd.DataFrame(FALLBACK_2026_RACES)
    names = get_race_event_options(int(year))
    return pd.DataFrame(
        {
            "RoundNumber": range(1, len(names) + 1),
            "EventName": names,
            "RaceDate": [pd.NaT] * len(names),
        }
    )


def get_event_schedule_safe(year: int) -> pd.DataFrame:
    try:
        sched = fastf1.get_event_schedule(int(year), include_testing=False).copy()
        if sched is not None and len(sched) > 0 and "EventName" in sched.columns:
            if "RoundNumber" not in sched.columns:
                sched["RoundNumber"] = range(1, len(sched) + 1)
            date_col = None
            for candidate in ["EventDate", "Session5Date", "RaceDate"]:
                if candidate in sched.columns:
                    date_col = candidate
                    break
            if date_col:
                sched["RaceDate"] = pd.to_datetime(sched[date_col], errors="coerce").dt.date
            elif "RaceDate" not in sched.columns:
                sched["RaceDate"] = pd.NaT
            return sched
    except Exception:
        pass
    fallback = get_fallback_schedule(int(year))
    fallback["RaceDate"] = pd.to_datetime(fallback["RaceDate"], errors="coerce").dt.date
    return fallback


def get_latest_completed_race(year: int | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    year = int(year or today.year)
    sched = get_event_schedule_safe(year)
    if "RaceDate" in sched.columns:
        dated = sched.dropna(subset=["RaceDate"]).copy()
        completed = dated[dated["RaceDate"] <= today]
        if len(completed) > 0:
            row = completed.sort_values("RaceDate").iloc[-1]
            return {
                "year": year,
                "event_name": str(row["EventName"]),
                "round_number": int(row["RoundNumber"]) if pd.notna(row["RoundNumber"]) else None,
                "race_date": row["RaceDate"],
            }
    prev = get_event_schedule_safe(year - 1)
    row = prev.iloc[-1]
    return {
        "year": year - 1,
        "event_name": str(row["EventName"]),
        "round_number": int(row["RoundNumber"]) if pd.notna(row["RoundNumber"]) else None,
        "race_date": row.get("RaceDate", None),
    }


def format_laptime(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}:{secs:04.1f}"


def format_axis_laptime(x, pos):
    minutes = int(x // 60)
    seconds = x % 60
    return f"{minutes}:{seconds:04.1f}"


def format_std_axis(x, pos):
    return f"±{x:.2f}s"


def darken_color(color, factor=0.68):
    r, g, b = mcolors.to_rgb(color)
    return (r * factor, g * factor, b * factor)


def save_current_fig(fig, out_path: Path):
    fig.tight_layout()
    fig.savefig(out_path, dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def get_clean_driver_laps(session, driver_code: str) -> pd.DataFrame:
    laps = session.laps.pick_drivers(driver_code).copy()
    laps = laps.sort_values("LapNumber")
    laps = laps.dropna(subset=["LapNumber", "LapTime", "Compound"]).copy()

    if "TrackStatus" in laps.columns:
        laps = laps[laps["TrackStatus"] == "1"]

    if "PitOutTime" in laps.columns:
        laps = laps[laps["PitOutTime"].isna()]

    if "PitInTime" in laps.columns:
        laps = laps[laps["PitInTime"].isna()]

    if "TyreLife" in laps.columns:
        laps = laps[laps["TyreLife"] > 1]

    laps = laps.pick_quicklaps()
    laps = laps.dropna(subset=["LapTime"]).copy()
    laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()

    cols = ["LapNumber", "LapTimeSeconds", "Compound"]
    if "TyreLife" in laps.columns:
        cols.append("TyreLife")

    return laps[cols].copy()


def build_stints_from_laps(laps: pd.DataFrame, driver_code: str | None = None) -> pd.DataFrame:
    laps = laps.copy().sort_values("LapNumber")
    laps = laps.dropna(subset=["LapNumber", "Compound"]).copy()

    laps["PrevCompound"] = laps["Compound"].shift(1)
    compound_change = laps["Compound"] != laps["PrevCompound"]

    if "TyreLife" in laps.columns:
        tyre_reset = laps["TyreLife"].diff().fillna(1) <= 0
    else:
        tyre_reset = False

    laps["NewStint"] = compound_change | tyre_reset
    if not laps.empty:
        laps.iloc[0, laps.columns.get_loc("NewStint")] = True

    laps["StintID"] = laps["NewStint"].cumsum()

    stints = (
        laps.groupby("StintID", as_index=False)
        .agg(
            Compound=("Compound", "first"),
            LapStart=("LapNumber", "min"),
            LapEnd=("LapNumber", "max"),
            LapCount=("LapNumber", "count"),
            AvgLapTime=("LapTimeSeconds", "mean"),
            MedianLapTime=("LapTimeSeconds", "median"),
            StdLapTime=("LapTimeSeconds", "std"),
        )
        .copy()
    )

    if driver_code is not None:
        stints["Driver"] = driver_code

    return stints


def render_fastest_lap_map(session, driver_a: str, driver_b: str, out_path: Path):
    from matplotlib.collections import LineCollection
    from matplotlib.colors import TwoSlopeNorm

    def winner_text(diff, a_code, b_code, threshold=0.02):
        if abs(diff) < threshold:
            return f"Equal {diff:+.3f}s", "white"
        elif diff > 0:
            return f"{a_code} {diff:+.3f}s", get_driver_plot_color(session, driver_a, 'a')
        else:
            return f"{b_code} {diff:+.3f}s", get_driver_plot_color(session, driver_b, 'b')

    lap_a = session.laps.pick_drivers(driver_a).pick_fastest()
    lap_b = session.laps.pick_drivers(driver_b).pick_fastest()

    if lap_a is None or lap_b is None:
        raise ValueError("Could not find fastest laps for one or both drivers.")

    tel_a = lap_a.get_car_data().add_distance().copy()
    tel_b = lap_b.get_car_data().add_distance().copy()

    pos_a = lap_a.get_pos_data().copy()
    pos_b = lap_b.get_pos_data().copy()

    tel_a = tel_a[["Distance", "Time", "Speed"]].dropna().copy()
    tel_b = tel_b[["Distance", "Time", "Speed"]].dropna().copy()
    pos_a = pos_a[["Time", "X", "Y"]].dropna().copy()
    pos_b = pos_b[["Time", "X", "Y"]].dropna().copy()

    max_dist = min(tel_a["Distance"].max(), tel_b["Distance"].max())
    common_dist = np.linspace(0, max_dist, 1200)

    time_a_sec = tel_a["Time"].dt.total_seconds().to_numpy()
    time_b_sec = tel_b["Time"].dt.total_seconds().to_numpy()
    dist_a = tel_a["Distance"].to_numpy()
    dist_b = tel_b["Distance"].to_numpy()

    interp_time_a = np.interp(common_dist, dist_a, time_a_sec)
    interp_time_b = np.interp(common_dist, dist_b, time_b_sec)

    delta = interp_time_b - interp_time_a

    pos_time_a = pos_a["Time"].dt.total_seconds().to_numpy()
    pos_time_b = pos_b["Time"].dt.total_seconds().to_numpy()

    x_a = np.interp(interp_time_a, pos_time_a, pos_a["X"].to_numpy())
    y_a = np.interp(interp_time_a, pos_time_a, pos_a["Y"].to_numpy())
    x_b = np.interp(interp_time_b, pos_time_b, pos_b["X"].to_numpy())
    y_b = np.interp(interp_time_b, pos_time_b, pos_b["Y"].to_numpy())

    x_track = (x_a + x_b) / 2.0
    y_track = (y_a + y_b) / 2.0

    points = np.array([x_track, y_track]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    segment_delta = delta[:-1]

    max_abs = np.nanmax(np.abs(segment_delta))
    norm = TwoSlopeNorm(vmin=-max_abs, vcenter=0.0, vmax=max_abs)

    s1_end = lap_a["Sector1Time"].total_seconds()
    s2_end = s1_end + lap_a["Sector2Time"].total_seconds()

    sector1_x = np.interp(s1_end, pos_time_a, pos_a["X"].to_numpy())
    sector1_y = np.interp(s1_end, pos_time_a, pos_a["Y"].to_numpy())
    sector2_x = np.interp(s2_end, pos_time_a, pos_a["X"].to_numpy())
    sector2_y = np.interp(s2_end, pos_time_a, pos_a["Y"].to_numpy())

    start_x = x_track[0]
    start_y = y_track[0]

    s1_a = lap_a["Sector1Time"].total_seconds()
    s2_a = lap_a["Sector2Time"].total_seconds()
    s3_a = lap_a["Sector3Time"].total_seconds()
    s1_b = lap_b["Sector1Time"].total_seconds()
    s2_b = lap_b["Sector2Time"].total_seconds()
    s3_b = lap_b["Sector3Time"].total_seconds()

    s1_line, _ = winner_text(s1_b - s1_a, driver_a, driver_b)
    s2_line, _ = winner_text(s2_b - s2_a, driver_a, driver_b)
    s3_line, _ = winner_text(s3_b - s3_a, driver_a, driver_b)

    lap_a_time = lap_a["LapTime"].total_seconds()
    lap_b_time = lap_b["LapTime"].total_seconds()
    lap_delta = lap_b_time - lap_a_time

    fig, ax = plt.subplots(figsize=get_figsize(image_format))

    base_track = LineCollection(
        segments,
        colors="#3a3a3a",
        linewidth=12,
        alpha=0.9,
        zorder=1
    )
    ax.add_collection(base_track)

    overlay = LineCollection(
        segments,
        cmap="bwr_r",
        norm=norm,
        linewidth=7,
        alpha=0.98,
        zorder=2
    )
    overlay.set_array(segment_delta)
    ax.add_collection(overlay)

    ax.scatter(start_x, start_y, s=90, color="white", edgecolors="black", linewidths=1.5, zorder=5)
    ax.scatter(sector1_x, sector1_y, s=70, color="white", edgecolors="black", linewidths=1.3, zorder=5)
    ax.scatter(sector2_x, sector2_y, s=70, color="white", edgecolors="black", linewidths=1.3, zorder=5)

    start_txt = ax.text(start_x, start_y, " START", color="white", fontsize=11, va="center", ha="left")
    s1_txt = ax.text(sector1_x, sector1_y, " S1", color="white", fontsize=11, va="center", ha="left")
    s2_txt = ax.text(sector2_x, sector2_y, " S2", color="white", fontsize=11, va="center", ha="left")

    for t in (start_txt, s1_txt, s2_txt):
        t.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground='black'),
            path_effects.Normal()
        ])

    ax.set_title(
        f"{session.event['EventName']} – Fastest Lap Comparison Map\n{driver_a} vs {driver_b}",
        fontsize=20,
        pad=18
    )
    ax.axis("equal")
    ax.axis("off")

    cbar = fig.colorbar(overlay, ax=ax, pad=0.02, shrink=0.8)
    cbar.set_label(f"Track Delta\n(+ {driver_a} faster, - {driver_b} faster)", fontsize=11)

    summary = (
        f"Fastest laps only\n\n"
        f"{driver_a}: {format_laptime(lap_a_time)}\n"
        f"{driver_b}: {format_laptime(lap_b_time)}\n"
        f"Gap: {lap_delta:+.3f}s\n\n"
        f"Sector 1: {s1_line}\n"
        f"Sector 2: {s2_line}\n"
        f"Sector 3: {s3_line}"
    )

    box = ax.text(
        0.02, 0.97,
        summary,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=11,
        color="white",
        bbox=dict(
            boxstyle="round,pad=0.45",
            facecolor="black",
            alpha=0.35,
            edgecolor="white"
        )
    )
    box.set_path_effects([
        path_effects.Stroke(linewidth=3, foreground='black'),
        path_effects.Normal()
    ])

    lab1 = ax.text(
        0.02, 0.08,
        f"Blue = {driver_a} gains time here",
        transform=ax.transAxes,
        color=get_driver_plot_color(session, driver_a, 'a'),
        fontsize=11,
        fontweight="bold"
    )
    lab2 = ax.text(
        0.02, 0.045,
        f"Red = {driver_b} gains time here",
        transform=ax.transAxes,
        color=get_driver_plot_color(session, driver_b, 'b'),
        fontsize=11,
        fontweight="bold"
    )

    for txt in (lab1, lab2):
        txt.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground='black'),
            path_effects.Normal()
        ])

    save_current_fig(fig, out_path)


def render_lap_consistency(session, drivers: list[str], out_path: Path):
    rows = []

    for drv in drivers:
        laps = get_clean_driver_laps(session, drv)
        if laps.empty:
            continue

        median_lap = laps["LapTimeSeconds"].median()
        std_lap = laps["LapTimeSeconds"].std()
        mean_lap = laps["LapTimeSeconds"].mean()
        lap_count = len(laps)

        rows.append({
            "Driver": drv,
            "MedianLap": median_lap,
            "StdDev": std_lap,
            "MeanLap": mean_lap,
            "LapCount": lap_count
        })

    stats = pd.DataFrame(rows)

    if stats.empty:
        raise ValueError("No valid laps found for selected drivers.")

    stats = stats.sort_values("StdDev", ascending=True).reset_index(drop=True)

    bar_colors = [
        get_driver_plot_color(session, drv, 'a')
        for drv in stats["Driver"]
    ]

    fig, ax = plt.subplots(figsize=get_figsize(image_format))

    ax.barh(
        stats["Driver"],
        stats["StdDev"],
        color=bar_colors,
        edgecolor="white",
        linewidth=1.2,
        height=0.72
    )

    ax.invert_yaxis()

    ax.set_title(f"{session.event['EventName']} – Race Pace Consistency", fontsize=22, pad=16)
    ax.set_xlabel("Lap Time Standard Deviation", fontsize=13)
    ax.set_ylabel("")
    ax.grid(axis='x', alpha=0.22)
    ax.grid(axis='y', visible=False)
    ax.xaxis.set_major_formatter(FuncFormatter(format_std_axis))

    xmax = stats["StdDev"].max()
    pad = max(0.01, xmax * 0.025)

    for i, row in stats.iterrows():
        std_val = row["StdDev"]
        median_val = row["MedianLap"]
        lap_count = int(row["LapCount"])

        median_text = f"{int(median_val // 60)}:{median_val % 60:05.2f}"
        label = f"±{std_val:.2f}s\n{median_text} | {lap_count} laps"

        txt = ax.text(
            std_val + pad,
            i,
            label,
            va='center',
            ha='left',
            fontsize=11,
            color='white',
            fontweight='bold'
        )
        txt.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground='black'),
            path_effects.Normal()
        ])

    best = stats.iloc[0]
    worst = stats.iloc[-1]

    summary = (
        f"Most consistent: {best['Driver']} (±{best['StdDev']:.2f}s)\n"
        f"Least consistent: {worst['Driver']} (±{worst['StdDev']:.2f}s)"
    )

    box = ax.text(
        0.985,
        0.97,
        summary,
        transform=ax.transAxes,
        ha='right',
        va='top',
        fontsize=11,
        bbox=dict(
            boxstyle="round,pad=0.45",
            facecolor="black",
            alpha=0.35,
            edgecolor="white"
        )
    )
    box.set_path_effects([
        path_effects.Stroke(linewidth=3, foreground='black'),
        path_effects.Normal()
    ])

    footnote = (
        "Uses green-flag representative laps only\n"
        "Excludes pit in/out laps and first lap on tyre set"
    )

    foot = ax.text(
        0.985,
        0.03,
        footnote,
        transform=ax.transAxes,
        ha='right',
        va='bottom',
        fontsize=9,
        color='white',
        alpha=0.85
    )
    foot.set_path_effects([
        path_effects.Stroke(linewidth=3, foreground='black'),
        path_effects.Normal()
    ])

    ax.set_xlim(0, xmax + pad * 10)

    save_current_fig(fig, out_path)


def render_driver_lap_comparison(session, driver_a: str, driver_b: str, out_path: Path):
    def get_driver_laps(driver):
        laps = session.laps.pick_drivers(driver).copy()

        if 'TrackStatus' in laps.columns:
            laps = laps[laps['TrackStatus'] == '1']
        if 'PitOutTime' in laps.columns:
            laps = laps[laps['PitOutTime'].isna()]
        if 'PitInTime' in laps.columns:
            laps = laps[laps['PitInTime'].isna()]
        if 'TyreLife' in laps.columns:
            laps = laps[laps['TyreLife'] > 1]

        laps = laps.pick_quicklaps()
        laps = laps.dropna(subset=["LapTime"]).copy()
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()
        laps["RollingLapTime"] = (
            laps["LapTimeSeconds"]
            .rolling(window=3, center=True, min_periods=1)
            .mean()
        )
        return laps

    a_laps = get_driver_laps(driver_a)
    b_laps = get_driver_laps(driver_b)

    if a_laps.empty or b_laps.empty:
        raise ValueError("No valid laps found for one or both drivers.")

    compound_colors = fastf1.plotting.get_compound_mapping(session=session)
    color_a = get_driver_plot_color(session, driver_a, "a")
    color_b = get_driver_plot_color(session, driver_b, "b")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

    ax1.scatter(
        a_laps["LapNumber"],
        a_laps["LapTimeSeconds"],
        c=[compound_colors.get(c, "grey") for c in a_laps["Compound"]],
        s=90,
        linewidths=0,
    )
    ax1.plot(a_laps["LapNumber"], a_laps["RollingLapTime"], linewidth=2.8, color=color_a)
    ax1.set_title(driver_a)
    ax1.set_ylabel("Lap Time")
    ax1.invert_yaxis()
    style_axes(ax1, xgrid=True, ygrid=True)

    ax2.scatter(
        b_laps["LapNumber"],
        b_laps["LapTimeSeconds"],
        c=[compound_colors.get(c, "grey") for c in b_laps["Compound"]],
        s=90,
        linewidths=0,
    )
    ax2.plot(b_laps["LapNumber"], b_laps["RollingLapTime"], linewidth=2.8, color=color_b)
    ax2.set_title(driver_b)
    ax2.set_xlabel("Lap Number")
    ax2.set_ylabel("Lap Time")
    ax2.invert_yaxis()
    style_axes(ax2, xgrid=True, ygrid=True)

    ax1.yaxis.set_major_formatter(FuncFormatter(format_axis_laptime))
    ax2.yaxis.set_major_formatter(FuncFormatter(format_axis_laptime))
    plt.suptitle(f"{session.event['EventName']} – {driver_a} vs {driver_b} Race Pace", fontsize=16)

    save_current_fig(fig, out_path)


def render_selected_driver_race_pace(session, drivers: list[str], out_path: Path):
    all_laps = []

    for idx, driver_code in enumerate(drivers):
        laps = session.laps.pick_drivers(driver_code).copy()

        if 'TrackStatus' in laps.columns:
            laps = laps[laps['TrackStatus'] == '1']
        if 'PitOutTime' in laps.columns:
            laps = laps[laps['PitOutTime'].isna()]
        if 'PitInTime' in laps.columns:
            laps = laps[laps['PitInTime'].isna()]
        if 'TyreLife' in laps.columns:
            laps = laps[laps['TyreLife'] > 1]

        laps = laps.pick_quicklaps()
        laps = laps.dropna(subset=['LapTime']).copy()

        if laps.empty:
            continue

        laps["DriverLabel"] = driver_code
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()
        laps["PlotLapNumber"] = laps["LapNumber"] if "LapNumber" in laps.columns else np.arange(1, len(laps) + 1)
        all_laps.append(laps)

    if not all_laps:
        raise ValueError("No valid laps found for the selected drivers.")

    plot_laps = pd.concat(all_laps, ignore_index=True)

    driver_medians = (
        plot_laps.groupby("DriverLabel")["LapTimeSeconds"]
        .median()
        .sort_values()
    )

    driver_order = driver_medians.index.tolist()
    fastest_time = driver_medians.iloc[0]
    driver_deltas = driver_medians - fastest_time

    fig, ax = plt.subplots(figsize=get_figsize(image_format))

    for idx, driver in enumerate(driver_order):
        driver_data = plot_laps[plot_laps["DriverLabel"] == driver].sort_values("PlotLapNumber")
        line_color = get_driver_plot_color(session, driver, "a" if idx % 2 == 0 else "b")
        linestyle = "-" if idx % 2 == 0 else "--"

        ax.plot(
            driver_data["PlotLapNumber"],
            driver_data["LapTimeSeconds"],
            label=driver,
            linewidth=2.5,
            alpha=0.95,
            color=line_color,
            linestyle=linestyle,
        )

        last_x = driver_data["PlotLapNumber"].iloc[-1]
        last_y = driver_data["LapTimeSeconds"].iloc[-1]
        text = ax.text(
            last_x + 0.35,
            last_y,
            driver,
            color=line_color,
            fontsize=10,
            va="center",
            ha="left"
        )
        apply_text_effect(text)

    ax.yaxis.set_major_formatter(FuncFormatter(format_axis_laptime))
    ax.set_title(f"{session.event['EventName']} – Selected Driver Race Pace", fontsize=20, pad=16)
    ax.set_xlabel("Lap Number", fontsize=12)
    ax.set_ylabel("Lap Time", fontsize=12)
    style_axes(ax, xgrid=True, ygrid=True)

    xmax = plot_laps["PlotLapNumber"].max()
    ax.set_xlim(plot_laps["PlotLapNumber"].min() - 1, xmax + 4)

    handles, labels = ax.get_legend_handles_labels()
    label_to_handle = dict(zip(labels, handles))
    ordered_handles = [label_to_handle[label] for label in driver_order]

    legend = ax.legend(
        ordered_handles,
        driver_order,
        title="Median Pace Order",
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        frameon=True
    )

    summary_lines = []
    for pos, driver in enumerate(driver_order[:5], start=1):
        median_val = driver_medians[driver]
        delta_val = driver_deltas[driver]
        mins = int(median_val // 60)
        secs = median_val % 60

        if pos == 1:
            summary_lines.append(f"{pos}. {driver}  {mins}:{secs:05.2f}")
        else:
            summary_lines.append(f"{pos}. {driver}  +{delta_val:.2f}s")

    summary_text = "Top 5 median race pace\n" + "\n".join(summary_lines)

    textbox = ax.text(
        0.015,
        0.98,
        summary_text,
        transform=ax.transAxes,
        va='top',
        ha='left',
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.4", facecolor="black", alpha=0.35, edgecolor="white")
    )
    apply_text_effect(textbox)
    save_current_fig(fig, out_path)


def render_team_race_pace_delta(session, out_path: Path):
    laps = session.laps.pick_wo_box().copy()

    if 'TrackStatus' in laps.columns:
        laps = laps[laps['TrackStatus'] == '1']
    if 'TyreLife' in laps.columns:
        laps = laps[laps['TyreLife'] > 1]

    laps = laps.pick_quicklaps()
    laps = laps.dropna(subset=['LapTime', 'Team']).copy()

    if laps.empty:
        raise ValueError("No valid team pace data found.")

    laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()

    team_medians = (
        laps.groupby("Team")["LapTimeSeconds"]
        .median()
        .sort_values()
    )

    fastest_team = team_medians.index[0]
    fastest_time = team_medians.iloc[0]
    team_delta = (team_medians - fastest_time).sort_values()

    plot_df = pd.DataFrame({
        "Team": team_delta.index,
        "Delta": team_delta.values,
        "MedianLapTime": team_medians.loc[team_delta.index].values
    }).reset_index(drop=True)

    team_colors = [
        get_team_plot_color(session, team)
        for team in plot_df["Team"]
    ]

    fig, ax = plt.subplots(figsize=get_figsize(image_format))

    ax.barh(
        plot_df["Team"],
        plot_df["Delta"],
        color=team_colors,
        edgecolor="white",
        linewidth=1.2,
        height=0.72
    )

    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"+{x:.1f}s"))

    ax.set_title(f"{session.event['EventName']} – Team Race Pace Delta", fontsize=22, pad=16)
    ax.set_xlabel("Delta to Fastest Team", fontsize=13)
    ax.set_ylabel("")
    ax.grid(axis='x', alpha=0.22)
    ax.grid(axis='y', visible=False)
    ax.axvline(0, color='white', linewidth=1.2, alpha=0.8)

    xmax = plot_df["Delta"].max()
    pad = max(0.035, xmax * 0.02 if xmax > 0 else 0.03)

    for i, row in plot_df.iterrows():
        delta = row["Delta"]
        median = row["MedianLapTime"]
        mins = int(median // 60)
        secs = median % 60

        if i == 0:
            label = f"{mins}:{secs:05.2f}\nFASTEST"
        else:
            label = f"+{delta:.2f}s\n{mins}:{secs:05.2f}"

        text_x = delta + pad if delta > 0 else pad

        txt = ax.text(
            text_x,
            i,
            label,
            va='center',
            ha='left',
            fontsize=11,
            color='white',
            fontweight='bold'
        )
        txt.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground='black'),
            path_effects.Normal()
        ])

    if len(plot_df) >= 2:
        p1 = plot_df.iloc[0]
        p2 = plot_df.iloc[1]
        gap = p2["Delta"]

        summary = (
            f"{p1['Team']} had the fastest median race pace.\n"
            f"{p2['Team']} was +{gap:.2f}s behind."
        )

        box = ax.text(
            0.985,
            0.90,
            summary,
            transform=ax.transAxes,
            ha='right',
            va='bottom',
            fontsize=11,
            bbox=dict(
                boxstyle="round,pad=0.45",
                facecolor="black",
                alpha=0.35,
                edgecolor="white"
            )
        )
        box.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground='black'),
            path_effects.Normal()
        ])

    ax.set_xlim(0, xmax + pad * 6)

    save_current_fig(fig, out_path)


def get_inclusive_pace_laps(session, driver_code: str):
    laps = session.laps.pick_drivers(driver_code).copy()
    # Remove only the obvious outliers (pit laps) but keep "slow" green flag laps
    laps = laps[laps["PitOutTime"].isna() & laps["PitInTime"].isna()]
    laps = laps.dropna(subset=["LapTime"])
    laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()
    return laps


def render_gap_to_leader(session, drivers: list[str], out_path: Path):
    fig, ax = plt.subplots(figsize=get_figsize(image_format))
    all_rows = []

    for drv in drivers:
        laps = session.laps.pick_drivers(drv).copy()
        laps = laps.sort_values("LapNumber")
        laps = laps.dropna(subset=["LapNumber", "LapTime"]).copy()

        # Optional cleaning for cleaner race-gap chart
        if "PitOutTime" in laps.columns:
            laps = laps[laps["PitOutTime"].isna()]
        if "PitInTime" in laps.columns:
            laps = laps[laps["PitInTime"].isna()]

        # Optional: keep only normal green-flag laps
        # if "TrackStatus" in laps.columns:
        #     laps = laps[laps["TrackStatus"] == "1"]

        if laps.empty:
            continue

        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()

        # Remove absurd lap outliers that usually break cumulative plots
        median_lap = laps["LapTimeSeconds"].median()
        laps = laps[laps["LapTimeSeconds"] < median_lap * 1.5].copy()

        if laps.empty:
            continue

        laps["CumulativeTime"] = laps["LapTimeSeconds"].cumsum()
        laps["Driver"] = drv

        all_rows.append(laps[["LapNumber", "Driver", "CumulativeTime"]])

    if not all_rows:
        raise ValueError("No valid laps found for selected drivers.")

    df = pd.concat(all_rows, ignore_index=True)

    # Leader at each lap = minimum cumulative time among valid drivers
    leader_df = (
        df.groupby("LapNumber", as_index=False)["CumulativeTime"]
        .min()
        .rename(columns={"CumulativeTime": "LeaderCumulative"})
    )

    df = df.merge(leader_df, on="LapNumber", how="left")
    df["GapToLeader"] = df["CumulativeTime"] - df["LeaderCumulative"]

    for drv in drivers:
        drv_df = df[df["Driver"] == drv].sort_values("LapNumber")
        if drv_df.empty:
            continue

        color = fastf1.plotting.get_driver_color(drv, session)

        ax.plot(
            drv_df["LapNumber"],
            drv_df["GapToLeader"],
            color=color,
            linewidth=2.5,
            alpha=0.95
        )

        last_x = drv_df["LapNumber"].iloc[-1]
        last_y = drv_df["GapToLeader"].iloc[-1]

        txt = ax.text(
            last_x + 0.3,
            last_y,
            f"{drv}  +{last_y:.1f}s",
            color=color,
            fontsize=10,
            va="center",
            ha="left"
        )
        txt.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground="black"),
            path_effects.Normal()
        ])

    ax.set_title(f"{session.event['EventName']} – Gap to Leader", fontsize=20, pad=16)
    ax.set_xlabel("Lap Number", fontsize=12)
    ax.set_ylabel("Gap to Leader (s)", fontsize=12)
    ax.grid(axis="y", alpha=0.25)
    ax.grid(axis="x", alpha=0.10)

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

    save_current_fig(fig, out_path)


def render_tyre_deg_analysis(session, drivers: list[str], out_path: Path):
    fig, ax = plt.subplots(figsize=get_figsize(image_format))
    found_any = False
    summary_lines = []

    for drv in drivers:
        laps = session.laps.pick_drivers(drv).copy()
        laps = laps.dropna(subset=["LapNumber", "LapTime"]).copy()

        # remove race start outlier
        laps = laps[laps["LapNumber"] > 1]

        # remove pit laps
        if "PitOutTime" in laps.columns:
            laps = laps[laps["PitOutTime"].isna()]
        if "PitInTime" in laps.columns:
            laps = laps[laps["PitInTime"].isna()]

        # keep representative race pace only
        if "TrackStatus" in laps.columns:
            laps = laps[laps["TrackStatus"] == "1"]

        laps = laps.dropna(subset=["LapTime"]).copy()
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()

        if len(laps) < 4:
            continue

        found_any = True
        color = fastf1.plotting.get_driver_color(drv, session)

        x = laps["LapNumber"].astype(float).to_numpy()
        y = laps["LapTimeSeconds"].astype(float).to_numpy()

        ax.scatter(
            x,
            y,
            color=color,
            s=45,
            alpha=0.75
        )

        # full-race trendline
        slope, intercept = np.polyfit(x, y, 1)
        x_line = np.linspace(x.min(), x.max(), 200)
        y_line = slope * x_line + intercept

        ax.plot(
            x_line,
            y_line,
            color=color,
            linewidth=2.6,
            label=drv
        )

        last_x = x_line[-1]
        last_y = y_line[-1]

        txt = ax.text(
            last_x + 0.4,
            last_y,
            f"{drv}  slope {slope:+.3f}s/lap",
            color=color,
            fontsize=10,
            va="center",
            ha="left"
        )
        txt.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground="black"),
            path_effects.Normal()
        ])

        summary_lines.append((drv, slope))

    if not found_any:
        raise ValueError("No valid full-race degradation data found for selected drivers.")

    ax.set_title(f"{session.event['EventName']} – Full Race Pace Degradation", fontsize=20, pad=16)
    ax.set_xlabel("Lap Number", fontsize=12)
    ax.set_ylabel("Lap Time", fontsize=12)
    ax.yaxis.set_major_formatter(FuncFormatter(format_axis_laptime))
    ax.grid(axis="y", alpha=0.25)
    ax.grid(axis="x", alpha=0.10)

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

    xmin = min(
        session.laps.pick_drivers(drv)["LapNumber"].dropna().min()
        for drv in drivers if not session.laps.pick_drivers(drv).empty
    )
    xmax = max(
        session.laps.pick_drivers(drv)["LapNumber"].dropna().max()
        for drv in drivers if not session.laps.pick_drivers(drv).empty
    )
    ax.set_xlim(max(1, xmin), xmax + 3)

    if summary_lines:
        summary_lines = sorted(summary_lines, key=lambda t: t[1])
        summary_text = "Degradation slope\n" + "\n".join(
            [f"{drv}: {slope:+.3f}s/lap" for drv, slope in summary_lines]
        )

        box = ax.text(
            0.015,
            0.98,
            summary_text,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=10,
            bbox=dict(
                boxstyle="round,pad=0.4",
                facecolor="black",
                alpha=0.35,
                edgecolor="white"
            )
        )
        box.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground="black"),
            path_effects.Normal()
        ])

    save_current_fig(fig, out_path)


def render_stint_strategy(session, drivers: list[str], out_path: Path):
    def get_driver_stints(driver: str) -> pd.DataFrame:
        laps = session.laps.pick_drivers(driver).copy()
        laps = laps.sort_values("LapNumber")
        laps = laps.dropna(subset=["Compound"]).copy()

        laps["PrevCompound"] = laps["Compound"].shift()
        laps["NewStint"] = laps["Compound"] != laps["PrevCompound"]
        if not laps.empty:
            laps.iloc[0, laps.columns.get_loc("NewStint")] = True

        laps["StintID"] = laps["NewStint"].cumsum()

        stints = (
            laps.groupby("StintID", as_index=False)
            .agg(
                Compound=("Compound", "first"),
                LapStart=("LapNumber", "min"),
                LapEnd=("LapNumber", "max"),
            )
            .copy()
        )
        stints["Driver"] = driver
        return stints

    if not drivers:
        raise ValueError("Please provide at least one driver.")

    stints = pd.concat([get_driver_stints(d) for d in drivers], ignore_index=True)
    compound_colors = fastf1.plotting.get_compound_mapping(session=session)

    fig, ax = plt.subplots(figsize=get_figsize(image_format))
    y_positions = {drv: i for i, drv in enumerate(drivers[::-1])}
    bar_height = 0.55

    for drv in drivers:
        driver_stints = stints[stints["Driver"] == drv]

        for _, row in driver_stints.iterrows():
            start = row["LapStart"]
            end = row["LapEnd"]
            width = end - start + 1
            compound = row["Compound"]
            y = y_positions[drv]

            ax.barh(
                y=y,
                width=width,
                left=start - 0.5,
                height=bar_height,
                color=compound_colors.get(compound, "grey"),
                edgecolor="white",
                linewidth=1.2,
            )

            if width > 3:
                txt = ax.text(
                    start - 0.5 + width / 2,
                    y,
                    compound,
                    ha="center",
                    va="center",
                    fontsize=11,
                    color="white",
                    fontweight="bold",
                )
                txt.set_path_effects([
                    path_effects.Stroke(linewidth=2, foreground="black"),
                    path_effects.Normal(),
                ])

    for drv in drivers:
        driver_stints = stints[stints["Driver"] == drv].sort_values("LapStart")
        y = y_positions[drv]
        for i in range(len(driver_stints) - 1):
            pit_lap = driver_stints.iloc[i]["LapEnd"] + 0.5
            ax.vlines(
                pit_lap,
                y - bar_height / 1.2,
                y + bar_height / 1.2,
                colors="white",
                linestyles="dashed",
                linewidth=1.3,
            )

    ax.set_yticks(list(y_positions.values()))
    ax.set_yticklabels(drivers[::-1])
    ax.set_xlabel("Lap Number")
    ax.set_title(f"{session.event['EventName']} – Stint Strategy", fontsize=20, pad=16)
    ax.grid(axis="x", alpha=0.25)
    ax.grid(axis="y", visible=False)

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)

    used_compounds = stints["Compound"].dropna().unique()
    legend_handles = [
        mpatches.Patch(facecolor=compound_colors.get(c, "grey"), edgecolor="white", label=c)
        for c in used_compounds
    ]
    ax.legend(handles=legend_handles, title="Compound", loc="upper right")

    save_current_fig(fig, out_path)


def render_lap_delta(session, driver_a: str, driver_b: str, out_path: Path):
    a = get_clean_driver_laps(session, driver_a).rename(
        columns={
            "LapTimeSeconds": "A_LapTime",
            "Compound": "A_Compound",
        }
    )
    b = get_clean_driver_laps(session, driver_b).rename(
        columns={
            "LapTimeSeconds": "B_LapTime",
            "Compound": "B_Compound",
        }
    )

    df = pd.merge(a, b, on="LapNumber", how="inner").sort_values("LapNumber").copy()
    if df.empty:
        raise ValueError("No overlapping clean laps found.")

    df["Delta"] = df["B_LapTime"] - df["A_LapTime"]
    df["RollingDelta"] = df["Delta"].rolling(window=3, center=True, min_periods=1).mean()

    color_a = get_driver_plot_color(session, driver_a, 'a')
    color_b = get_driver_plot_color(session, driver_b, 'b')
    compound_colors = fastf1.plotting.get_compound_mapping(session=session)

    bar_colors = np.where(df["Delta"] >= 0, color_a, color_b)

    fig, ax = plt.subplots(figsize=get_figsize(image_format))
    ax.bar(
        df["LapNumber"],
        df["Delta"],
        color=bar_colors,
        width=0.85,
        edgecolor="none",
        alpha=0.95,
        zorder=2,
    )
    ax.axhline(0, color="white", linewidth=1.2, alpha=0.9, zorder=3)
    ax.plot(
        df["LapNumber"],
        df["RollingDelta"],
        color="white",
        linewidth=2.4,
        alpha=0.95,
        zorder=4,
    )

    top_y = max(df["Delta"].max(), 0) * 0.92 if df["Delta"].max() > 0 else 0.15
    bot_y = min(df["Delta"].min(), 0) * 0.92 if df["Delta"].min() < 0 else -0.15

    for _, row in df.iterrows():
        ax.scatter(
            row["LapNumber"],
            top_y,
            s=42,
            color=compound_colors.get(row["A_Compound"], "grey"),
            edgecolors="white",
            linewidths=0.7,
            zorder=5,
        )
        ax.scatter(
            row["LapNumber"],
            bot_y,
            s=42,
            color=compound_colors.get(row["B_Compound"], "grey"),
            edgecolors="white",
            linewidths=0.7,
            zorder=5,
        )

    ax.set_title(
        f"{session.event['EventName']} – {driver_a} vs {driver_b} Lap-by-Lap Pace Delta",
        fontsize=20,
        pad=16,
    )
    ax.set_xlabel("Lap Number", fontsize=13)
    ax.set_ylabel("Pace Delta per Lap", fontsize=13)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:+.1f}s"))
    ax.grid(axis="y", alpha=0.22)
    ax.grid(axis="x", alpha=0.08)

    save_current_fig(fig, out_path)


def render_sector_performance_heatmap(session, drivers: list[str], out_path: Path):
    if not drivers:
        raise ValueError("Please provide at least one driver.")

    rows = []

    for drv in drivers:
        laps = session.laps.pick_drivers(drv).copy()
        laps = laps.dropna(subset=["LapTime", "Sector1Time", "Sector2Time", "Sector3Time"]).copy()

        if "PitOutTime" in laps.columns:
            laps = laps[laps["PitOutTime"].isna()]
        if "PitInTime" in laps.columns:
            laps = laps[laps["PitInTime"].isna()]
        if "TrackStatus" in laps.columns:
            laps = laps[laps["TrackStatus"] == "1"]

        laps = laps.pick_quicklaps()

        if laps.empty:
            continue

        s1 = laps["Sector1Time"].dt.total_seconds().median()
        s2 = laps["Sector2Time"].dt.total_seconds().median()
        s3 = laps["Sector3Time"].dt.total_seconds().median()

        rows.append({
            "Driver": drv,
            "S1": s1,
            "S2": s2,
            "S3": s3
        })

    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError("No valid sector data found for selected drivers.")

    df = df.sort_values(["S1", "S2", "S3"]).reset_index(drop=True)

    sector_cols = ["S1", "S2", "S3"]
    values = df[sector_cols].copy()

    # lower time = better, so normalize relative to fastest sector
    norm = values.copy()
    for col in sector_cols:
        fastest = values[col].min()
        slowest = values[col].max()
        spread = slowest - fastest

        if spread <= 1e-9:
            norm[col] = 0.0
        else:
            norm[col] = (values[col] - fastest) / spread

    fig, ax = plt.subplots(figsize=(8, max(5, len(df) * 0.7)))

    im = ax.imshow(
        norm[sector_cols].to_numpy(),
        aspect="auto",
        cmap="coolwarm_r",
        vmin=0,
        vmax=1
    )

    ax.set_xticks(range(len(sector_cols)))
    ax.set_xticklabels(["Sector 1", "Sector 2", "Sector 3"], fontsize=12)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["Driver"], fontsize=12)

    ax.set_title(f"{session.event['EventName']} – Sector Performance Heatmap", fontsize=20, pad=16)

    # write actual times inside cells
    for i in range(len(df)):
        for j, col in enumerate(sector_cols):
            val = df.iloc[i][col]
            txt = ax.text(
                j, i, f"{val:.3f}",
                ha="center",
                va="center",
                color="white",
                fontsize=10,
                fontweight="bold"
            )
            txt.set_path_effects([
                path_effects.Stroke(linewidth=3, foreground="black"),
                path_effects.Normal()
            ])

    cbar = fig.colorbar(im, ax=ax, pad=0.02)
    cbar.set_label("Relative sector loss\n0 = fastest, 1 = slowest", fontsize=10)

    # optional summary box
    best_s1 = df.loc[df["S1"].idxmin(), "Driver"]
    best_s2 = df.loc[df["S2"].idxmin(), "Driver"]
    best_s3 = df.loc[df["S3"].idxmin(), "Driver"]

    summary = (
        f"Fastest S1: {best_s1}\n"
        f"Fastest S2: {best_s2}\n"
        f"Fastest S3: {best_s3}"
    )

    box = ax.text(
        1.02, 0.02,
        summary,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=10,
        color="white",
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="black",
            alpha=0.35,
            edgecolor="white"
        )
    )
    box.set_path_effects([
        path_effects.Stroke(linewidth=3, foreground="black"),
        path_effects.Normal()
    ])

    save_current_fig(fig, out_path)


def render_lap_delta_with_stints(session, driver_a: str, driver_b: str, out_path: Path):
    laps_a = get_clean_driver_laps(session, driver_a)
    laps_b = get_clean_driver_laps(session, driver_b)

    stints_a = build_stints_from_laps(laps_a, driver_a)
    stints_b = build_stints_from_laps(laps_b, driver_b)

    merged = pd.merge(
        laps_a,
        laps_b,
        on="LapNumber",
        suffixes=(f"_{driver_a}", f"_{driver_b}"),
    ).sort_values("LapNumber").reset_index(drop=True)

    if merged.empty:
        raise ValueError(f"No overlapping clean laps found for {driver_a} and {driver_b}.")

    merged["Delta"] = (
        merged[f"LapTimeSeconds_{driver_b}"] - merged[f"LapTimeSeconds_{driver_a}"]
    )
    merged["DeltaSmooth"] = (
        merged["Delta"].rolling(window=5, center=True, min_periods=1).mean()
    )

    driver_a_color = get_driver_plot_color(session, driver_a, 'a')
    driver_b_color = get_driver_plot_color(session, driver_b, 'b')
    compound_colors = fastf1.plotting.get_compound_mapping(session=session)

    fig, ax = plt.subplots(figsize=get_figsize(image_format))
    x = merged["LapNumber"]
    y = merged["DeltaSmooth"]

    ax.fill_between(
        x,
        y,
        0,
        where=(y >= 0),
        color=driver_a_color,
        alpha=0.45,
        interpolate=True,
        label=f"{driver_a} faster",
    )

    ax.fill_between(
        x,
        y,
        0,
        where=(y < 0),
        color=driver_b_color,
        alpha=0.45,
        interpolate=True,
        label=f"{driver_b} faster",
    )

    ax.plot(x, y, color="white", linewidth=3.2, zorder=3)
    ax.axhline(0, color="white", linestyle="--", linewidth=1.2, alpha=0.9, zorder=2)

    for i in range(len(stints_a) - 1):
        pit_lap = stints_a.loc[i, "LapEnd"] + 0.5
        ax.axvline(
            pit_lap,
            color=driver_a_color,
            linestyle=":",
            linewidth=2,
            alpha=0.95,
            zorder=1,
        )

    for i in range(len(stints_b) - 1):
        pit_lap = stints_b.loc[i, "LapEnd"] + 0.5
        ax.axvline(
            pit_lap,
            color=driver_b_color,
            linestyle=":",
            linewidth=2,
            alpha=0.95,
            zorder=1,
        )

    yl = max(abs(merged["DeltaSmooth"].min()), abs(merged["DeltaSmooth"].max()))
    yl = max(yl, 0.25)
    top_y = yl * 0.93
    bot_y = -yl * 0.93

    comp_a_col = f"Compound_{driver_a}"
    comp_b_col = f"Compound_{driver_b}"

    for _, row in merged.iterrows():
        ax.scatter(
            row["LapNumber"],
            top_y,
            s=40,
            color=compound_colors.get(row[comp_a_col], "grey"),
            edgecolors="white",
            linewidths=0.7,
            zorder=4,
        )
        ax.scatter(
            row["LapNumber"],
            bot_y,
            s=40,
            color=compound_colors.get(row[comp_b_col], "grey"),
            edgecolors="white",
            linewidths=0.7,
            zorder=4,
        )

    ax.set_title(
        f"{session.event['EventName']} – Lap-by-Lap Pace Delta\n{driver_a} vs {driver_b}",
        fontsize=20,
        pad=16,
    )
    ax.set_xlabel("Lap Number", fontsize=13)
    ax.set_ylabel("Lap Time Delta", fontsize=13)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:+.1f}s"))

    ax.grid(axis="y", alpha=0.22)
    ax.grid(axis="x", alpha=0.08)
    ax.set_xlim(merged["LapNumber"].min() - 1, merged["LapNumber"].max() + 1)
    ax.set_ylim(-yl * 1.1, yl * 1.1)

    top_text = ax.text(
        0.01,
        0.97,
        f"Above 0.0s = {driver_a} faster",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=11,
        color=driver_a_color,
        fontweight="bold",
    )
    bot_text = ax.text(
        0.01,
        0.03,
        f"Below 0.0s = {driver_b} faster",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=11,
        color=driver_b_color,
        fontweight="bold",
    )

    for txt in (top_text, bot_text):
        txt.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground="black"),
            path_effects.Normal(),
        ])

    faster_a = int((merged["Delta"] > 0).sum())
    faster_b = int((merged["Delta"] < 0).sum())
    median_delta = merged["Delta"].median()

    summary_text = (
        f"{driver_a} faster laps: {faster_a}\n"
        f"{driver_b} faster laps: {faster_b}\n"
        f"Median delta: {median_delta:+.2f}s"
    )

    summary = ax.text(
        0.985,
        0.97,
        summary_text,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10,
        color="white",
        bbox=dict(boxstyle="round,pad=0.35", facecolor=(0, 0, 0, 0.35), edgecolor="white"),
    )
    summary.set_path_effects([
        path_effects.Stroke(linewidth=2, foreground="black"),
        path_effects.Normal(),
    ])

    legend_handles = [
        Line2D([0], [0], color=driver_a_color, lw=6, label=driver_a),
        Line2D([0], [0], color=driver_b_color, lw=6, label=driver_b),
    ]
    ax.legend(handles=legend_handles, loc="lower right")

    save_current_fig(fig, out_path)


def render_position_tracker(session, drivers: list[str], out_path: Path):
    fig, ax = plt.subplots(figsize=get_figsize(image_format))
    for idx, drv in enumerate(drivers):
        drv_laps = session.laps.pick_drivers(drv).copy()
        if drv_laps.empty:
            continue
        ax.plot(
            drv_laps['LapNumber'],
            drv_laps['Position'],
            label=drv,
            color=get_driver_plot_color(session, drv, "a" if idx % 2 == 0 else "b"),
            linewidth=2.6
        )
    ax.set_ylim(20.5, 0.5)
    ax.set_yticks(range(1, 21))
    ax.set_title(f"{session.event['EventName']} - Position Tracker", fontsize=20)
    ax.set_xlabel("Lap Number")
    ax.set_ylabel("Position")
    style_axes(ax, xgrid=True, ygrid=True)
    ax.legend(bbox_to_anchor=(1.01, 1), loc='upper left')
    save_current_fig(fig, out_path)


def render_telemetry_comparison(session, lap_num, driver_a, driver_b, out_path):
    laps_a = session.laps.pick_drivers(driver_a).pick_lap(lap_num)
    laps_b = session.laps.pick_drivers(driver_b).pick_lap(lap_num)
    tel_a = laps_a.get_telemetry().add_distance()
    tel_b = laps_b.get_telemetry().add_distance()

    color_a = get_driver_plot_color(session, driver_a, "a")
    color_b = get_driver_plot_color(session, driver_b, "b")

    fig, ax = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    ax[0].plot(tel_a['Distance'], tel_a['Speed'], label=driver_a, color=color_a, linewidth=2.4)
    ax[0].plot(tel_b['Distance'], tel_b['Speed'], label=driver_b, color=color_b, linewidth=2.4)
    ax[0].set_ylabel("Speed (km/h)")
    ax[0].legend()

    ax[1].plot(tel_a['Distance'], tel_a['Throttle'], color=color_a, linewidth=2.2)
    ax[1].plot(tel_b['Distance'], tel_b['Throttle'], color=color_b, linewidth=2.2)
    ax[1].set_ylabel("Throttle %")

    ax[2].plot(tel_a['Distance'], tel_a['Brake'], color=color_a, linewidth=2.2)
    ax[2].plot(tel_b['Distance'], tel_b['Brake'], color=color_b, linewidth=2.2)
    ax[2].set_ylabel("Brake (On/Off)")
    ax[2].set_xlabel("Distance (m)")

    for axis in ax:
        style_axes(axis, xgrid=True, ygrid=True)

    plt.suptitle(f"Lap {lap_num} Telemetry: {driver_a} vs {driver_b}")
    save_current_fig(fig, out_path)


def render_speed_traps(session, out_path: Path):
    laps = session.laps.dropna(subset=['SpeedST']).copy()
    if laps.empty:
        raise ValueError("No Speed Trap data found.")

    max_speeds = laps.groupby('Driver')['SpeedST'].max().sort_values(ascending=False).reset_index()
    fig, ax = plt.subplots(figsize=get_figsize(image_format))
    colors = [get_driver_plot_color(session, d, "a" if i % 2 == 0 else "b") for i, d in enumerate(max_speeds['Driver'])]
    ax.bar(max_speeds['Driver'], max_speeds['SpeedST'], color=colors, edgecolor='white')
    ax.set_title(f"{session.event['EventName']} - Maximum Speed (Speed Trap)", fontsize=20)
    ax.set_ylabel("Speed (km/h)")
    ax.set_ylim(max_speeds['SpeedST'].min() - 5, max_speeds['SpeedST'].max() + 5)
    style_axes(ax, xgrid=False, ygrid=True)
    save_current_fig(fig, out_path)


def render_car_pace_delta_map(
    session,
    driver_a: str,
    driver_b: str,
    out_path: Path,
    lap_mode: str = "Median race lap",
    lap_number: int | None = None
):
    from matplotlib.collections import LineCollection
    from matplotlib.colors import TwoSlopeNorm

    def get_reference_lap(driver_code: str):
        laps = session.laps.pick_drivers(driver_code).copy()
        laps = laps.dropna(subset=["LapTime"]).copy()

        if "PitOutTime" in laps.columns:
            laps = laps[laps["PitOutTime"].isna()]
        if "PitInTime" in laps.columns:
            laps = laps[laps["PitInTime"].isna()]
        if "TrackStatus" in laps.columns:
            laps = laps[laps["TrackStatus"] == "1"]

        laps = laps.pick_quicklaps()
        laps = laps.dropna(subset=["LapTime"]).copy()

        if laps.empty:
            raise ValueError(f"No valid laps found for {driver_code}.")

        if lap_mode == "Fastest lap":
            return laps.pick_fastest()

        if lap_mode == "Same lap number":
            if lap_number is None:
                raise ValueError("Lap number is required.")
            lap_df = laps[laps["LapNumber"] == lap_number]
            if lap_df.empty:
                raise ValueError(f"{driver_code} has no valid lap {lap_number}.")
            return lap_df.iloc[0]

        # Median race lap
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()
        median_time = laps["LapTimeSeconds"].median()
        idx = (laps["LapTimeSeconds"] - median_time).abs().idxmin()
        return laps.loc[idx]

    lap_a = get_reference_lap(driver_a)
    lap_b = get_reference_lap(driver_b)

    tel_a = lap_a.get_car_data().add_distance().copy()
    tel_b = lap_b.get_car_data().add_distance().copy()

    pos_a = lap_a.get_pos_data().copy()
    pos_b = lap_b.get_pos_data().copy()

    tel_a = tel_a[["Distance", "Time", "Speed"]].dropna().copy()
    tel_b = tel_b[["Distance", "Time", "Speed"]].dropna().copy()
    pos_a = pos_a[["Time", "X", "Y"]].dropna().copy()
    pos_b = pos_b[["Time", "X", "Y"]].dropna().copy()

    max_dist = min(tel_a["Distance"].max(), tel_b["Distance"].max())
    common_dist = np.linspace(0, max_dist, 1400)

    time_a_sec = tel_a["Time"].dt.total_seconds().to_numpy()
    time_b_sec = tel_b["Time"].dt.total_seconds().to_numpy()
    dist_a = tel_a["Distance"].to_numpy()
    dist_b = tel_b["Distance"].to_numpy()

    interp_time_a = np.interp(common_dist, dist_a, time_a_sec)
    interp_time_b = np.interp(common_dist, dist_b, time_b_sec)

    # positive = driver_a faster
    delta = interp_time_b - interp_time_a

    pos_time_a = pos_a["Time"].dt.total_seconds().to_numpy()
    pos_time_b = pos_b["Time"].dt.total_seconds().to_numpy()

    x_a = np.interp(interp_time_a, pos_time_a, pos_a["X"].to_numpy())
    y_a = np.interp(interp_time_a, pos_time_a, pos_a["Y"].to_numpy())
    x_b = np.interp(interp_time_b, pos_time_b, pos_b["X"].to_numpy())
    y_b = np.interp(interp_time_b, pos_time_b, pos_b["Y"].to_numpy())

    x_track = (x_a + x_b) / 2.0
    y_track = (y_a + y_b) / 2.0

    points = np.array([x_track, y_track]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    segment_delta = delta[:-1]

    max_abs = np.nanmax(np.abs(segment_delta))
    if max_abs < 1e-9:
        max_abs = 0.001

    norm = TwoSlopeNorm(vmin=-max_abs, vcenter=0.0, vmax=max_abs)

    fig, ax = plt.subplots(figsize=get_figsize(image_format))


    base_track = LineCollection(
        segments,
        colors="#2f2f38",
        linewidth=12,
        alpha=0.9,
        zorder=1
    )
    ax.add_collection(base_track)

    overlay = LineCollection(
        segments,
        cmap="coolwarm_r",
        norm=norm,
        linewidth=7,
        alpha=0.98,
        zorder=2
    )
    overlay.set_array(segment_delta)
    ax.add_collection(overlay)

    start_x = x_track[0]
    start_y = y_track[0]

    ax.scatter(start_x, start_y, s=90, color="white", edgecolors="black", linewidths=1.5, zorder=5)
    txt = ax.text(start_x, start_y, " START", color="white", fontsize=11, va="center", ha="left")
    txt.set_path_effects([
        path_effects.Stroke(linewidth=3, foreground="black"),
        path_effects.Normal()
    ])

    lap_a_time = lap_a["LapTime"].total_seconds()
    lap_b_time = lap_b["LapTime"].total_seconds()
    lap_delta = lap_b_time - lap_a_time

    color_a = fastf1.plotting.get_driver_color(driver_a, session)
    color_b = fastf1.plotting.get_driver_color(driver_b, session)

    ax.set_title(
        f"{session.event['EventName']} – Car Pace Delta Map\n{driver_a} vs {driver_b} ({lap_mode})",
        fontsize=20,
        pad=18
    )
    ax.axis("equal")
    ax.axis("off")

    cbar = fig.colorbar(overlay, ax=ax, pad=0.02, shrink=0.8)
    cbar.set_label(f"Track Delta\n(+ {driver_a} faster, - {driver_b} faster)", fontsize=11)

    summary = (
        f"Car pace proxy via drivers\n\n"
        f"{driver_a}: {format_laptime(lap_a_time)}\n"
        f"{driver_b}: {format_laptime(lap_b_time)}\n"
        f"Gap: {lap_delta:+.3f}s\n"
        f"Mode: {lap_mode}"
    )

    box = ax.text(
        0.02, 0.97,
        summary,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=11,
        color="white",
        bbox=dict(
            boxstyle="round,pad=0.45",
            facecolor="black",
            alpha=0.35,
            edgecolor="white"
        )
    )
    box.set_path_effects([
        path_effects.Stroke(linewidth=3, foreground="black"),
        path_effects.Normal()
    ])

    lab1 = ax.text(
        0.02, 0.08,
        f"Blue = {driver_a} / Car A gains",
        transform=ax.transAxes,
        color=color_a,
        fontsize=11,
        fontweight="bold"
    )
    lab2 = ax.text(
        0.02, 0.045,
        f"Red = {driver_b} / Car B gains",
        transform=ax.transAxes,
        color=color_b,
        fontsize=11,
        fontweight="bold"
    )

    for t in (lab1, lab2):
        t.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground="black"),
            path_effects.Normal()
        ])

    save_current_fig(fig, out_path)


def render_stint_average_pace(session, drivers: list[str], compound_name: str, out_path: Path):
    all_stints = []

    for drv in drivers:
        laps = get_clean_driver_laps(session, drv)
        if laps.empty:
            continue
        all_stints.append(build_stints_from_laps(laps, drv))

    if not all_stints:
        raise ValueError("No valid stint data found.")

    stints = pd.concat(all_stints, ignore_index=True)
    plot_df = stints[stints["Compound"] == compound_name.upper()].copy()

    if plot_df.empty:
        raise ValueError(f"No {compound_name.upper()} stints available.")

    plot_df = plot_df.sort_values("AvgLapTime", ascending=True).reset_index(drop=True)

    base_driver_colors = {
        drv: get_driver_plot_color(session, drv, 'a')
        for drv in plot_df["Driver"].unique()
    }

    fastest = float(plot_df["AvgLapTime"].min())
    slowest = float(plot_df["AvgLapTime"].max())
    spread = slowest - fastest

    # Make tiny differences visually bigger
    pad_left = max(0.15, spread * 0.35)
    pad_right = max(0.25, spread * 0.45)

    x_min = max(0, fastest - pad_left)
    x_max = slowest + pad_right

    fig, ax = plt.subplots(figsize=get_figsize(image_format))

    y_positions = list(range(len(plot_df)))[::-1]
    bar_height = 0.72

    widths = plot_df["AvgLapTime"] - x_min

    ax.barh(
        y=y_positions,
        width=widths,
        left=x_min,
        color=[base_driver_colors[d] for d in plot_df["Driver"]],
        edgecolor="white",
        linewidth=1.2,
        height=bar_height,
    )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(plot_df["Driver"], fontsize=12)
    ax.xaxis.set_major_formatter(FuncFormatter(format_axis_laptime))
    ax.set_xlim(x_min, x_max)

    # Vertical line for fastest stint
    ax.axvline(fastest, color="white", linestyle="--", linewidth=1.4, alpha=0.9)

    for i, (_, row) in enumerate(plot_df.iterrows()):
        y = y_positions[i]
        avg_lap = float(row["AvgLapTime"])
        delta = avg_lap - fastest
        lap_count = int(row["LapCount"]) if "LapCount" in row else 0

        if delta <= 0.0001:
            delta_text = "FASTEST"
        else:
            delta_text = f"+{delta:.3f}s"

        label = (
            f"{row['Driver']}  {format_laptime(avg_lap)}\n"
            f"{delta_text}   |   {lap_count} laps"
        )

        txt = ax.text(
            avg_lap + max(0.03, spread * 0.03),
            y,
            label,
            ha="left",
            va="center",
            fontsize=10,
            color="white",
            fontweight="bold",
        )
        txt.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground="black"),
            path_effects.Normal(),
        ])

    ax.set_title(
        f"{session.event['EventName']} – {compound_name.title()} Stint Average Pace",
        fontsize=22,
        pad=16,
    )
    ax.set_xlabel("Average Lap Time", fontsize=13)
    ax.set_ylabel("")
    ax.grid(axis="x", alpha=0.22)
    ax.grid(axis="y", visible=False)

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)

    save_current_fig(fig, out_path)
