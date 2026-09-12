import streamlit as st
import fastf1
import fastf1.plotting
from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patheffects as path_effects
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.colors as mcolors

# -----------------------------------------------------------------------------
# App paths / page setup
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
ASSET_DIR = BASE_DIR / "assets"
ASSET_HUD_DIR = ASSET_DIR / "hud"
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_CHART_DIR = OUTPUT_DIR / "charts"
OUTPUT_TELEMETRY_DIR = OUTPUT_DIR / "telemetry"
OUTPUT_RADIO_DIR = OUTPUT_DIR / "radio"
OUTPUT_VIDEO_DIR = OUTPUT_DIR / "videos"
OUTPUT_REPLAY_LOG_DIR = OUTPUT_DIR / "replay_logs"
OUTPUT_HUD_EXPORT_DIR = OUTPUT_DIR / "hud_exports"
OUTPUT_HUD_FRAMES_DIR = OUTPUT_DIR / "hud_frames"
REPLAY_CACHE_DIR = BASE_DIR / "replay_cache"
RADIO_CACHE_DIR = OUTPUT_RADIO_DIR / "cache"
RACE_REPLAY_DIR = BASE_DIR / "f1-race-replay"

for directory in [
    ASSET_DIR,
    ASSET_HUD_DIR,
    OUTPUT_DIR,
    OUTPUT_CHART_DIR,
    OUTPUT_TELEMETRY_DIR,
    OUTPUT_RADIO_DIR,
    OUTPUT_VIDEO_DIR,
    OUTPUT_REPLAY_LOG_DIR,
    OUTPUT_HUD_EXPORT_DIR,
    OUTPUT_HUD_FRAMES_DIR,
    REPLAY_CACHE_DIR,
    RADIO_CACHE_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="RACE HYPE Studio", page_icon="F1", layout="wide")


# -----------------------------------------------------------------------------
# FastF1 / matplotlib style
# -----------------------------------------------------------------------------
fastf1.plotting.setup_mpl(
    mpl_timedelta_support=False,
    color_scheme="fastf1",
    #misc_mpl_mods=False
)

# -----------------------------------------------------------------------------
# Broadcast theme / color system
# -----------------------------------------------------------------------------
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

plt.style.use("dark_background")
plt.rcParams["figure.facecolor"] = THEME["background"]
plt.rcParams["axes.facecolor"] = THEME["panel"]
plt.rcParams["savefig.facecolor"] = THEME["background"]
plt.rcParams["axes.edgecolor"] = THEME["panel"]
plt.rcParams["grid.color"] = THEME["grid"]
plt.rcParams["text.color"] = THEME["text"]
plt.rcParams["axes.labelcolor"] = THEME["text"]
plt.rcParams["xtick.color"] = THEME["text"]
plt.rcParams["ytick.color"] = THEME["text"]
plt.rcParams["legend.facecolor"] = THEME["panel"]
plt.rcParams["legend.edgecolor"] = THEME["grid"]
plt.rcParams["font.size"] = 11

COLOR_MODE = "FastF1 Official"
CUSTOM_COLOR_A = "#00D2BE"
CUSTOM_COLOR_B = "#DC0000"
MONO_COLOR_A = "#FFFFFF"
MONO_COLOR_B = "#8B5CF6"

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


# -----------------------------------------------------------------------------
# CSV helpers
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Session / telemetry helpers
# -----------------------------------------------------------------------------
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


GENERIC_CAR_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Automobile.svg/512px-Automobile.svg.png"
F1_CAR_MEDIA_BY_TEAM = {
    "mercedes": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/mercedes/2026mercedescarright.webp",
    "ferrari": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/ferrari/2026ferraricarright.webp",
    "mclaren": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/mclaren/2026mclarencarright.webp",
    "red_bull": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/red_bull/2026red_bullcarright.webp",
    "racing_bulls": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/racing_bulls/2026racing_bullscarright.webp",
    "aston_martin": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/astonmartin/2026astonmartincarright.webp",
    "alpine": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/alpine/2026alpinecarright.webp",
    "haas": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/haas/2026haascarright.webp",
    "williams": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/williams/2026williamscarright.webp",
    "audi": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/audi/2026audicarright.webp",
    "cadillac": "https://media.formula1.com/image/upload/c_lfill,h_224/q_auto/d_common:f1:2026:fallback:car:2026fallbackcarright.webp/v1740000001/common/f1/2026/cadillac/2026cadillaccarright.webp",
}


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


@st.cache_data(show_spinner=False, ttl=3600)
def _build_generic_car_placeholder(team_name: str) -> np.ndarray:
    """Generate a local placeholder car image to avoid broken remote URLs."""
    h, w = 120, 260
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = np.array([20, 24, 33], dtype=np.uint8)  # dark background

    # Body color derived from team name hash (stable but varied)
    seed = abs(hash(team_name)) % 255
    body = np.array([60 + (seed % 120), 80 + ((seed * 3) % 120), 120 + ((seed * 5) % 100)], dtype=np.uint8)

    # Chassis
    img[50:78, 40:220] = body
    # Nose
    img[58:70, 215:248] = body
    # Cockpit
    img[42:58, 95:145] = np.array([35, 40, 52], dtype=np.uint8)

    # Wheels (simple circles)
    yy, xx = np.ogrid[:h, :w]
    for cx, cy, r in [(72, 84, 14), (188, 84, 14)]:
        wheel = (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2
        rim = (xx - cx) ** 2 + (yy - cy) ** 2 <= (r - 5) ** 2
        img[wheel] = np.array([20, 20, 20], dtype=np.uint8)
        img[rim] = np.array([120, 120, 130], dtype=np.uint8)

    return img


def render_driver_media_gallery(session, driver_codes: list[str], heading: str = "Driver & Car Visuals"):
    codes = [c.strip().upper() for c in driver_codes if c and c.strip()]
    if not codes:
        return

    st.markdown(f"### {heading}")
    cols = st.columns(len(codes))

    for idx, code in enumerate(codes):
        with cols[idx]:
            try:
                drv = session.get_driver(code)
            except Exception:
                st.warning(f"No driver data for `{code}`")
                continue

            first = str(_pick_first_present(drv, ["FirstName"], "")).strip()
            last = str(_pick_first_present(drv, ["LastName"], "")).strip()
            broadcast = str(_pick_first_present(drv, ["BroadcastName", "Abbreviation"], code)).strip()
            full_name = f"{first} {last}".strip() if (first or last) else broadcast
            team_name = str(_pick_first_present(drv, ["TeamName", "Team"], "Unknown Team")).strip()

            headshot_url = _pick_first_present(
                drv,
                ["HeadshotUrl", "headshotUrl", "PhotoUrl", "DriverImageUrl"],
                None,
            )
            car_url = _pick_first_present(
                drv,
                ["CarImageUrl", "TeamLogoUrl", "TeamLogo"],
                None,
            )

            local_headshot = _find_local_asset(BASE_DIR, "drivers", code)
            resolved_car_image = _resolve_car_image(team_name, car_url)

            st.caption(code)
            st.markdown(f"**{full_name}**")
            st.caption(team_name)

            if headshot_url:
                st.image(headshot_url, use_container_width=True)
            elif local_headshot:
                st.image(local_headshot, use_container_width=True)
            else:
                st.info("No driver image found")

            try:
                st.image(resolved_car_image, width=200)
            except Exception:
                st.image(_build_generic_car_placeholder(team_name), width=200)


DEFAULT_DRIVER_CODES = [
    "VER", "PER", "LEC", "SAI", "HAM", "RUS", "NOR", "PIA", "ALO", "STR",
    "GAS", "OCO", "TSU", "RIC", "ALB", "SAR", "HUL", "MAG", "BOT", "ZHO", "ANT",
]


@st.cache_data(show_spinner=False, ttl=900)
def get_race_event_options(year: int) -> list[str]:
    try:
        sched = fastf1.get_event_schedule(int(year), include_testing=False)
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


@st.cache_data(show_spinner=False, ttl=900)
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


@st.cache_data(show_spinner=False, ttl=900)
def get_driver_catalog(
    mode: str,
    year: int,
    event_name: str | None,
    session_name: str | None,
    test_number: int | None,
    day_number: int | None,
) -> pd.DataFrame:
    try:
        if mode == "Race Weekend":
            s = fastf1.get_session(int(year), event_name, session_name)
        else:
            s = fastf1.get_testing_session(int(year), int(test_number), int(day_number))

        s.load(laps=False, telemetry=False, weather=False, messages=False)
        results = s.results.copy()
        if results is None or len(results) == 0:
            raise RuntimeError("No session results")

        rows = []
        for _, r in results.iterrows():
            code = str(_pick_first_present(r, ["Abbreviation", "DriverNumber"], "")).strip().upper()
            if not code:
                continue

            first = str(_pick_first_present(r, ["FirstName"], "")).strip()
            last = str(_pick_first_present(r, ["LastName"], "")).strip()
            full_name = f"{first} {last}".strip() or code
            team_name = str(_pick_first_present(r, ["TeamName", "Team"], "Unknown Team")).strip()

            rows.append(
                {
                    "code": code,
                    "label": f"{code} - {full_name}",
                    "team_name": team_name,
                    "headshot_url": _pick_first_present(r, ["HeadshotUrl", "headshotUrl", "PhotoUrl", "DriverImageUrl"], None),
                    "car_url": _pick_first_present(r, ["CarImageUrl", "TeamLogoUrl", "TeamLogo"], None),
                }
            )

        df = pd.DataFrame(rows).drop_duplicates(subset=["code"]).sort_values("code")
        if len(df) == 0:
            raise RuntimeError("No drivers in results")
        return df
    except Exception:
        fallback = pd.DataFrame({"code": DEFAULT_DRIVER_CODES})
        fallback["label"] = fallback["code"]
        fallback["team_name"] = "Unknown Team"
        fallback["headshot_url"] = None
        fallback["car_url"] = None
        return fallback


def render_driver_picker_preview(driver_catalog: pd.DataFrame, code: str, heading: str):
    if driver_catalog is None or len(driver_catalog) == 0 or not code:
        return

    row_df = driver_catalog[driver_catalog["code"] == code.upper()]
    if len(row_df) == 0:
        return
    row = row_df.iloc[0]

    team_name = str(row.get("team_name", "Unknown Team"))
    headshot_url = row.get("headshot_url", None)
    car_url = row.get("car_url", None)
    local_headshot = _find_local_asset(BASE_DIR, "drivers", code.upper())
    resolved_car_image = _resolve_car_image(team_name, car_url)

    st.caption(heading)
    # Keep the driver and car previews close together.
    c_left, c_right, _ = st.columns([1, 1.4, 4])
    with c_left:
        if pd.notna(headshot_url) and str(headshot_url).strip():
            st.image(str(headshot_url), width=80)
        elif local_headshot:
            st.image(local_headshot, width=80)
        else:
            st.info(f"{code.upper()} image not found")
    with c_right:
        try:
            st.image(resolved_car_image, width=260)
        except Exception:
            st.image(_build_generic_car_placeholder(team_name), width=260)


# -----------------------------------------------------------------------------
# Chart helpers
# -----------------------------------------------------------------------------
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
    
# --- 2. Lap-by-Lap Position Chart (Bump Chart) ---
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


try:
    cache_dir = BASE_DIR / "fastf1_cache"
    cache_dir.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))
except Exception:
    # fallback for cloud (Streamlit, Render, etc.)
    fastf1.Cache.enable_cache("/tmp/fastf1")


# -----------------------------------------------------------------------------
# UI selection state
# -----------------------------------------------------------------------------
from services.export_service import normalize_telemetry
from services.fastf1_service import load_fastf1_lap_export
from ui.components import render_header, render_nav
from ui.styles import inject_styles
from ui.workspaces import (
    render_analytics_section,
    render_files_section,
    render_hud_export_section,
    render_live_timing_section,
    render_overview_section,
    render_radio_section,
    render_race_replay_section,
    render_telemetry_export_section,
)


WORKSPACES = [
    "Overview",
    "Live Timing",
    "Analytics",
    "Telemetry Export",
    "HUD Export",
    "Race Replay",
    "Radio",
]

image_format = st.session_state.get("image_format", "16:9 (YouTube)")


def _build_fastf1_export_modern(selection: dict):
    mode = selection.get("mode", "Race Weekend")
    if mode == "Race Weekend":
        return load_fastf1_lap_export(
            int(selection["year"]),
            selection["event"],
            selection["session"],
            selection["driver"],
            selection.get("lap", "Fastest"),
            selection.get("lap_number"),
        )
    session, _, lap = build_selected_lap_tel(
        mode=mode,
        year=int(selection["year"]),
        event_name=selection.get("event") if mode == "Race Weekend" else None,
        session_name=selection.get("session") if mode == "Race Weekend" else None,
        test_number=selection.get("test_number", 1) if mode != "Race Weekend" else None,
        day_number=selection.get("day_number", 1) if mode != "Race Weekend" else None,
        driver=selection["driver"],
        lap_mode=selection.get("lap", "Fastest"),
        lap_number=selection.get("lap_number"),
    )
    raw = lap.get_telemetry()
    canonical = normalize_telemetry(raw, "FastF1")
    metadata = {
        "source": "FastF1",
        "event": str(session.event.get("EventName", selection.get("event", "Testing"))),
        "session": str(getattr(session, "name", selection.get("session", "Testing"))),
        "driver": selection["driver"],
        "lap_number": int(lap.get("LapNumber", 0) or 0),
    }
    return canonical, canonical.copy(), metadata


def _generate_analysis_chart_modern(chart_name: str, selection: dict, controls: dict) -> Path:
    global image_format, COLOR_MODE, CUSTOM_COLOR_A, CUSTOM_COLOR_B

    image_format = selection.get("image_format", "16:9 (YouTube)")
    COLOR_MODE = selection.get("color_mode", "FastF1 Official")
    CUSTOM_COLOR_A = st.session_state.get("custom_color_a", "#00D2BE")
    CUSTOM_COLOR_B = st.session_state.get("custom_color_b", "#DC0000")
    mode = selection.get("mode", "Race Weekend")
    session = get_session_from_inputs(
        mode=mode,
        year=int(selection["year"]),
        event_name=selection.get("event") if mode == "Race Weekend" else None,
        session_name=selection.get("session") if mode == "Race Weekend" else None,
        test_number=controls.get("test_number") if mode != "Race Weekend" else None,
        day_number=controls.get("day_number") if mode != "Race Weekend" else None,
        require_telemetry=chart_name in {
            "Fastest lap map",
            "Telemetry Comparison",
            "Car Pace Delta Map",
            "Speed Trap Analysis",
        },
    )
    driver_a = str(controls.get("driver_a", selection.get("driver_a", "VER"))).upper()
    driver_b = str(controls.get("driver_b", selection.get("driver_b", "LEC"))).upper()
    drivers = [str(value).upper() for value in controls.get("drivers", [])]
    if not drivers:
        drivers = [driver_a, driver_b]
    context = (
        f"{selection['year']}_{selection.get('event', 'Testing')}_"
        f"{selection.get('session', 'Test')}_{chart_name}"
    )
    safe_context = "".join(
        char if char.isalnum() or char in "_-" else "_"
        for char in context
    ).strip("_")
    output = OUTPUT_CHART_DIR / f"{safe_context}.png"

    if chart_name == "Fastest lap map":
        render_fastest_lap_map(session, driver_a, driver_b, output)
    elif chart_name == "Telemetry Comparison":
        render_telemetry_comparison(
            session,
            int(controls.get("lap_number", 10)),
            driver_a,
            driver_b,
            output,
        )
    elif chart_name == "Car Pace Delta Map":
        render_car_pace_delta_map(
            session,
            driver_a,
            driver_b,
            output,
            lap_mode=controls.get("lap_compare_mode", "Fastest laps"),
            lap_number=controls.get("lap_number"),
        )
    elif chart_name == "Sector Performance Heatmap":
        render_sector_performance_heatmap(session, drivers, output)
    elif chart_name == "Selected driver race pace":
        render_selected_driver_race_pace(session, drivers, output)
    elif chart_name == "Driver lap comparison":
        render_driver_lap_comparison(session, driver_a, driver_b, output)
    elif chart_name == "Lap consistency":
        render_lap_consistency(session, drivers, output)
    elif chart_name == "Lap-by-lap pace delta":
        render_lap_delta(session, driver_a, driver_b, output)
    elif chart_name == "Lap-by-lap delta + stints":
        render_lap_delta_with_stints(session, driver_a, driver_b, output)
    elif chart_name == "Stint strategy":
        render_stint_strategy(session, drivers, output)
    elif chart_name == "Hard stint average pace":
        render_stint_average_pace(session, drivers, "HARD", output)
    elif chart_name == "Medium stint average pace":
        render_stint_average_pace(session, drivers, "MEDIUM", output)
    elif chart_name == "Tyre Degradation Analysis":
        render_tyre_deg_analysis(session, drivers, output)
    elif chart_name == "Position Tracker":
        render_position_tracker(session, drivers, output)
    elif chart_name == "Gap to Leader":
        render_gap_to_leader(session, drivers, output)
    elif chart_name == "Team race pace delta":
        render_team_race_pace_delta(session, output)
    elif chart_name == "Speed Trap Analysis":
        render_speed_traps(session, output)
    else:
        raise ValueError(f"Unsupported analysis: {chart_name}")
    return output


inject_styles()
latest_context = get_latest_completed_race(date.today().year)
active_workspace = st.session_state.get("workspace_nav", "Overview")
if active_workspace not in WORKSPACES:
    active_workspace = "Overview"
if st.session_state.get("workspace_nav_control") not in WORKSPACES:
    st.session_state["workspace_nav_control"] = active_workspace
with st.container(key="studio_header"):
    brand_column, nav_column = st.columns([1.2, 5.8], vertical_alignment="center")
    with brand_column:
        render_header(active_workspace)
    with nav_column:
        workspace = render_nav(WORKSPACES, active_workspace)
st.session_state["workspace_nav"] = workspace

shared = {
    "latest": latest_context,
    "event_loader": get_race_event_options,
    "driver_loader": get_driver_catalog,
}
if workspace == "Overview":
    render_overview_section(
        latest=latest_context,
        output_dir=OUTPUT_DIR,
        chart_dir=OUTPUT_CHART_DIR,
        radio_dir=OUTPUT_RADIO_DIR,
        replay_dir=REPLAY_CACHE_DIR,
        fastf1_cache=BASE_DIR / "fastf1_cache",
    )
elif workspace == "Live Timing":
    render_live_timing_section(**shared)
elif workspace == "Analytics":
    render_analytics_section(**shared, generate_chart=_generate_analysis_chart_modern)
elif workspace == "Telemetry Export":
    render_telemetry_export_section(
        **shared,
        fastf1_builder=_build_fastf1_export_modern,
        output_dir=OUTPUT_TELEMETRY_DIR,
    )
elif workspace == "HUD Export":
    render_hud_export_section(
        **shared,
        fastf1_builder=_build_fastf1_export_modern,
        assets_dir=ASSET_HUD_DIR,
        output_dir=OUTPUT_HUD_EXPORT_DIR,
        frames_dir=OUTPUT_HUD_FRAMES_DIR,
    )
elif workspace == "Race Replay":
    render_race_replay_section(**shared, legacy_dir=RACE_REPLAY_DIR)
elif workspace == "Radio":
    render_radio_section(
        **shared,
        cache_dir=RADIO_CACHE_DIR,
        output_dir=OUTPUT_RADIO_DIR,
    )
elif workspace == "Files":
    render_files_section(
        output_dir=OUTPUT_DIR,
        telemetry_dir=OUTPUT_TELEMETRY_DIR,
        chart_dir=OUTPUT_CHART_DIR,
        radio_dir=OUTPUT_RADIO_DIR,
        replay_dir=REPLAY_CACHE_DIR,
        assets_dir=ASSET_DIR,
        hud_export_dir=OUTPUT_HUD_EXPORT_DIR,
        hud_frames_dir=OUTPUT_HUD_FRAMES_DIR,
    )

st.stop()

# Retained only as inert migration reference during this incremental refactor.
_LEGACY_UI_REFERENCE = r'''
st.markdown(
    """
    <div class="f1-hero">
        <div>
            <div class="f1-kicker">Telemetry Studio</div>
            <h1>RACE HYPE</h1>
            <div class="f1-subcopy">
                Analyze sessions, replay races, export lap telemetry, and browse public team-radio clips.
            </div>
        </div>
        <div class="f1-topline">
            <span class="f1-chip">LOCAL</span>
            <span class="f1-chip">FASTF1</span>
            <span class="f1-chip">OPENF1</span>
            <span class="f1-chip">RADIO ARCHIVE</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

WORKSPACES = ["Overview", "Analytics", "Telemetry Export", "Race Replay", "Radio", "Files"]
CHART_GROUPS = {
    "Lap Analysis": [
        "Fastest lap map",
        "Telemetry Comparison",
        "Car Pace Delta Map",
        "Sector Performance Heatmap",
    ],
    "Race Pace": [
        "Selected driver race pace",
        "Driver lap comparison",
        "Lap consistency",
        "Lap-by-lap pace delta",
        "Lap-by-lap delta + stints",
    ],
    "Strategy": [
        "Stint strategy",
        "Hard stint average pace",
        "Medium stint average pace",
        "Tyre Degradation Analysis",
    ],
    "Race Overview": [
        "Position Tracker",
        "Gap to Leader",
        "Team race pace delta",
        "Speed Trap Analysis",
    ],
}

if "workspace_nav" not in st.session_state:
    st.session_state["workspace_nav"] = "Overview"
if st.session_state["workspace_nav"] not in WORKSPACES:
    st.session_state["workspace_nav"] = "Overview"

workspace = st.radio(
    "Workspace",
    WORKSPACES,
    index=WORKSPACES.index(st.session_state["workspace_nav"]),
    horizontal=True,
    label_visibility="collapsed",
    key="workspace_nav",
)

image_format = st.session_state.get("image_format", "16:9 (YouTube)")
COLOR_MODE = st.session_state.get("color_mode", "FastF1 Official")
CUSTOM_COLOR_A = st.session_state.get("custom_color_a", "#00D2BE")
CUSTOM_COLOR_B = st.session_state.get("custom_color_b", "#DC0000")
fps = int(st.session_state.get("export_fps", 30))
mode = st.session_state.get("analysis_mode", "Race Weekend")
create_mode = "Race Telemetry"
chart_mode = False
lap_output_mode = False

if workspace in {"Analytics", "Telemetry Export"}:
    st.markdown('<div class="f1-panel">', unsafe_allow_html=True)
    left, right, v1, v2 = st.columns([1.1, 1.0, 1.0, 1.1])

    with left:
        mode = st.selectbox(
            "Mode",
            ["Race Weekend", "Pre-season Testing"],
            index=["Race Weekend", "Pre-season Testing"].index(st.session_state.get("analysis_mode", "Race Weekend")),
            key="analysis_mode",
        )
    with right:
        fps = st.selectbox("Export FPS", [25, 30, 50], index=[25, 30, 50].index(fps), key="export_fps")
    with v1:
        image_format = st.selectbox(
            "Image format",
            ["16:9 (YouTube)", "1:1 (Instagram)", "9:16 (TikTok)"],
            index=["16:9 (YouTube)", "1:1 (Instagram)", "9:16 (TikTok)"].index(image_format),
            key="image_format",
        )
    with v2:
        COLOR_MODE = st.selectbox(
            "Color mode",
            ["FastF1 Official", "Custom", "Monochrome"],
            index=["FastF1 Official", "Custom", "Monochrome"].index(COLOR_MODE),
            help="Use official FastF1 colors or override them for chart visuals.",
            key="color_mode",
        )

    if COLOR_MODE == "Custom":
        c_a, c_b = st.columns(2)
        with c_a:
            CUSTOM_COLOR_A = st.color_picker("Driver / Series Color A", CUSTOM_COLOR_A, key="custom_color_a")
        with c_b:
            CUSTOM_COLOR_B = st.color_picker("Driver / Series Color B", CUSTOM_COLOR_B, key="custom_color_b")

    if workspace == "Telemetry Export":
        st.markdown("#### Telemetry Export")
        source_col, note_col = st.columns([1, 2])
        with source_col:
            st.selectbox("Source", ["Auto", "FastF1", "OpenF1", "Upload CSV"], index=0, key="telemetry_source")
        with note_col:
            st.info("2026-specific overtake and boost telemetry appears only when exposed by the selected data source.")
        create_mode = "Race Telemetry"
        lap_output_mode = True
    else:
        category = st.segmented_control(
            "Chart category",
            list(CHART_GROUPS.keys()),
            default=st.session_state.get("chart_category", "Lap Analysis"),
            key="chart_category",
        )
        create_mode = st.selectbox(
            "Chart",
            CHART_GROUPS[category],
            index=0,
            key=f"chart_choice_{category}",
        )
        chart_mode = True
        lap_output_mode = False
    st.markdown("</div>", unsafe_allow_html=True)


def parse_driver_list(txt: str) -> list[str]:
    return [x.strip().upper() for x in txt.split(",") if x.strip()]


def safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(value)).strip("_")


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
    "yas marina": "Abu Dhabi Grand Prix",
}


def normalize_radio_race_name(race: str) -> str:
    race_text = str(race).strip()
    key = race_text.lower()
    if key in RADIO_RACE_ALIASES:
        return RADIO_RACE_ALIASES[key]
    grand_prix_bases = {v.lower().replace(" grand prix", "") for v in RADIO_RACE_ALIASES.values()}
    if "grand prix" not in key and key in grand_prix_bases:
        return f"{race_text} Grand Prix"
    return race_text


def tail_text(path: Path, max_lines: int = 80) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    return "\n".join(lines[-max_lines:])


def is_process_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import psutil

        return psutil.pid_exists(int(pid))
    except Exception:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {int(pid)}"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            return str(pid) in result.stdout
        except Exception:
            return False


def apply_app_chrome():
    st.markdown(
        """
        <style>
        :root {
            --f1-bg: #090B10;
            --f1-red: #E10600;
            --f1-yellow: #FACC15;
            --f1-cyan: #38BDF8;
            --f1-green: #2CCB70;
            --f1-panel: #11141B;
            --f1-panel-soft: #161A23;
            --f1-border: rgba(255, 255, 255, 0.08);
            --f1-text: #F5F7FA;
            --f1-muted: #9DA7B4;
        }

        .stApp {
            background:
                radial-gradient(circle at 12% 0%, rgba(225, 6, 0, 0.14), transparent 28rem),
                linear-gradient(180deg, #0C0F16 0%, var(--f1-bg) 26rem, #07090D 100%);
            color: var(--f1-text);
        }

        .block-container {
            padding-top: 1.0rem;
            padding-bottom: 2rem;
            max-width: 1420px;
        }

        h1, h2, h3 {
            letter-spacing: 0;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #090a10, #11131c);
            border-right: 1px solid var(--f1-border);
        }

        div[role="radiogroup"] {
            gap: 0.55rem;
            flex-wrap: wrap;
            background: rgba(17, 20, 27, 0.78);
            border: 1px solid var(--f1-border);
            border-radius: 12px;
            padding: 0.4rem;
            width: fit-content;
            max-width: 100%;
            margin-bottom: 1rem;
        }

        div[role="radiogroup"] label {
            background: transparent;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 0.5rem 0.75rem;
            margin: 0;
        }

        div[role="radiogroup"] label:has(input:checked) {
            border-color: rgba(225, 6, 0, 0.65);
            background: rgba(225, 6, 0, 0.15);
        }

        div[role="radiogroup"] label [data-testid="stMarkdownContainer"] p {
            font-weight: 800;
        }

        [data-testid="stMetric"],
        [data-testid="stDataFrame"],
        .stAlert,
        div[data-testid="stExpander"] {
            border: 1px solid var(--f1-border);
            border-radius: 12px;
            background: rgba(17, 20, 27, 0.9);
            box-shadow: 0 18px 48px rgba(0, 0, 0, 0.18);
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 10px;
            border: 1px solid rgba(225, 6, 0, 0.62);
            background: linear-gradient(180deg, #ff2a17, #E10600);
            color: white;
            font-weight: 700;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: #ffd23f;
            color: white;
            filter: brightness(1.08);
        }

        .stSelectbox div[data-baseweb="select"],
        .stTextInput input,
        .stNumberInput input {
            background: var(--f1-panel-soft);
            border-color: var(--f1-border);
        }

        .f1-hero {
            position: relative;
            display: flex;
            align-items: end;
            justify-content: space-between;
            gap: 1rem;
            border-left: 4px solid var(--f1-red);
            padding: 0.25rem 0 0.85rem 1rem;
            margin-bottom: 0.9rem;
            max-width: 1220px;
        }

        .f1-hero h1 {
            font-size: clamp(2.1rem, 4vw, 3.1rem);
            line-height: 1;
            margin: 0.1rem 0 0.35rem;
            text-transform: uppercase;
        }

        .f1-kicker {
            color: var(--f1-yellow);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.18em;
            text-transform: uppercase;
        }

        .f1-subcopy {
            color: var(--f1-muted);
            max-width: 760px;
        }

        .f1-topline {
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
            margin-top: 0.9rem;
        }

        .f1-chip {
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.055);
            color: #e8eaf2;
            font-size: 0.78rem;
            font-weight: 750;
            padding: 0.35rem 0.55rem;
            text-transform: uppercase;
        }

        .f1-note {
            border-left: 3px solid var(--f1-cyan);
            background: rgba(56, 189, 248, 0.075);
            padding: 0.75rem 0.9rem;
            border-radius: 0 8px 8px 0;
            color: #dbeafe;
            margin: 0.4rem 0 1rem;
        }

        .f1-panel {
            border: 1px solid var(--f1-border);
            background: rgba(17, 20, 27, 0.72);
            border-radius: 14px;
            padding: 0.9rem;
            margin-bottom: 1rem;
        }

        @media (max-width: 820px) {
            .f1-hero {
                align-items: start;
                flex-direction: column;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header():
    st.markdown(
        """
        <div class="f1-hero">
            <div class="f1-kicker">Race Control Studio</div>
            <h1>RACE HYPE Studio</h1>
            <div class="f1-subcopy">
                Build race graphics, export HUD telemetry, and pull team-radio clips from one workspace.
            </div>
            <div class="f1-topline">
                <span class="f1-chip">FastF1 telemetry</span>
                <span class="f1-chip">OpenF1 radio</span>
                <span class="f1-chip">AE / RaceRender exports</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False, ttl=3600)
def load_radio_session_data(year: int, race: str, session_code: str, force_refresh: bool = False):
    import f1radio

    requested_race = str(race).strip()
    resolved_race = normalize_radio_race_name(requested_race)
    f1radio.set_cache_dir(str(RADIO_CACHE_DIR))
    session = f1radio.load(
        int(year),
        resolved_race,
        str(session_code).strip().upper(),
        verbose=False,
        force_refresh=bool(force_refresh),
    )

    safe_label = safe_filename(f"radio_{year}_{session.race}_{session.session_type}")
    csv_path = OUTPUT_RADIO_DIR / f"{safe_label}.csv"
    json_path = OUTPUT_RADIO_DIR / f"{safe_label}.json"
    session.export_csv(str(csv_path))
    session.export_json(str(json_path))

    rows = []
    for idx, clip in enumerate(session.clips):
        rows.append(
            {
                "idx": idx,
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
        "requested_race": requested_race,
        "resolved_race": resolved_race,
        "race": session.race,
        "session_type": session.session_type,
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "clips": rows,
    }


def render_local_radio_exports(error: Exception | None = None) -> bool:
    local_exports = sorted(OUTPUT_RADIO_DIR.glob("*.csv")) + sorted(BASE_DIR.glob("*radio*.csv"))
    if not local_exports:
        return False

    if error is not None:
        st.warning(f"Live radio load failed, so I switched to local exports: {error}")

    export_path = st.selectbox(
        "Local radio export",
        local_exports,
        format_func=lambda p: p.name,
    )
    clips_df = pd.read_csv(export_path)
    if clips_df.empty:
        st.info("That export has no clips.")
        return True

    if "position" not in clips_df.columns and "context_position" in clips_df.columns:
        clips_df["position"] = clips_df["context_position"]
    if "compound" not in clips_df.columns and "context_compound" in clips_df.columns:
        clips_df["compound"] = clips_df["context_compound"]

    clips_df["_row_id"] = range(len(clips_df))
    counts = clips_df.groupby("driver", dropna=False).size().reset_index(name="clips").sort_values(["clips", "driver"], ascending=[False, True])
    st.caption(f"Local export contains {len(clips_df)} clips across {counts['driver'].nunique()} drivers.")
    driver_options = ["ALL"] + sorted(clips_df["driver"].dropna().astype(str).unique().tolist())
    selected_driver = st.selectbox("Driver", driver_options, index=0, key="local-radio-driver")
    filtered = clips_df if selected_driver == "ALL" else clips_df[clips_df["driver"] == selected_driver]
    filtered = filtered.reset_index(drop=True)
    st.caption(f"Showing {len(filtered)} of {len(clips_df)} clips.")

    labels = []
    for _, row in filtered.iterrows():
        lap = "" if pd.isna(row.get("lap", np.nan)) else int(row.get("lap"))
        pos = "" if pd.isna(row.get("position", np.nan)) else int(row.get("position"))
        labels.append(f"{int(row['_row_id'])} | {row.get('driver', '-')} | {row.get('time', '-')} | Lap {lap} | P{pos}")

    selected_label = st.selectbox("Radio clip", labels, index=0, key="local-radio-clip")
    selected_idx = int(selected_label.split("|", 1)[0].strip())
    selected = clips_df[clips_df["_row_id"] == selected_idx].iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Driver", selected.get("driver", "-"))
    c2.metric("Lap", "-" if pd.isna(selected.get("lap", np.nan)) else int(selected.get("lap")))
    c3.metric("Position", "-" if pd.isna(selected.get("position", np.nan)) else f"P{int(selected.get('position'))}")
    c4.metric("Tyre", "-" if pd.isna(selected.get("compound", np.nan)) else str(selected.get("compound")))

    local_path_value = selected.get("local_path", "")
    local_path = Path(str(local_path_value)) if pd.notna(local_path_value) and str(local_path_value).strip() else None
    if local_path and local_path.exists():
        audio_bytes = local_path.read_bytes()
        st.audio(audio_bytes, format="audio/mp3")
        st.download_button(
            "Download selected MP3",
            data=audio_bytes,
            file_name=local_path.name,
            mime="audio/mpeg",
            key="local-radio-mp3",
        )
    elif pd.notna(selected.get("recording_url", np.nan)) and str(selected.get("recording_url")).strip():
        st.audio(str(selected.get("recording_url")))
        st.link_button("Open MP3 source", str(selected.get("recording_url")))
    else:
        st.warning("This clip has no playable local file or recording URL.")

    show_cols = [c for c in ["driver", "driver_name", "team", "time", "lap", "position", "compound"] if c in clips_df.columns]
    st.dataframe(filtered[show_cols], use_container_width=True, hide_index=True)
    with st.expander("Clip count by driver", expanded=False):
        st.dataframe(counts, use_container_width=True, hide_index=True)
    st.download_button(
        "Download local session CSV",
        data=export_path.read_bytes(),
        file_name=export_path.name,
        mime="text/csv",
        key="local-radio-csv",
    )
    return True


def render_radio_messages_section():
    st.subheader("Radio Messages")
    st.markdown(
        """
        <div class="f1-note">
            F1 radio data comes from the public OpenF1/FOM timing archive. It is not every private team-radio exchange, so some sessions only expose a handful of short clips.
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        import f1radio  # noqa: F401
    except Exception:
        st.error("The `f1radio` package is not available in this Python environment. Install requirements in the app venv, then reload.")
        render_local_radio_exports()
        return

    latest = get_latest_completed_race(date.today().year)
    latest_label = f"{latest['event_name']} ({latest['race_date']})" if latest.get("race_date") else latest["event_name"]
    st.markdown(f'<div class="f1-note">Latest completed race default: <strong>{latest_label}</strong></div>', unsafe_allow_html=True)

    existing_query = st.session_state.get(
        "radio_query",
        {
            "year": int(latest["year"]),
            "race": latest["event_name"],
            "session": "R",
            "force_refresh": False,
        },
    )

    session_options = ["R", "Q", "SQ", "S", "FP1", "FP2", "FP3"]
    session_index = session_options.index(existing_query.get("session", "R")) if existing_query.get("session", "R") in session_options else 0

    c1, c2, c3, c4 = st.columns([0.85, 1.8, 0.85, 0.9])
    with c1:
        radio_year = st.number_input("Year", min_value=2023, max_value=2035, value=int(existing_query.get("year", latest["year"])), step=1)
    event_options = get_race_event_options(int(radio_year))
    default_event = str(existing_query.get("race", latest["event_name"]))
    if default_event not in event_options and latest["event_name"] in event_options and int(radio_year) == int(latest["year"]):
        default_event = latest["event_name"]
    event_index = event_options.index(default_event) if default_event in event_options else 0
    with c2:
        radio_race = st.selectbox("Track / Event", event_options, index=event_index)
    with c3:
        radio_session = st.selectbox("Session", session_options, index=session_index)
    with c4:
        force_refresh = st.checkbox("Refresh cache", value=bool(existing_query.get("force_refresh", False)))

    load_clicked = st.button("Load radio messages", type="primary")
    use_latest = st.button("Use latest completed race")

    if use_latest:
        st.session_state["radio_query"] = {
            "year": int(latest["year"]),
            "race": latest["event_name"],
            "session": "R",
            "force_refresh": False,
        }
        st.rerun()

    if load_clicked:
        st.session_state["radio_query"] = {
            "year": int(radio_year),
            "race": radio_race,
            "session": radio_session,
            "force_refresh": force_refresh,
        }

    if "radio_query" not in st.session_state:
        st.info("Choose a track, driver/session setup, then load radio messages.")
        return

    query = st.session_state["radio_query"]
    st.caption(
        f"Loading request: {query['year']} {query['race']} {query['session']} "
        f"(resolved as {normalize_radio_race_name(query['race'])})"
    )

    try:
        with st.spinner("Loading team radio and cached MP3 files..."):
            radio_data = load_radio_session_data(
                query["year"],
                query["race"],
                query["session"],
                query["force_refresh"],
            )
    except Exception as e:
        if not render_local_radio_exports(e):
            st.error(str(e))
        return

    clips_df = pd.DataFrame(radio_data["clips"])
    if clips_df.empty:
        st.warning("No radio clips found for that session.")
        return

    st.success(
        f"{radio_data['race']} {radio_data['session_type']}: {len(clips_df)} public clips ready."
    )
    if radio_data["resolved_race"].lower() != radio_data["requested_race"].lower():
        st.caption(f"Race alias applied: {radio_data['requested_race']} -> {radio_data['resolved_race']}")

    counts = clips_df.groupby("driver", dropna=False).size().reset_index(name="clips").sort_values(["clips", "driver"], ascending=[False, True])
    c_total, c_drivers, c_top = st.columns(3)
    c_total.metric("Public clips", len(clips_df))
    c_drivers.metric("Drivers with clips", counts["driver"].nunique())
    c_top.metric("Most clips", f"{counts.iloc[0]['driver']} ({int(counts.iloc[0]['clips'])})")

    d1, d2 = st.columns([1, 2])
    with d1:
        driver_options = ["ALL"] + sorted(clips_df["driver"].dropna().astype(str).unique().tolist())
        selected_driver = st.selectbox("Driver", driver_options, index=0, key="radio-driver-filter-v2")

    filtered = clips_df if selected_driver == "ALL" else clips_df[clips_df["driver"] == selected_driver]
    filtered = filtered.reset_index(drop=True)
    st.caption(f"Showing {len(filtered)} of {len(clips_df)} clips. Choose ALL to see every public clip in this session.")

    with d2:
        clip_labels = [
            f"{int(row.idx)} | {row.driver} | {row.time} | Lap {'' if pd.isna(row.lap) else int(row.lap)} | P{'' if pd.isna(row.position) else int(row.position)}"
            for row in filtered.itertuples()
        ]
        selected_label = st.selectbox("Radio clip", clip_labels, index=0, key="radio-clip-v2")

    selected_idx = int(selected_label.split("|", 1)[0].strip())
    selected = clips_df[clips_df["idx"] == selected_idx].iloc[0]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Driver", selected["driver"])
    m2.metric("Lap", "-" if pd.isna(selected["lap"]) else int(selected["lap"]))
    m3.metric("Position", "-" if pd.isna(selected["position"]) else f"P{int(selected['position'])}")
    m4.metric("Tyre", "-" if pd.isna(selected["compound"]) else str(selected["compound"]))

    local_path = Path(str(selected["local_path"]))
    if local_path.exists():
        audio_bytes = local_path.read_bytes()
        st.audio(audio_bytes, format="audio/mp3")
        st.download_button(
            "Download selected MP3",
            data=audio_bytes,
            file_name=local_path.name,
            mime="audio/mpeg",
        )
    elif selected["recording_url"]:
        st.audio(str(selected["recording_url"]))
        st.link_button("Open MP3 source", str(selected["recording_url"]))
    else:
        st.warning("This clip has no audio file or recording URL.")

    st.dataframe(
        filtered[["driver", "driver_name", "team", "time", "lap", "position", "compound", "tyre_age", "last_lap"]],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Clip count by driver", expanded=False):
        st.dataframe(counts, use_container_width=True, hide_index=True)

    csv_path = Path(radio_data["csv_path"])
    json_path = Path(radio_data["json_path"])
    c_csv, c_json = st.columns(2)
    with c_csv:
        st.download_button(
            "Download session CSV",
            data=csv_path.read_bytes(),
            file_name=csv_path.name,
            mime="text/csv",
        )
    with c_json:
        st.download_button(
            "Download session JSON",
            data=json_path.read_bytes(),
            file_name=json_path.name,
            mime="application/json",
        )


def render_race_replay_section():
    st.subheader("Race Replay")
    st.markdown(
        """
        <div class="f1-note">
            Browser-native replay runs inside this Streamlit page. It does not open an external viewer, tab, or desktop window.
        </div>
        """,
        unsafe_allow_html=True,
    )

    latest = get_latest_completed_race(date.today().year)
    replay_year = st.number_input(
        "Year",
        min_value=2018,
        max_value=2035,
        value=int(st.session_state.get("replay_year", latest["year"])),
        step=1,
        key="replay_year",
    )
    schedule = get_event_schedule_safe(int(replay_year))
    event_names = schedule["EventName"].astype(str).tolist()
    selected_default = st.session_state.get("replay_event", latest["event_name"])
    default_event = selected_default if selected_default in event_names else (
        latest["event_name"] if int(replay_year) == int(latest["year"]) and latest["event_name"] in event_names else event_names[0]
    )
    event_index = event_names.index(default_event)

    c1, c2, c3, c4, c5 = st.columns([1.0, 2.0, 1.1, 1.1, 0.95])
    with c1:
        st.metric("Latest completed", latest["event_name"])
    with c2:
        replay_event = st.selectbox("Event / round", event_names, index=event_index, key="replay_event")
    selected_row = schedule[schedule["EventName"].astype(str) == replay_event].iloc[0]
    round_number = int(selected_row["RoundNumber"]) if pd.notna(selected_row["RoundNumber"]) else event_index + 1
    with c3:
        replay_session = st.selectbox("Session type", ["Race", "Sprint", "Qualifying", "Sprint Qualifying"], index=0, key="replay_session")
    with c4:
        sample_rate = st.selectbox("Sample rate", [4, 5, 8, 10], index=1, format_func=lambda v: f"{v} Hz", key="replay_rate")
    with c5:
        refresh_data = st.checkbox("Refresh data", value=False, key="replay_refresh")

    load_col, meta_col = st.columns([1, 3])
    with load_col:
        load_replay = st.button("Load Replay", type="primary", use_container_width=True)
    with meta_col:
        st.caption(f"Round {round_number} · cached payloads: {len(list_replay_cache())}")

    if load_replay:
        progress = st.progress(0, text="Preparing replay")

        def update_progress(value, text):
            progress.progress(min(1.0, float(value)), text=text)

        try:
            payload = build_replay_payload(
                int(replay_year),
                replay_event,
                replay_session,
                sample_rate_hz=int(sample_rate),
                refresh=bool(refresh_data),
                progress_callback=update_progress,
            )
            st.session_state["replay_payload"] = payload
            st.success("Replay payload ready.")
        except Exception as e:
            st.error(f"Replay could not be loaded: {e}")
            with st.expander("Technical details", expanded=False):
                st.code(str(e), language="text")

    payload = st.session_state.get("replay_payload")
    if payload:
        meta = payload.get("meta", {})
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Event", meta.get("event", replay_event))
        m2.metric("Session", meta.get("session", replay_session))
        m3.metric("Frames", len(payload.get("frames", [])))
        m4.metric("Drivers", len(payload.get("drivers", {})))
        render_embedded_replay(payload)
    else:
        st.info("Choose a session and load the replay. The first build can take a little while; cached reloads are much faster.")

    with st.expander("Advanced", expanded=False):
        a1, a2, a3 = st.columns(3)
        with a1:
            if st.button("Clear replay cache"):
                removed = clear_replay_cache()
                st.success(f"Removed {removed} replay payload file(s).")
        with a2:
            if payload:
                st.download_button(
                    "Download replay payload JSON",
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    file_name=f"replay_{safe_filename(str(meta.get('event', replay_event)))}_{meta.get('session', replay_session)}.json",
                    mime="application/json",
                )
        with a3:
            st.caption("The desktop viewer remains only for troubleshooting.")

        if payload:
            with st.expander("View technical processing details", expanded=False):
                st.json(payload.get("technical", {}))

        with st.expander("Legacy desktop viewer", expanded=False):
            repo_url = "https://github.com/4f4d/f1-race-replay"
            main_py = RACE_REPLAY_DIR / "main.py"
            if not main_py.exists():
                st.warning("Legacy desktop viewer repo is not installed in this workspace.")
                st.link_button("Open GitHub repo", repo_url)
            else:
                no_hud = st.checkbox("No HUD", value=False, key="legacy_no_hud")
                legacy_refresh = st.checkbox("Refresh legacy data", value=False, key="legacy_refresh")
                args = [sys.executable, "-u", "main.py", "--viewer", "--year", str(int(replay_year)), "--round", str(round_number)]
                if replay_session == "Sprint":
                    args.append("--sprint")
                elif replay_session == "Sprint Qualifying":
                    args.append("--sprint-qualifying")
                elif replay_session == "Qualifying":
                    args.append("--qualifying")
                if no_hud:
                    args.append("--no-hud")
                if legacy_refresh:
                    args.append("--refresh-data")
                st.code(" ".join(args), language="powershell")
                if st.button("Launch legacy desktop viewer"):
                    try:
                        OUTPUT_REPLAY_LOG_DIR.mkdir(parents=True, exist_ok=True)
                        run_label = safe_filename(f"{int(replay_year)}_{round_number}_{replay_session}")
                        log_path = OUTPUT_REPLAY_LOG_DIR / f"race_replay_{run_label}.log"
                        ready_path = OUTPUT_REPLAY_LOG_DIR / f"race_replay_{run_label}.ready"
                        if ready_path.exists():
                            ready_path.unlink()
                        launch_args = args + ["--ready-file", str(ready_path)]
                        log_file = log_path.open("w", encoding="utf-8", errors="replace")
                        creationflags = 0
                        if sys.platform.startswith("win"):
                            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                        proc = subprocess.Popen(
                            launch_args,
                            cwd=str(RACE_REPLAY_DIR),
                            stdout=log_file,
                            stderr=subprocess.STDOUT,
                            text=True,
                            creationflags=creationflags,
                            env={
                                **os.environ,
                                "PYTHONUNBUFFERED": "1",
                                "PYTHONIOENCODING": "utf-8",
                                "PYTHONUTF8": "1",
                            },
                        )
                        log_file.close()
                        st.session_state["race_replay_last_log"] = str(log_path)
                        st.session_state["race_replay_last_ready"] = str(ready_path)
                        st.session_state["race_replay_last_pid"] = proc.pid
                        st.session_state["race_replay_last_command"] = " ".join(launch_args)
                        st.success(f"Legacy viewer started. PID: {proc.pid}")
                    except Exception as e:
                        st.error(f"Could not launch legacy desktop viewer: {e}")

            last_log = st.session_state.get("race_replay_last_log")
            if last_log:
                log_path = Path(last_log)
                if log_path.exists():
                    st.code(tail_text(log_path), language="text")
                    st.download_button(
                        "Download replay log",
                        data=log_path.read_bytes(),
                        file_name=log_path.name,
                        mime="text/plain",
                    )


def render_library_section():
    st.subheader("Files")

    locations = [
        ("Recent exports", OUTPUT_DIR),
        ("Telemetry files", OUTPUT_TELEMETRY_DIR),
        ("Chart images", OUTPUT_CHART_DIR),
        ("Radio audio", RADIO_CACHE_DIR),
        ("Radio CSV / JSON", OUTPUT_RADIO_DIR),
        ("Replay payload cache", REPLAY_CACHE_DIR),
        ("Assets", ASSET_DIR),
    ]

    stats_cols = st.columns(3)
    stats_cols[0].metric("File groups", len(locations))
    stats_cols[1].metric("Replay payloads", len(list_replay_cache()))
    stats_cols[2].metric("Radio cache", "Ready" if RADIO_CACHE_DIR.exists() else "Missing")

    for label, folder in locations:
        folder.mkdir(parents=True, exist_ok=True)
        files = sorted([p for p in folder.rglob("*") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)[:40]
        with st.expander(f"{label} - {len(files)} files", expanded=label in {"Telemetry files", "Chart images", "Replay payload cache"}):
            if not files:
                st.caption(str(folder))
                st.info("No files here yet.")
                continue
            st.caption(str(folder))
            file_df = pd.DataFrame(
                {
                    "file": [p.name for p in files],
                    "type": [p.suffix.lower().lstrip(".") or "file" for p in files],
                    "size_kb": [round(p.stat().st_size / 1024, 1) for p in files],
                    "modified": [pd.to_datetime(p.stat().st_mtime, unit="s") for p in files],
                }
            )
            st.dataframe(file_df, use_container_width=True, hide_index=True)
            selected_file = st.selectbox(
                f"Download from {label}",
                files,
                format_func=lambda p: p.name,
                key=f"download_{safe_filename(label)}",
            )
            if selected_file and selected_file.exists():
                st.download_button(
                    f"Download {selected_file.name}",
                    data=selected_file.read_bytes(),
                    file_name=selected_file.name,
                    mime="application/octet-stream",
                    key=f"download_btn_{safe_filename(label)}",
                )


def render_overview_section():
    latest = get_latest_completed_race(date.today().year)
    st.subheader("Overview")
    st.markdown(
        """
        <div class="f1-note">
            Latest race context, data status, recent outputs, and shortcuts into the main workspaces.
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest completed race", latest["event_name"])
    c2.metric("Year", latest["year"])
    c3.metric("Round", latest.get("round_number") or "-")
    c4.metric("Replay cache", f"{len(list_replay_cache())} payloads")

    s1, s2, s3 = st.columns(3)
    s1.success("FastF1 cache ready" if (BASE_DIR / "fastf1_cache").exists() else "FastF1 cache missing")
    s2.info("OpenF1 fallback available in telemetry export")
    s3.info("Public radio archive available when f1radio has clips")

    qa1, qa2, qa3, qa4 = st.columns(4)
    if qa1.button("Open latest race analytics", use_container_width=True):
        st.session_state["workspace_nav"] = "Analytics"
        st.session_state["analysis_mode"] = "Race Weekend"
        st.rerun()
    if qa2.button("Export latest fastest lap", use_container_width=True):
        st.session_state["workspace_nav"] = "Telemetry Export"
        st.session_state["analysis_mode"] = "Race Weekend"
        st.rerun()
    if qa3.button("Load latest race replay", use_container_width=True):
        st.session_state["workspace_nav"] = "Race Replay"
        st.session_state["replay_year"] = int(latest["year"])
        st.session_state["replay_event"] = latest["event_name"]
        st.rerun()
    if qa4.button("Browse latest radio clips", use_container_width=True):
        st.session_state["workspace_nav"] = "Radio"
        st.rerun()

    recent_exports = sorted(
        [p for p in OUTPUT_DIR.rglob("*") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:12]
    r1, r2 = st.columns([1.1, 1])
    with r1:
        st.markdown("#### Recent export files")
        if recent_exports:
            st.dataframe(
                pd.DataFrame(
                    {
                        "file": [p.name for p in recent_exports],
                        "folder": [p.parent.name for p in recent_exports],
                        "size_kb": [round(p.stat().st_size / 1024, 1) for p in recent_exports],
                        "modified": [pd.to_datetime(p.stat().st_mtime, unit="s") for p in recent_exports],
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No exports yet.")
    with r2:
        st.markdown("#### Recent chart previews")
        chart_files = sorted(OUTPUT_CHART_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
        if chart_files:
            for path in chart_files:
                st.image(str(path), caption=path.name, use_container_width=True)
        else:
            st.info("Generate a chart to see previews here.")


apply_app_chrome()

if workspace == "Overview":
    render_overview_section()
    st.stop()

if workspace == "Radio":
    render_radio_messages_section()
    st.stop()

if workspace == "Race Replay":
    render_race_replay_section()
    st.stop()

if workspace == "Files":
    render_library_section()
    st.stop()


if mode == "Race Weekend":
    if lap_output_mode:
        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            year = st.number_input("Year", min_value=2018, max_value=2035, value=2026, step=1)
        event_options = get_race_event_options(int(year))
        latest_for_year = get_latest_completed_race(int(year))
        default_event_idx = event_options.index(latest_for_year["event_name"]) if latest_for_year["event_name"] in event_options else 0
        with c2:
            event_name = st.selectbox("Track / Event", event_options, index=default_event_idx)
        with c3:
            session_name = st.selectbox("Session", ["FP1", "FP2", "FP3", "Q", "R", "SQ", "SS"], index=2)
        driver_catalog = get_driver_catalog("Race Weekend", year, event_name, session_name, None, None)
        driver_options = driver_catalog["code"].tolist()
        default_idx = driver_options.index("LEC") if "LEC" in driver_options else 0
        with c4:
            driver = st.selectbox("Driver", driver_options, index=default_idx, format_func=lambda c: driver_catalog.loc[driver_catalog["code"] == c, "label"].iloc[0] if (driver_catalog["code"] == c).any() else c)
        with c5:
            lap_mode = st.selectbox("Lap", ["Fastest", "Lap number"], index=0)

        lap_number = None
        if lap_mode == "Lap number":
            lap_number = st.number_input("Lap #", min_value=1, max_value=300, value=1, step=1)

        render_driver_picker_preview(driver_catalog, driver, "Selected Driver")
        normalize_distance = st.checkbox("Normalize Distance to 0-1", value=False)
        btn_generate = st.button("Generate", type="primary")
        if btn_generate:
            try:
                with st.spinner("Loading session and building telemetry..."):
                    session, tel_df, lap = build_selected_lap_tel(
                        mode="Race Weekend",
                        year=year,
                        event_name=event_name,
                        session_name=session_name,
                        test_number=None,
                        day_number=None,
                        driver=driver,
                        lap_mode=lap_mode,
                        lap_number=lap_number,
                    )

                lap_seconds = float(tel_df["t"].iloc[-1])
                st.write(f"Lap duration: {lap_seconds:.3f}s")

                safe_event = str(event_name).replace(" ", "_")
                label = driver.upper()
                csv_name = f"telemetry_{year}_{safe_event}_{session_name}_{label}_{lap_mode}.csv"
                telemetry_csv = tel_df.to_csv(index=False).encode("utf-8")
                (OUTPUT_TELEMETRY_DIR / csv_name).write_bytes(telemetry_csv)

                st.download_button(
                    "Download LAP telemetry CSV",
                    data=telemetry_csv,
                    file_name=csv_name,
                    mime="text/csv",
                )

                full_tel = lap.get_telemetry()
                st.write("Available telemetry columns:")
                st.write(list(full_tel.columns))
                full_csv_name = (
                    f"full_telemetry_{year}_{safe_event}_{session_name}_{label}_{lap_mode}"
                    f"{'_normalized_distance' if normalize_distance and 'Distance' in full_tel.columns else ''}.csv"
                )
                full_csv = full_tel.to_csv(index=False).encode("utf-8")
                (OUTPUT_TELEMETRY_DIR / full_csv_name).write_bytes(full_csv)
                st.download_button(
                    "Download FULL Telemetry CSV",
                    data=full_csv,
                    file_name=full_csv_name,
                    mime="text/csv",
                )
                
                ae_df = make_after_effects_tsv(full_tel, fps=int(fps))
                ae_name = f"ae_dataver_{year}_{safe_event}_{session_name}_{label}_{lap_mode}.tsv"
                ae_tsv = ae_df.to_csv(sep="\t", index=False).encode("utf-8")
                (OUTPUT_TELEMETRY_DIR / ae_name).write_bytes(ae_tsv)

                st.download_button(
                    "Download After Effects TSV",
                    data=ae_tsv,
                    file_name=ae_name,
                    mime="text/tab-separated-values",
                )

                # Optional preprocessing for After Effects: normalize track distance to 0..1.
                if normalize_distance and "Distance" in full_tel.columns:
                    full_tel = full_tel.copy()
                    max_dist = full_tel["Distance"].max()
                    if pd.notna(max_dist) and max_dist not in (0, 0.0):
                        full_tel["Distance"] = full_tel["Distance"] / float(max_dist)
                    else:
                        full_tel["Distance"] = 0.0

                rr_df = make_racerender_csv(full_tel)
                rr_name = (
                    f"racerender_{year}_{safe_event}_{session_name}_{label}_{lap_mode}"
                    f"{'_normalized_distance' if normalize_distance and 'Distance' in full_tel.columns else ''}.csv"
                )
                rr_csv = rr_df.to_csv(index=False).encode("utf-8")
                (OUTPUT_TELEMETRY_DIR / rr_name).write_bytes(rr_csv)
                st.download_button(
                    "Download RaceRender Telemetry CSV (km/h)",
                    data=rr_csv,
                    file_name=rr_name,
                    mime="text/csv",
                )

                st.success("Telemetry prepared for After Effects.")

            except Exception as e:
                st.error(str(e))
                st.stop()

    else:
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            year = st.number_input("Year", min_value=2018, max_value=2035, value=2026, step=1)
        event_options = get_race_event_options(int(year))
        latest_for_year = get_latest_completed_race(int(year))
        default_event_idx = event_options.index(latest_for_year["event_name"]) if latest_for_year["event_name"] in event_options else 0
        with c2:
            event_name = st.selectbox("Track / Event", event_options, index=default_event_idx)
        with c3:
            session_name = st.selectbox("Session", ["FP1", "FP2", "FP3", "Q", "R", "SQ", "SS"], index=4)
        with c4:
            st.write("")
            st.write("")
            st.caption("Charts use full session data")

        driver_catalog = get_driver_catalog("Race Weekend", year, event_name, session_name, None, None)
        driver_options = driver_catalog["code"].tolist()

        selected_drivers = []
        compare_driver = None
        driver = None
        comp_lap = None
        lap_compare_mode = None
        compare_lap = None

        if create_mode == "Car Pace Delta Map":
            lap_compare_mode = st.selectbox(
                "Lap source",
                ["Fastest lap", "Same lap number", "Median race lap"],
                index=2
            )

            if lap_compare_mode == "Same lap number":
                compare_lap = st.number_input("Lap #", min_value=1, max_value=300, value=20, step=1)

        if create_mode in {"Stint strategy", "Hard stint average pace", "Medium stint average pace","Lap consistency","Selected driver race pace","Position Tracker","Gap to Leader","Tyre Degradation Analysis","Sector Performance Heatmap",}:
            drivers_text = st.text_input("Drivers (comma-separated)", value="RUS, ANT, LEC, HAM")
            selected_drivers = parse_driver_list(drivers_text)

        if create_mode in {"Lap-by-lap pace delta","Lap-by-lap delta + stints","Fastest lap map","Driver lap comparison","Telemetry Comparison","Car Pace Delta Map",}:
            d1, d2 = st.columns(2)
            idx_a = driver_options.index("RUS") if "RUS" in driver_options else 0
            idx_b = driver_options.index("LEC") if "LEC" in driver_options else (1 if len(driver_options) > 1 else 0)
            with d1:
                driver = st.selectbox("Driver A", driver_options, index=idx_a, format_func=lambda c: driver_catalog.loc[driver_catalog["code"] == c, "label"].iloc[0] if (driver_catalog["code"] == c).any() else c)
            with d2:
                compare_driver = st.selectbox("Driver B", driver_options, index=idx_b, format_func=lambda c: driver_catalog.loc[driver_catalog["code"] == c, "label"].iloc[0] if (driver_catalog["code"] == c).any() else c)
            render_driver_picker_preview(driver_catalog, driver, "Driver A")
            render_driver_picker_preview(driver_catalog, compare_driver, "Driver B")
        if create_mode == "Telemetry Comparison":
            comp_lap = st.number_input("Lap #", min_value=1, max_value=300, value=10, step=1)

        btn_generate = st.button("Generate", type="primary")

        if btn_generate:
            try:
                with st.spinner("Loading session..."):
                    session = get_session_from_inputs(
                        mode="Race Weekend",
                        year=year,
                        event_name=event_name,
                        session_name=session_name,
                        test_number=None,
                        day_number=None,
                        require_telemetry=False,
                    )

                safe_event = str(event_name).replace(" ", "_")

                if create_mode == "Stint strategy":
                    out_path = OUTPUT_CHART_DIR / f"stint_strategy_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering stint strategy chart..."):
                        render_stint_strategy(session, selected_drivers, out_path)

                elif create_mode == "Lap-by-lap pace delta":
                    out_path = OUTPUT_CHART_DIR / f"lap_delta_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering lap-by-lap pace delta..."):
                        render_lap_delta(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Lap-by-lap delta + stints":
                    out_path = OUTPUT_CHART_DIR / f"lap_delta_stints_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering lap-by-lap delta + stints..."):
                        render_lap_delta_with_stints(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Hard stint average pace":
                    out_path = OUTPUT_CHART_DIR / f"hard_stint_avg_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering hard stint average pace chart..."):
                        render_stint_average_pace(session, selected_drivers, "HARD", out_path)

                elif create_mode == "Medium stint average pace":
                    out_path = OUTPUT_CHART_DIR / f"medium_stint_avg_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering medium stint average pace chart..."):
                        render_stint_average_pace(session, selected_drivers, "MEDIUM", out_path)
                elif create_mode == "Fastest lap map":
                    out_path = OUTPUT_CHART_DIR / f"fastest_lap_map_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering fastest lap comparison map..."):
                        render_fastest_lap_map(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Lap consistency":
                    out_path = OUTPUT_CHART_DIR / f"lap_consistency_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering lap consistency chart..."):
                        render_lap_consistency(session, selected_drivers, out_path)

                elif create_mode == "Driver lap comparison":
                    out_path = OUTPUT_CHART_DIR / f"driver_lap_comparison_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering driver lap comparison..."):
                        render_driver_lap_comparison(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Selected driver race pace":
                    out_path = OUTPUT_CHART_DIR / f"selected_driver_race_pace_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering selected driver race pace..."):
                        render_selected_driver_race_pace(session, selected_drivers, out_path)

                elif create_mode == "Team race pace delta":
                    out_path = OUTPUT_CHART_DIR / f"team_race_pace_delta_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering team race pace delta..."):
                        render_team_race_pace_delta(session, out_path)
               # --- CORRECTED NEW CODE ---
                elif create_mode == "Position Tracker":
                    # Changed safe_test -> safe_event and added session_name
                    out_path = OUTPUT_CHART_DIR / f"position_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering Position Tracker..."):
                        render_position_tracker(session, selected_drivers, out_path)

                elif create_mode == "Telemetry Comparison":
                    # Added .upper() to match your style and session_name for consistency
                    out_path = OUTPUT_CHART_DIR / f"telemetry_L{comp_lap}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner(f"Rendering Telemetry for Lap {comp_lap}..."):
                        render_telemetry_comparison(session, comp_lap, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Speed Trap Analysis":
                    # Changed safe_test -> safe_event
                    out_path = OUTPUT_CHART_DIR / f"speedtrap_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering Speed Trap Analysis..."):
                        render_speed_traps(session, out_path)
                # --------------------------------
                elif create_mode == "Gap to Leader":
                    out_path = OUTPUT_CHART_DIR / f"gap_leader_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Calculating gaps to leader..."):
                        render_gap_to_leader(session, selected_drivers, out_path)

                elif create_mode == "Tyre Degradation Analysis":
                    out_path = OUTPUT_CHART_DIR / f"tyre_deg_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Analyzing tyre degradation..."):
                        render_tyre_deg_analysis(session, selected_drivers, out_path)
                        
                elif create_mode == "Sector Performance Heatmap":
                    out_path = OUTPUT_CHART_DIR / f"sector_heatmap_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering sector performance heatmap..."):
                        render_sector_performance_heatmap(session, selected_drivers, out_path)
                        
                elif create_mode == "Car Pace Delta Map":
                    out_path = OUTPUT_CHART_DIR / f"car_pace_map_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering car pace delta map..."):
                        render_car_pace_delta_map(
                            session,
                            driver.upper(),
                            compare_driver.upper(),
                            out_path,
                            lap_mode=lap_compare_mode,
                            lap_number=compare_lap
                        )

                else:
                    raise RuntimeError("Unsupported create mode.")

                st.success("Done.")
                st.image(str(out_path))
                st.download_button(
                    "Download PNG",
                    data=out_path.read_bytes(),
                    file_name=out_path.name,
                    mime="image/png",
                )

            except Exception as e:
                st.error(str(e))
                st.stop()

else:
    if lap_output_mode:
        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            year = st.number_input("Year", min_value=2018, max_value=2035, value=2026, step=1)
        with c2:
            test_number = st.number_input("Test #", min_value=1, max_value=3, value=1, step=1)
        with c3:
            day_number = st.number_input("Day #", min_value=1, max_value=7, value=3, step=1)
        driver_catalog = get_driver_catalog("Pre-season Testing", year, None, None, test_number, day_number)
        driver_options = driver_catalog["code"].tolist()
        default_idx = driver_options.index("LEC") if "LEC" in driver_options else 0
        with c4:
            driver = st.selectbox("Driver", driver_options, index=default_idx, format_func=lambda c: driver_catalog.loc[driver_catalog["code"] == c, "label"].iloc[0] if (driver_catalog["code"] == c).any() else c)
        with c5:
            lap_mode = st.selectbox("Lap", ["Fastest", "Lap number"], index=0)

        lap_number = None
        if lap_mode == "Lap number":
            lap_number = st.number_input("Lap #", min_value=1, max_value=300, value=1, step=1)

        render_driver_picker_preview(driver_catalog, driver, "Selected Driver")
        normalize_distance = st.checkbox("Normalize Distance to 0-1", value=False)
        btn_generate = st.button("Generate", type="primary")
        if btn_generate:
            try:
                with st.spinner("Loading session and building telemetry..."):
                    session, tel_df, lap = build_selected_lap_tel(
                        mode="Pre-season Testing",
                        year=year,
                        event_name=None,
                        session_name=None,
                        test_number=test_number,
                        day_number=day_number,
                        driver=driver,
                        lap_mode=lap_mode,
                        lap_number=lap_number,
                    )

                lap_seconds = float(tel_df["t"].iloc[-1])
                st.write(f"Lap duration: {lap_seconds:.3f}s")

                label = driver.upper()
                safe_test = f"T{int(test_number)}_D{int(day_number)}"
                csv_name = f"telemetry_{year}_{safe_test}_{label}_{lap_mode}.csv"
                telemetry_csv = tel_df.to_csv(index=False).encode("utf-8")
                (OUTPUT_TELEMETRY_DIR / csv_name).write_bytes(telemetry_csv)

                st.download_button(
                    "Download LAP telemetry CSV",
                    data=telemetry_csv,
                    file_name=csv_name,
                    mime="text/csv",
                )

                full_tel = lap.get_telemetry()
                st.write("Available telemetry columns:")
                st.write(list(full_tel.columns))
                full_csv_name = (
                    f"full_telemetry_{year}_{safe_test}_{label}_{lap_mode}"
                    f"{'_normalized_distance' if normalize_distance and 'Distance' in full_tel.columns else ''}.csv"
                )
                full_csv = full_tel.to_csv(index=False).encode("utf-8")
                (OUTPUT_TELEMETRY_DIR / full_csv_name).write_bytes(full_csv)
                st.download_button(
                    "Download FULL Telemetry CSV",
                    data=full_csv,
                    file_name=full_csv_name,
                    mime="text/csv",
                )
                
                ae_df = make_after_effects_tsv(full_tel, fps=int(fps))
                ae_name = f"ae_dataver_{year}_{safe_test}_{label}_{lap_mode}.tsv"
                ae_tsv = ae_df.to_csv(sep="\t", index=False).encode("utf-8")
                (OUTPUT_TELEMETRY_DIR / ae_name).write_bytes(ae_tsv)

                st.download_button(
                    "Download After Effects TSV",
                    data=ae_tsv,
                    file_name=ae_name,
                    mime="text/tab-separated-values",
                )

                # Optional preprocessing for After Effects: normalize track distance to 0..1.
                if normalize_distance and "Distance" in full_tel.columns:
                    full_tel = full_tel.copy()
                    max_dist = full_tel["Distance"].max()
                    if pd.notna(max_dist) and max_dist not in (0, 0.0):
                        full_tel["Distance"] = full_tel["Distance"] / float(max_dist)
                    else:
                        full_tel["Distance"] = 0.0

                rr_df = make_racerender_csv(full_tel)
                rr_name = (
                    f"racerender_{year}_{safe_test}_{label}_{lap_mode}"
                    f"{'_normalized_distance' if normalize_distance and 'Distance' in full_tel.columns else ''}.csv"
                )
                rr_csv = rr_df.to_csv(index=False).encode("utf-8")
                (OUTPUT_TELEMETRY_DIR / rr_name).write_bytes(rr_csv)
                st.download_button(
                    "Download RaceRender Telemetry CSV (km/h)",
                    data=rr_csv,
                    file_name=rr_name,
                    mime="text/csv",
                )

                st.success("Telemetry prepared for After Effects.")

            except Exception as e:
                st.error(str(e))
                st.stop()

    else:
        c1, c2, c3 = st.columns(3)

        with c1:
            year = st.number_input("Year", min_value=2018, max_value=2035, value=2026, step=1)
        with c2:
            test_number = st.number_input("Test #", min_value=1, max_value=3, value=1, step=1)
        with c3:
            day_number = st.number_input("Day #", min_value=1, max_value=7, value=3, step=1)

        driver_catalog = get_driver_catalog("Pre-season Testing", year, None, None, test_number, day_number)
        driver_options = driver_catalog["code"].tolist()
        
        selected_drivers = []
        compare_driver = None
        driver = None
        comp_lap = None

        if create_mode in {"Stint strategy", "Hard stint average pace", "Medium stint average pace", "Lap consistency", "Selected driver race pace", "Position Tracker"}:
            drivers_text = st.text_input("Drivers (comma-separated)", value="RUS, ANT, LEC, HAM")
            selected_drivers = parse_driver_list(drivers_text)
            

        if create_mode in {"Lap-by-lap pace delta", "Lap-by-lap delta + stints", "Fastest lap map", "Driver lap comparison", "Telemetry Comparison"}:
            d1, d2 = st.columns(2)
            idx_a = driver_options.index("RUS") if "RUS" in driver_options else 0
            idx_b = driver_options.index("LEC") if "LEC" in driver_options else (1 if len(driver_options) > 1 else 0)
            with d1:
                driver = st.selectbox("Driver A", driver_options, index=idx_a, format_func=lambda c: driver_catalog.loc[driver_catalog["code"] == c, "label"].iloc[0] if (driver_catalog["code"] == c).any() else c)
            with d2:
                compare_driver = st.selectbox("Driver B", driver_options, index=idx_b, format_func=lambda c: driver_catalog.loc[driver_catalog["code"] == c, "label"].iloc[0] if (driver_catalog["code"] == c).any() else c)
            render_driver_picker_preview(driver_catalog, driver, "Driver A")
            render_driver_picker_preview(driver_catalog, compare_driver, "Driver B")

        btn_generate = st.button("Generate", type="primary")

        if btn_generate:
            try:
                with st.spinner("Loading testing session..."):
                    session = get_session_from_inputs(
                        mode="Pre-season Testing",
                        year=year,
                        event_name=None,
                        session_name=None,
                        test_number=test_number,
                        day_number=day_number,
                        require_telemetry=False,
                    )

                safe_test = f"T{int(test_number)}_D{int(day_number)}"

                if create_mode == "Stint strategy":
                    out_path = OUTPUT_CHART_DIR / f"stint_strategy_{year}_{safe_test}.png"
                    with st.spinner("Rendering stint strategy chart..."):
                        render_stint_strategy(session, selected_drivers, out_path)

                elif create_mode == "Lap-by-lap pace delta":
                    out_path = OUTPUT_CHART_DIR / f"lap_delta_{year}_{safe_test}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering lap-by-lap pace delta..."):
                        render_lap_delta(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Lap-by-lap delta + stints":
                    out_path = OUTPUT_CHART_DIR / f"lap_delta_stints_{year}_{safe_test}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering lap-by-lap delta + stints..."):
                        render_lap_delta_with_stints(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Hard stint average pace":
                    out_path = OUTPUT_CHART_DIR / f"hard_stint_avg_{year}_{safe_test}.png"
                    with st.spinner("Rendering hard stint average pace chart..."):
                        render_stint_average_pace(session, selected_drivers, "HARD", out_path)

                elif create_mode == "Medium stint average pace":
                    out_path = OUTPUT_CHART_DIR / f"medium_stint_avg_{year}_{safe_test}.png"
                    with st.spinner("Rendering medium stint average pace chart..."):
                        render_stint_average_pace(session, selected_drivers, "MEDIUM", out_path)

                else:
                    raise RuntimeError("Unsupported create mode.")

                st.success("Done.")
                st.image(str(out_path))
                st.download_button(
                    "Download PNG",
                    data=out_path.read_bytes(),
                    file_name=out_path.name,
                    mime="image/png",
                )

            except Exception as e:
                st.error(str(e))
                st.stop()
'''
