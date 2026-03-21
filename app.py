import streamlit as st
import fastf1
import fastf1.plotting
from pathlib import Path
import pandas as pd
import numpy as np

from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib.patheffects as path_effects
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.colors as mcolors


# -----------------------------------------------------------------------------
# FastF1 / matplotlib style
# -----------------------------------------------------------------------------
fastf1.plotting.setup_mpl(
    mpl_timedelta_support=False,
    color_scheme="fastf1",
    misc_mpl_mods=False
)

image_format = st.selectbox(
    "Image format",
    ["16:9 (YouTube)", "1:1 (Instagram)", "9:16 (TikTok)"],
    index=0
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


def get_figsize(format_mode):
    if format_mode == "16:9 (YouTube)":
        return (16, 9)
    if format_mode == "1:1 (Instagram)":
        return (10, 10)
    if format_mode == "9:16 (TikTok)":
        return (9, 16)

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
):
    if mode == "Race Weekend":
        session = fastf1.get_session(int(year), event_name, session_name)
    else:
        session = fastf1.get_testing_session(int(year), int(test_number), int(day_number))

    session.load(laps=True, telemetry=True, weather=False, messages=False)
    return session


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


# -----------------------------------------------------------------------------
# Paths / cache
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

try:
    BASE_DIR = Path(__file__).parent
    cache_dir = BASE_DIR / "fastf1_cache"
    cache_dir.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))
except:
    # fallback for cloud (Streamlit, Render, etc.)
    fastf1.Cache.enable_cache("/tmp/fastf1")


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.set_page_config(page_title="F1 HYPE Generator", layout="wide")
st.title("F1 HYPE Generator (Local)")

left, right = st.columns([1, 1])

with left:
    mode = st.selectbox("Mode", ["Race Weekend", "Pre-season Testing"], index=0)

with right:
    fps = st.selectbox("Export FPS", [25, 30, 50], index=1)


create_mode = st.selectbox(
    "Create",
    [
        "Race Telemetry",
        "Stint strategy",
        "Lap-by-lap pace delta",
        "Lap-by-lap delta + stints",
        "Hard stint average pace",
        "Medium stint average pace",
        "Fastest lap map",
        "Lap consistency",
        "Driver lap comparison",
        "Selected driver race pace",
        "Team race pace delta",
        "Position Tracker",        # New
        "Telemetry Comparison",    # New
        "Speed Trap Analysis",
        "Gap to Leader",
        "Tyre Degradation Analysis",
        "Sector Performance Heatmap",
        "Car Pace Delta Map",
    ],
    index=0,
)


with st.sidebar:
    st.subheader("Chart Colors")
    color_mode_ui = st.selectbox(
        "Color mode",
        ["FastF1 Official", "Custom", "Monochrome"],
        index=0,
        help="Use official FastF1 colors or override them for chart visuals."
    )

    custom_color_a_ui = "#00D2BE"
    custom_color_b_ui = "#DC0000"

    if color_mode_ui == "Custom":
        custom_color_a_ui = st.color_picker("Driver / Series Color A", "#00D2BE")
        custom_color_b_ui = st.color_picker("Driver / Series Color B", "#DC0000")
    elif color_mode_ui == "Monochrome":
        st.caption("Monochrome uses white + purple for cleaner analytics charts.")

COLOR_MODE = color_mode_ui
CUSTOM_COLOR_A = custom_color_a_ui
CUSTOM_COLOR_B = custom_color_b_ui

chart_mode = create_mode in {
    "Stint strategy",
    "Lap-by-lap pace delta",
    "Lap-by-lap delta + stints",
    "Hard stint average pace",
    "Medium stint average pace",
    "Fastest lap map",
    "Lap consistency",
    "Driver lap comparison",
    "Selected driver race pace",
    "Team race pace delta",
    "Position Tracker",        # New
    "Telemetry Comparison",    # New
    "Speed Trap Analysis",
    "Gap to Leader",
    "Tyre Degradation Analysis",
    "Sector Performance Heatmap",
    "Car Pace Delta Map",
}

lap_output_mode = create_mode in {"Race Telemetry"}


def parse_driver_list(txt: str) -> list[str]:
    return [x.strip().upper() for x in txt.split(",") if x.strip()]


if mode == "Race Weekend":
    if lap_output_mode:
        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            year = st.number_input("Year", min_value=2018, max_value=2035, value=2026, step=1)
        with c2:
            event_name = st.text_input("Event name", value="Bahrain")
        with c3:
            session_name = st.selectbox("Session", ["FP1", "FP2", "FP3", "Q", "R", "SQ", "SS"], index=2)
        with c4:
            driver = st.text_input("Driver code", value="LEC")
        with c5:
            lap_mode = st.selectbox("Lap", ["Fastest", "Lap number"], index=0)

        lap_number = None
        if lap_mode == "Lap number":
            lap_number = st.number_input("Lap #", min_value=1, max_value=300, value=1, step=1)

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

                st.download_button(
                    "Download LAP telemetry CSV",
                    data=tel_df.to_csv(index=False).encode("utf-8"),
                    file_name=csv_name,
                    mime="text/csv",
                )

                full_tel = lap.get_telemetry()
                st.write("Available telemetry columns:")
                st.write(list(full_tel.columns))
                st.download_button(
                    "Download FULL Telemetry CSV",
                    data=full_tel.to_csv(index=False).encode("utf-8"),
                    file_name=(
                        f"full_telemetry_{year}_{safe_event}_{session_name}_{label}_{lap_mode}"
                        f"{'_normalized_distance' if normalize_distance and 'Distance' in full_tel.columns else ''}.csv"
                    ),
                    mime="text/csv",
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
                st.download_button(
                    "Download RaceRender Telemetry CSV (km/h)",
                    data=rr_df.to_csv(index=False).encode("utf-8"),
                    file_name=(
                        f"racerender_{year}_{safe_event}_{session_name}_{label}_{lap_mode}"
                        f"{'_normalized_distance' if normalize_distance and 'Distance' in full_tel.columns else ''}.csv"
                    ),
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
        with c2:
            event_name = st.text_input("Event name", value="Australia")
        with c3:
            session_name = st.selectbox("Session", ["FP1", "FP2", "FP3", "Q", "R", "SQ", "SS"], index=4)
        with c4:
            st.write("")
            st.write("")
            st.caption("Charts use full session data")

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
            with d1:
                driver = st.text_input("Driver A", value="RUS")
            with d2:
                compare_driver = st.text_input("Driver B", value="LEC")
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
                    )

                safe_event = str(event_name).replace(" ", "_")

                if create_mode == "Stint strategy":
                    out_path = OUTPUT_DIR / f"stint_strategy_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering stint strategy chart..."):
                        render_stint_strategy(session, selected_drivers, out_path)

                elif create_mode == "Lap-by-lap pace delta":
                    out_path = OUTPUT_DIR / f"lap_delta_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering lap-by-lap pace delta..."):
                        render_lap_delta(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Lap-by-lap delta + stints":
                    out_path = OUTPUT_DIR / f"lap_delta_stints_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering lap-by-lap delta + stints..."):
                        render_lap_delta_with_stints(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Hard stint average pace":
                    out_path = OUTPUT_DIR / f"hard_stint_avg_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering hard stint average pace chart..."):
                        render_stint_average_pace(session, selected_drivers, "HARD", out_path)

                elif create_mode == "Medium stint average pace":
                    out_path = OUTPUT_DIR / f"medium_stint_avg_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering medium stint average pace chart..."):
                        render_stint_average_pace(session, selected_drivers, "MEDIUM", out_path)
                elif create_mode == "Fastest lap map":
                    out_path = OUTPUT_DIR / f"fastest_lap_map_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering fastest lap comparison map..."):
                        render_fastest_lap_map(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Lap consistency":
                    out_path = OUTPUT_DIR / f"lap_consistency_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering lap consistency chart..."):
                        render_lap_consistency(session, selected_drivers, out_path)

                elif create_mode == "Driver lap comparison":
                    out_path = OUTPUT_DIR / f"driver_lap_comparison_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering driver lap comparison..."):
                        render_driver_lap_comparison(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Selected driver race pace":
                    out_path = OUTPUT_DIR / f"selected_driver_race_pace_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering selected driver race pace..."):
                        render_selected_driver_race_pace(session, selected_drivers, out_path)

                elif create_mode == "Team race pace delta":
                    out_path = OUTPUT_DIR / f"team_race_pace_delta_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering team race pace delta..."):
                        render_team_race_pace_delta(session, out_path)
               # --- CORRECTED NEW CODE ---
                elif create_mode == "Position Tracker":
                    # Changed safe_test -> safe_event and added session_name
                    out_path = OUTPUT_DIR / f"position_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering Position Tracker..."):
                        render_position_tracker(session, selected_drivers, out_path)

                elif create_mode == "Telemetry Comparison":
                    # Added .upper() to match your style and session_name for consistency
                    out_path = OUTPUT_DIR / f"telemetry_L{comp_lap}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner(f"Rendering Telemetry for Lap {comp_lap}..."):
                        render_telemetry_comparison(session, comp_lap, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Speed Trap Analysis":
                    # Changed safe_test -> safe_event
                    out_path = OUTPUT_DIR / f"speedtrap_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering Speed Trap Analysis..."):
                        render_speed_traps(session, out_path)
                # --------------------------------
                elif create_mode == "Gap to Leader":
                    out_path = OUTPUT_DIR / f"gap_leader_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Calculating gaps to leader..."):
                        render_gap_to_leader(session, selected_drivers, out_path)

                elif create_mode == "Tyre Degradation Analysis":
                    out_path = OUTPUT_DIR / f"tyre_deg_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Analyzing tyre degradation..."):
                        render_tyre_deg_analysis(session, selected_drivers, out_path)
                        
                elif create_mode == "Sector Performance Heatmap":
                    out_path = OUTPUT_DIR / f"sector_heatmap_{year}_{safe_event}_{session_name}.png"
                    with st.spinner("Rendering sector performance heatmap..."):
                        render_sector_performance_heatmap(session, selected_drivers, out_path)
                        
                elif create_mode == "Car Pace Delta Map":
                    out_path = OUTPUT_DIR / f"car_pace_map_{year}_{safe_event}_{session_name}_{driver.upper()}_{compare_driver.upper()}.png"
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
        with c4:
            driver = st.text_input("Driver code", value="LEC")
        with c5:
            lap_mode = st.selectbox("Lap", ["Fastest", "Lap number"], index=0)

        lap_number = None
        if lap_mode == "Lap number":
            lap_number = st.number_input("Lap #", min_value=1, max_value=300, value=1, step=1)

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

                st.download_button(
                    "Download LAP telemetry CSV",
                    data=tel_df.to_csv(index=False).encode("utf-8"),
                    file_name=csv_name,
                    mime="text/csv",
                )

                full_tel = lap.get_telemetry()
                st.write("Available telemetry columns:")
                st.write(list(full_tel.columns))
                st.download_button(
                    "Download FULL Telemetry CSV",
                    data=full_tel.to_csv(index=False).encode("utf-8"),
                    file_name=(
                        f"full_telemetry_{year}_{safe_test}_{label}_{lap_mode}"
                        f"{'_normalized_distance' if normalize_distance and 'Distance' in full_tel.columns else ''}.csv"
                    ),
                    mime="text/csv",
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
                st.download_button(
                    "Download RaceRender Telemetry CSV (km/h)",
                    data=rr_df.to_csv(index=False).encode("utf-8"),
                    file_name=(
                        f"racerender_{year}_{safe_test}_{label}_{lap_mode}"
                        f"{'_normalized_distance' if normalize_distance and 'Distance' in full_tel.columns else ''}.csv"
                    ),
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
        
        selected_drivers = []
        compare_driver = None
        driver = None
        comp_lap = None

        if create_mode in {"Stint strategy", "Hard stint average pace", "Medium stint average pace", "Lap consistency", "Selected driver race pace", "Position Tracker"}:
            drivers_text = st.text_input("Drivers (comma-separated)", value="RUS, ANT, LEC, HAM")
            selected_drivers = parse_driver_list(drivers_text)
            

        if create_mode in {"Lap-by-lap pace delta", "Lap-by-lap delta + stints", "Fastest lap map", "Driver lap comparison", "Telemetry Comparison"}:
            d1, d2 = st.columns(2)
            with d1:
                driver = st.text_input("Driver A", value="RUS")
            with d2:
                compare_driver = st.text_input("Driver B", value="LEC")

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
                    )

                safe_test = f"T{int(test_number)}_D{int(day_number)}"

                if create_mode == "Stint strategy":
                    out_path = OUTPUT_DIR / f"stint_strategy_{year}_{safe_test}.png"
                    with st.spinner("Rendering stint strategy chart..."):
                        render_stint_strategy(session, selected_drivers, out_path)

                elif create_mode == "Lap-by-lap pace delta":
                    out_path = OUTPUT_DIR / f"lap_delta_{year}_{safe_test}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering lap-by-lap pace delta..."):
                        render_lap_delta(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Lap-by-lap delta + stints":
                    out_path = OUTPUT_DIR / f"lap_delta_stints_{year}_{safe_test}_{driver.upper()}_{compare_driver.upper()}.png"
                    with st.spinner("Rendering lap-by-lap delta + stints..."):
                        render_lap_delta_with_stints(session, driver.upper(), compare_driver.upper(), out_path)

                elif create_mode == "Hard stint average pace":
                    out_path = OUTPUT_DIR / f"hard_stint_avg_{year}_{safe_test}.png"
                    with st.spinner("Rendering hard stint average pace chart..."):
                        render_stint_average_pace(session, selected_drivers, "HARD", out_path)

                elif create_mode == "Medium stint average pace":
                    out_path = OUTPUT_DIR / f"medium_stint_avg_{year}_{safe_test}.png"
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